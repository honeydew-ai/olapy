# -*- encoding: utf8 -*-
"""
The main Module to manage `XMLA <https://technet.microsoft.com/fr-fr/library/ms187178(v=sql.90).aspx>`_ \
requests and responses, and managing Spyne soap server.

"""
from __future__ import absolute_import, division, print_function

import imp
import logging
import os
import sys
from datetime import datetime
from os.path import expanduser
from wsgiref.simple_server import make_server

import click
import xmlwitch
from spyne import AnyXml, Application, Fault, ServiceBase, rpc
from spyne.const.http import HTTP_200
from spyne.error import InvalidCredentialsError
from spyne.protocol.soap import Soap11
from spyne.server.http import HttpTransportContext
from spyne.server.wsgi import WsgiApplication

from ..services.models import DiscoverRequest, ExecuteRequest, Session
from .xmla_discover_tools import XmlaDiscoverTools
from .xmla_execute_tools import XmlaExecuteTools
from .xmla_execute_xsds import execute_xsd


class XmlaSoap11(Soap11):
    """XHR does not work over https without this patch"""

    def create_in_document(self, ctx, charset=None):
        if isinstance(ctx.transport, HttpTransportContext):
            http_verb = ctx.transport.get_request_method()
            if http_verb == "OPTIONS":
                ctx.transport.resp_headers['allow'] = "POST, OPTIONS"
                ctx.transport.respond(HTTP_200)
                raise Fault("")
        return Soap11.create_in_document(self, ctx, charset)

# class MyApplication(Application):
#     def __init__(self, *args, **kargs):
#         Application.__init__(self, *args, **kargs)
#         # self.executor = MdxEngine('sales')
#
#     def get_session(self):
#         return self.executor


# TODO: find a solution for spyne ctx
class XmlaProviderService(ServiceBase):
    """
    The main class to activate SOAP services between xmla clients and olapy.
    """

    # IMPORTANT : all XSD and SOAP responses are written manually (not generated by Spyne lib)
    # because Spyne doesn't support encodingStyle and other namespaces required by Excel,
    # check it <http://stackoverflow.com/questions/25046837/the-encodingstyle-attribute-is-not-allowed-in-spyne>
    #
    # We have to instantiate XmlaDiscoverTools and declare variables
    # as class variable so we can access them in Discovery and Execute functions
    # this problem is related with Spyne architecture, NO CHOICE
    #
    # NOTE : some variables and functions names shouldn't respect naming convention here
    # because we need to create the xmla response (generated by spyne) with the same variable names,
    # and then, xmla requests from excel can be reached
    # thus make life easier.

    # discover_tools = XmlaDiscoverTools(None,None)
    # sessio_id = discover_tools.session_id

    # instead of initializer
    discover_tools = None
    sessio_id = None

    @rpc(
        DiscoverRequest,
        _returns=AnyXml,
        _body_style="bare",
        _out_header=Session,
        _throws=InvalidCredentialsError,
    )
    def Discover(ctx, request):
        """The first principle function of xmla protocol.

        :param request: :class:`DiscoverRequest` object

        :return: XML Discover response as string

        """
        # ctx is the 'context' parameter used by Spyne
        # (which cause problems when we want to access xmla_provider instantiation variables)
        discover_tools = XmlaProviderService.discover_tools
        ctx.out_header = Session(SessionId=str(XmlaProviderService.sessio_id))
        # config_parser = ConfigParser(discover_tools.executor.cube_path)
        config_parser = discover_tools.executor.cube_config
        if config_parser.xmla_authentication and ctx.transport.req_env['QUERY_STRING'] != 'admin':
            raise InvalidCredentialsError(
                fault_string='You do not have permission to access this resource',
                fault_object=None,
            )

        method_name = request.RequestType.lower() + '_response'
        method = getattr(discover_tools, method_name)

        if request.RequestType == "DISCOVER_DATASOURCES":
            return method()
        return method(request)

    # Execute function must take 2 argument ( JUST 2 ! ) Command and Properties
    # we encapsulate them in ExecuteRequest object
    @rpc(
        ExecuteRequest,
        _returns=AnyXml,
        _body_style="bare",
        _out_header=Session,
    )
    def Execute(ctx, request):
        """The second principle function of xmla protocol.

        :param request: :class:`ExecuteRequest` object Execute.
        :return: XML Execute response as string
        """
        ctx.out_header = Session(SessionId=str(XmlaProviderService.sessio_id))
        mdx_query = request.Command.Statement.encode().decode('utf8')
        if mdx_query == '':
            # check if command contains a query

            xml = xmlwitch.Builder()
            with xml['return']:
                xml.root(xmlns="urn:schemas-microsoft-com:xml-analysis:empty")

            return str(xml)

        else:
            XmlaProviderService.discover_tools.change_catalogue(
                request.Properties.PropertyList.Catalog,)

            xml = xmlwitch.Builder()
            executor = XmlaProviderService.discover_tools.executor
            # todo back and check this
            executor.mdx_query = mdx_query

            # Hierarchize
            if all(key in mdx_query
                   for key in
                   ['WITH MEMBER', 'strtomember', '[Measures].[XL_SD0]']):
                convert2formulas = True
            else:
                convert2formulas = False

            xmla_tools = XmlaExecuteTools(executor, convert2formulas)

            with xml['return']:
                with xml.root(
                        xmlns="urn:schemas-microsoft-com:xml-analysis:mddataset",
                        **{
                            'xmlns:xsd': 'http://www.w3.org/2001/XMLSchema',
                            'xmlns:xsi':
                            'http://www.w3.org/2001/XMLSchema-instance',
                        }):
                    xml.write(execute_xsd)
                    with xml.OlapInfo:
                        with xml.CubeInfo:
                            with xml.Cube:
                                xml.CubeName('Sales')
                                xml.LastDataUpdate(
                                    datetime.now().strftime(
                                        '%Y-%m-%dT%H:%M:%S',),
                                    xmlns="http://schemas.microsoft.com/analysisservices/2003/engine",
                                )
                                xml.LastSchemaUpdate(
                                    datetime.now().strftime(
                                        '%Y-%m-%dT%H:%M:%S',),
                                    xmlns="http://schemas.microsoft.com/analysisservices/2003/engine",
                                )
                        xml.write(xmla_tools.generate_cell_info())
                        with xml.AxesInfo:
                            xml.write(xmla_tools.generate_axes_info())
                            xml.write(xmla_tools.generate_axes_info_slicer())

                    with xml.Axes:
                        xml.write(xmla_tools.generate_xs0())
                        xml.write(xmla_tools.generate_slicer_axis())

                    with xml.CellData:
                        xml.write(xmla_tools.generate_cell_data())
            return str(xml)


home_directory = expanduser("~")
conf_file = os.path.join(home_directory, 'olapy-data', 'logs', 'xmla.log')


def get_wsgi_application(olapy_data, source_type):
    # [XmlaProviderService()], __name__ error ???
    # to refresh mdxengine with their class data

    # MdxEngine.olapy_data_location = olapy_data
    # if source_type is not None:
    #     MdxEngine.source_type = source_type

    # todo pass here mdx_eng params
    XmlaProviderService.discover_tools = XmlaDiscoverTools(olapy_data, source_type)
    XmlaProviderService.sessio_id = XmlaProviderService.discover_tools.session_id
    application = Application(
        [XmlaProviderService],
        'urn:schemas-microsoft-com:xml-analysis',
        in_protocol=XmlaSoap11(validator='soft'),
        out_protocol=XmlaSoap11(validator='soft')
    )

    # validator='soft' or nothing, this is important because spyne doesn't
    # support encodingStyle until now !!!!

    return WsgiApplication(application)


@click.command()
@click.option('--host', '-h', default='0.0.0.0', help='Host ip address.')
@click.option('--port', '-p', default=8000, help='Host port.')
@click.option('--write_on_file', '-wf', default=True,
              help='Write logs into a file or display them into the console. (True : on file)(False : on console)', )
@click.option('--log_file_path', '-lf', default=conf_file, help='Log file path. DEFAUL : ' + conf_file)
@click.option('--sql_alchemy_uri', '-sa', default=None, help="SQL Alchemy URI , **DON'T PUT THE DATABASE NAME** ")
@click.option('--olapy_data', '-od', default=None, help="Olapy Data folder location, Default : ~/olapy-data")
@click.option('--source_type', '-st', default=None, help="Get cubes from where ( db | csv ), DEFAULT : csv")
def runserver(host, port, write_on_file, log_file_path, sql_alchemy_uri, olapy_data, source_type):
    """
    Start the xmla server.
    """

    if sql_alchemy_uri is not None:
        # Example: olapy start_server -wf=True -sa='postgresql+psycopg2://postgres:root@localhost:5432'
        os.environ['SQLALCHEMY_DATABASE_URI'] = sql_alchemy_uri

    try:
        imp.reload(sys)
        # reload(sys)  # Reload is a hack
        sys.setdefaultencoding('UTF8')
    except Exception:
        pass

    wsgi_application = get_wsgi_application(olapy_data, source_type)

    # log to the console
    # logging.basicConfig(level=logging.DEBUG")
    # log to the file
    if write_on_file:
        if not os.path.isdir(
                os.path.join(home_directory, 'olapy-data', 'logs'),):
            os.makedirs(os.path.join(home_directory, 'olapy-data', 'logs'))
        logging.basicConfig(level=logging.DEBUG, filename=log_file_path)
    else:
        logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('spyne.protocol.xml').setLevel(logging.DEBUG)
    logging.info("listening to http://127.0.0.1:8000/xmla")
    logging.info("wsdl is at: http://localhost:8000/xmla?wsdl")
    server = make_server(host, port, wsgi_application)
    server.serve_forever()
