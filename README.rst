OlaPy, an experimental OLAP engine based on Pandas
==================================================

About
-----

**OlaPy** is an OLAP_ engine based on Python, which gives you a set of tools for the development of reporting and analytical
applications, multidimensional analysis, and browsing of aggregated data with MDX_ and XMLA_ support.


.. _OLAP: https://en.wikipedia.org/wiki/Online_analytical_processing
.. _MDX: https://en.wikipedia.org/wiki/MultiDimensional_eXpressions
.. _XMLA: https://en.wikipedia.org/wiki/XML_for_Analysis

`Documentation <https://olapy.readthedocs.io/en/latest/>`_

.. image:: https://raw.githubusercontent.com/abilian/olapy/master/docs/pictures/olapy.gif

Status
~~~~~~

This project is currently a research prototype, not suited for production use.


.. image:: https://static.pepy.tech/badge/olapy
   :target: https://pepy.tech/project/olapy

Licence
~~~~~~~

This project is currently licenced under the LGPL v3 licence.

Installation
------------

    git clone git@github.com:honeydew-ai/olapy.git

install poetry:

    curl -sSL https://install.python-poetry.org | python3 -

install dependencies:

    poetry install

set environment variables:

    export OLAPY_PATH=$(pwd)/olapy-data

    olapy init

Usage
-----

Run the server:

    olapy runserver

here is a configuration that works as a POC:

    olapy runserver --write_on_file false --source_type csv --cube_config_file=./olapy-data/cubes/cubes-config.yml --olapy_data=./olapy-data

Open Excel and go to Data -> From Other Sources -> From Analysis Services and use

    http://localhost:8000/xmla

as server name and click next, then you can chose one of default olapy demo cubes (sales, foodmart...) and finish.


for all the options, you can use::

    olapy runserver --help

there is also a configuration file for the server in the root of the project:

olapy-data/olapy-config.yml

It can be used to configure the connection to the database, the cubes to load, etc.