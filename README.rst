django-pyodbc
=============

|version|_   |downloads|_

.. |downloads| image:: http://img.shields.io/pypi/dm/django-pyodbc.svg?style=flat
.. _downloads: https://pypi.python.org/pypi/django-pyodbc

.. |version| image:: http://img.shields.io/pypi/v/django-pyodbc.svg?style=flat
.. _version: https://pypi.python.org/pypi/django-pyodbc

django-pyodbc is a `Django <http://djangoproject.com>`_ SQL Server DB backend powered by the `pyodbc <https://github.com/mkleehammer/pyodbc>`_ library. pyodbc is a mature, viable way to access SQL Server from Python in multiple platforms and is actively maintained. It's also used by SQLAlchemy for SQL Server connections.

This is a fork of the original `django-pyodbc <https://code.google.com/p/django-pyodbc/>`_, hosted on Google Code and last updated in 2011.

Features
--------

* [x] Support for Django 1.4-1.10.
* [x] Support for SQL Server 2000, 2005, 2008, and 2012 (please let us know if you have success running this backend with another version of SQL Server)
* [x] Support for Openedge 11.6
* [x] Support for `IBM's DB2 <https://en.wikipedia.org/wiki/IBM_DB2>`_
* [x] Native Unicode support. Every string that goes in is stored as Unicode, and every string that goes out of the database is returned as Unicode. No conversion to/from intermediate encodings takes place, so things like max_length in CharField works just like expected.
* [x] Both Windows Authentication (Integrated Security) and SQL Server Authentication.
* [x] LIMIT+OFFSET and offset w/o LIMIT emulation under SQL Server 2005.
* [x] LIMIT+OFFSET under SQL Server 2000.
* [x] Django's TextField both under SQL Server 2000 and 2005.
* [x] Passes most of the tests of the Django test suite.
* [x] Compatible with SQL Server and SQL Server Native Client from Microsoft (Windows) and FreeTDS ODBC drivers (Linux).

TODO
--------
* [ ] Python 3 support. See [#47](https://github.com/lionheart/django-pyodbc/issues/47) for details.

Installation
------------

1. Install django-pyodbc.

   .. code:: python

      pip install django-pyodbc
      
2. Now you can now add a database to your settings using standard ODBC parameters.

   .. code:: python

      DATABASES = {
         'default': {
             'ENGINE': "django_pyodbc",
             'HOST': "127.0.0.1,1433",
             'USER': "mssql_user",
             'PASSWORD': "mssql_password",
             'NAME': "database_name",
             'OPTIONS': {
                 'host_is_server': True
             },
         }
      }

3. That's it! You're done.*

   \* *You may need to configure your machine and drivers to do an*
   `ODBC <https://en.wikipedia.org/wiki/Open_Database_Connectivity>`_
   *connection to your database server, if you haven't already.  For Linux this
   involves installing and*
   `configuring Unix ODBC and FreeTDS <http://www.unixodbc.org/doc/FreeTDS.html>`_ .
   *Iterate on the command line to test your*
   `pyodbc <https://mkleehammer.github.io/pyodbc/>`_ *connection like:*

   .. code:: python

       python -c 'import pyodbc; print(pyodbc.connect("DSN=foobar_mssql_data_source_name;UID=foo;PWD=bar").cursor().execute("select 1"))'

   *extended instructions* `here <https://github.com/lionheart/django-pyodbc/issues/10>`_


Configuration
-------------

The following settings control the behavior of the backend:

Standard Django settings
~~~~~~~~~~~~~~~~~~~~~~~~

``NAME`` String. Database name. Required.

``HOST`` String. SQL Server instance in ``server\instance`` or ``ip,port`` format.

``PORT`` String. SQL Server port.

``USER`` String. Database user name. If not given then MS Integrated Security
    will be used.

``PASSWORD`` String. Database user password.

``OPTIONS`` Dictionary. Current available keys:

* ``driver``

    String. ODBC Driver to use. Default is ``"SQL Server"`` on Windows and ``"FreeTDS"`` on other platforms.

* ``dsn``

    String. A named DSN can be used instead of ``HOST``.

* ``autocommit``

    Boolean. Indicates if pyodbc should direct the the ODBC driver to activate the autocommit feature. Default value is ``False``.

* ``MARS_Connection``

    Boolean. Only relevant when running on Windows and with SQL Server 2005 or later through MS *SQL Server Native client* driver (i.e. setting ``driver`` to ``"SQL Server Native Client 11.0"``). See http://msdn.microsoft.com/en-us/library/ms131686.aspx.  Default value is ``False``.

* ``host_is_server``

    Boolean. Only relevant if using the FreeTDS ODBC driver under Unix/Linux.

    By default, when using the FreeTDS ODBC driver the value specified in the ``HOST`` setting is used in a ``SERVERNAME`` ODBC connection string component instead of being used in a ``SERVER`` component; this means that this value should be the name of a *dataserver* definition present in the ``freetds.conf`` FreeTDS configuration file instead of a hostname or an IP address.

    But if this option is present and it's value is True, this special behavior is turned off.

    See http://freetds.org/userguide/dsnless.htm for more information.

* ``extra_params``

    String. Additional parameters for the ODBC connection. The format is
    ``"param=value;param=value"``.

* ``collation``

    String. Name of the collation to use when performing text field lookups against the database. For Chinese language you can set it to ``"Chinese_PRC_CI_AS"``. The default collation for the database will be used if no value is specified.

* ``encoding``

    String. Encoding used to decode data from this database. Default is 'utf-8'.

* ``driver_needs_utf8``

    Boolean. Some drivers (FreeTDS, and other ODBC drivers?) don't support Unicode yet, so SQL clauses' encoding is forced to utf-8 for those cases.

    If this option is not present, the value is guessed according to the driver set.

* ``limit_table_list``

    Boolean.  This will restrict the table list query to the dbo schema.

* ``openedge``

    Boolean.  This will trigger support for Progress Openedge
    
* ``left_sql_quote`` , ``right_sql_quote``

    String.  Specifies the string to be inserted for left and right quoting of SQL identifiers respectively.  Only set these if django-pyodbc isn't guessing the correct quoting for your system.  
    
    
OpenEdge Support
~~~~~~~~~~~~~~~~~~~~~~~~
For OpenEdge support make sure you supply both the deiver and the openedge extra options, all other parameters should work the same

Tests
-----

To run the test suite:

.. code:: bash

   python tests/runtests.py --settings=test_django_pyodbc


License
-------

This project originally started life as django-sql-server. This project was
abandoned in 2011 and was brought back to life as django-pyodbc by our team in
2013. In the process, most of the project was refactored and brought up to speed
with modern Django best practices. The work done prior to the 2013 rewrite is
licensed under BSD (3-Clause). Improvements since then are licensed under Apache
2.0. See `LICENSE <LICENSE>`_ for more details.


SemVer
------

This project implements `Semantic Versioning <http://semver.org/>`_ . 


Credits
-------

* `Aaron Aichlmayr <https://github.com/waterfoul>`_
* `Adam Vandenber <javascript:; "For code to distinguish between different Query classes when subclassing them.">`_
* `Alex Vidal <https://github.com/avidal>`_
* `Dan Loewenherz <http://dlo.me>`_
* `Filip Wasilewski <http://code.djangoproject.com/ticket/5246 "For his pioneering work, proving this was possible and profusely documenting the code with links to relevant vendor technical articles.">`_
* `Michael Manfre <https://github.com/manfre>`_
* `Michiya Takahashi <https://github.com/michiya>`_
* `Paul Tax <https://github.com/tax>`_
* `Ramiro Morales <http://djangopeople.net/ramiro/>`_
* `Wei guangjing <http://djangopeople.net/vcc/>`_
* `mamcx <http://code.djangoproject.com/ticket/5062>`_ "For the first implementation using pymssql."

From the original project README.

* All the Django core developers, especially Malcolm Tredinnick. For being an example of technical excellence and for building such an impressive community.
* The Oracle Django team (Matt Boersma, Ian Kelly) for some excellent ideas when it comes to implement a custom Django DB backend.
