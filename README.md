django-pyodbc
=============

A [Django](http://djangoproject.com) MS SQL Server external DB backend that
uses ODBC by employing the [pyodbc](http://pyodbc.sourceforge.net) library. It
supports SQL Server 2000 and 2005.

Features
--------

* Supports Django 1.4 or newer.
* Supports LIMIT+OFFSET and offset w/o LIMIT emulation under SS2005.
* Supports LIMIT+OFFSET under SS2000.
* Transparently supports Django's TextField both under SS2000 and SS2005.
* Passes most of the tests of the Django test suite.
* Compatible with SQL Server and SQL Server Native Client from Microsoft
  (Windows) and FreeTDS ODBC drivers (Linux).

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

3. That's all!

Configuration
-------------

The following settings control the behavior of the backend:

### Standard Django settings

`NAME` String. Database name. Required.

`HOST` String. SQL Server instance in `server\instance` or `ip,port` format.

`USER` String. Database user name. If not given then MS Integrated Security
    will be used.

`PASSWORD` String. Database user password.

`OPTIONS` Dictionary. Current available keys are:

    ``driver``
        String. ODBC Driver to use. Default is ``"SQL Server"`` on Windows and
        ``"FreeTDS"`` on other platforms.

    ``dsn``
        String. A named DSN can be used instead of ``HOST``.

    ``autocommit``
        Boolean. Indicates if pyodbc should direct the the ODBC driver to
        activate the autocommit feature. Default value is ``False``.

    ``MARS_Connection``
        Boolean. Only relevant when running on Windows and with SQL Server 2005
        or later through MS *SQL Server Native client* driver (i.e. setting
        ``driver`` to ``"SQL Server Native Client 11.0"``). See
        http://msdn.microsoft.com/en-us/library/ms131686.aspx.
        Default value is ``False``.

    ``host_is_server``
        Boolean. Only relevant if using the FreeTDS ODBC driver under
        Unix/Linux.

        By default, when using the FreeTDS ODBC driver the value specified in
        the ``HOST`` setting is used in a ``SERVERNAME`` ODBC
        connection string component instead of being used in a ``SERVER``
        component; this means that this value should be the name of a
        *dataserver* definition present in the ``freetds.conf`` FreeTDS
        configuration file instead of a hostname or an IP address.

        But if this option is present and it's value is True, this special
        behavior is turned off.

        See http://freetds.org/userguide/dsnless.htm for more information.

    ``extra_params``
        String. Additional parameters for the ODBC connection. The format is
        ``"param=value;param=value"``.

    ``collation``
        String. Name of the collation to use when performing text field lookups
        against the database. For Chinese language you can set it to 
        ``"Chinese_PRC_CI_AS"``. The default collation for the database
        will be used if no value is specified.

License
-------

See LICENSE.

Credits
-------

* [Alex Vidal](https://github.com/avidal)
* [Dan Loewenherz](http://dlo.me)
* [Michiya Takahashi](https://github.com/michiya)
* [Filip Wasilewski](http://code.djangoproject.com/ticket/5246)
* [Ramiro Morales](http://djangopeople.net/ramiro/)
* [Wei guangjing](http://djangopeople.net/vcc/)
* [mamcx](http://code.djangoproject.com/ticket/5062)

