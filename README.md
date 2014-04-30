django-pyodbc
=============

django-pyodbc is a [Django](http://djangoproject.com) SQL Server DB backend powered by the [pyodbc](https://github.com/mkleehammer/pyodbc) library. pyodbc is a mature, viable way to access SQL Server from Python in multiple platforms and is actively maintained. It's also used by SQLAlchemy for SQL Server connections.

This is a fork of the original [django-pyodbc](https://code.google.com/p/django-pyodbc/), hosted on Google Code and last updated in 2011.

Features
--------

* Support for Django 1.4 and up.
* Support for SQL Server 2000, 2005, 2008, and 2012 (please let us know if you have success running this backend with another version of SQL Server)
* Native Unicode support. Every string that goes in is stored as Unicode, and every string that goes out of the database is returned as Unicode. No conversion to/from intermediate encodings takes place, so things like max_length in CharField works just like expected.
* Both Windows Authentication (Integrated Security) and SQL Server Authentication.
* LIMIT+OFFSET and offset w/o LIMIT emulation under SQL Server 2005.
* LIMIT+OFFSET under SQL Server 2000.
* Django's TextField both under SQL Server 2000 and 2005.
* Passes most of the tests of the Django test suite.
* Compatible with SQL Server and SQL Server Native Client from Microsoft (Windows) and FreeTDS ODBC drivers (Linux).

Installation
------------

1. Install django-pyodbc.

        pip install django-pyodbc

2. Now you can now add a database to your settings using standard ODBC parameters.

    ```python
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
    ```

3. That's it! You're done.

Configuration
-------------

The following settings control the behavior of the backend:

### Standard Django settings

`NAME` String. Database name. Required.

`HOST` String. SQL Server instance in `server\instance` or `ip,port` format.

`USER` String. Database user name. If not given then MS Integrated Security
    will be used.

`PASSWORD` String. Database user password.

`OPTIONS` Dictionary. Current available keys:

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


Tests
-----

To run the test suite:

```
python tests/runtests.py --settings=test_django_pyodbc
```

License
-------

See [LICENSE](LICENSE).

Credits
-------

* [Adam Vandenber](javascript:; "For code to distinguish between different Query classes when subclassing them.")
* [Alex Vidal](https://github.com/avidal)
* [Dan Loewenherz](http://dlo.me)
* [Filip Wasilewski](http://code.djangoproject.com/ticket/5246 "For his pioneering work, proving this was possible and profusely documenting the code with links to relevant vendor technical articles.")
* [Michael Manfre](https://github.com/manfre)
* [Michiya Takahashi](https://github.com/michiya)
* [Paul Tax](https://github.com/tax)
* [Ramiro Morales](http://djangopeople.net/ramiro/)
* [Wei guangjing](http://djangopeople.net/vcc/)
* [mamcx](http://code.djangoproject.com/ticket/5062 "For the first implementation using pymssql.")

From the original project README.

* All the Django core developers, especially Malcolm Tredinnick. For being an example of technical excellence and for building such an impressive community.
* The Oracle Django team (Matt Boersma, Ian Kelly) for some excellent ideas when it comes to implement a custom Django DB backend.

