# Copyright 2013-2017 Lionheart Software LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Copyright (c) 2008, django-pyodbc developers (see README.rst).
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#     1. Redistributions of source code must retain the above copyright notice,
#        this list of conditions and the following disclaimer.
#
#     2. Redistributions in binary form must reproduce the above copyright
#        notice, this list of conditions and the following disclaimer in the
#        documentation and/or other materials provided with the distribution.
#
#     3. Neither the name of django-sql-server nor the names of its contributors
#        may be used to endorse or promote products derived from this software
#        without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
MS SQL Server database backend for Django.
"""
import datetime
import os
import re
import sys
import warnings

from django.core.exceptions import ImproperlyConfigured

try:
    import pyodbc as Database
except ImportError:
    e = sys.exc_info()[1]
    raise ImproperlyConfigured("Error loading pyodbc module: %s" % e)

m = re.match(r'(\d+)\.(\d+)\.(\d+)(?:-beta(\d+))?', Database.version)
vlist = list(m.groups())
if vlist[3] is None: vlist[3] = '9999'
pyodbc_ver = tuple(map(int, vlist))
if pyodbc_ver < (2, 0, 38, 9999):
    raise ImproperlyConfigured("pyodbc 2.0.38 or newer is required; you have %s" % Database.version)

from django.db import utils
try:
    from django.db.backends.base.base import BaseDatabaseWrapper
    from django.db.backends.base.features import  BaseDatabaseFeatures
    from django.db.backends.base.validation import BaseDatabaseValidation
except ImportError:
    # import location prior to Django 1.8
    from django.db.backends import BaseDatabaseWrapper, BaseDatabaseFeatures, BaseDatabaseValidation
from django.db.backends.signals import connection_created

from django.conf import settings
from django import VERSION as DjangoVersion
if DjangoVersion[:2] == (1, 10):
    _DJANGO_VERSION = 19
elif DjangoVersion[:2] == (1, 9):
    _DJANGO_VERSION = 19
elif DjangoVersion[:2] == (1, 8):
    _DJANGO_VERSION = 18
elif DjangoVersion[:2] == (1, 7):
    _DJANGO_VERSION = 17
elif DjangoVersion[:2] == (1, 6):
    _DJANGO_VERSION = 16
elif DjangoVersion[:2] == (1, 5):
    _DJANGO_VERSION = 15
elif DjangoVersion[:2] == (1, 4):
    _DJANGO_VERSION = 14
elif DjangoVersion[:2] == (1, 3):
    _DJANGO_VERSION = 13
elif DjangoVersion[:2] == (1, 2):
    _DJANGO_VERSION = 12
else:
    raise ImproperlyConfigured("Django %d.%d is not supported." % DjangoVersion[:2])

from django_pyodbc.operations import DatabaseOperations
from django_pyodbc.client import DatabaseClient
from django_pyodbc.compat import binary_type, text_type, timezone
from django_pyodbc.creation import DatabaseCreation
from django_pyodbc.introspection import DatabaseIntrospection

DatabaseError = Database.Error
IntegrityError = Database.IntegrityError

class DatabaseFeatures(BaseDatabaseFeatures):
    can_use_chunked_reads = False
    can_return_id_from_insert = True
    supports_microsecond_precision = False
    supports_regex_backreferencing = False
    supports_subqueries_in_group_by = False
    supports_transactions = True
    #uses_savepoints = True
    allow_sliced_subqueries = False
    supports_paramstyle_pyformat = False

    #has_bulk_insert = False
    # DateTimeField doesn't support timezones, only DateTimeOffsetField
    supports_timezones = False
    supports_sequence_reset = False
    supports_tablespaces = True
    ignores_nulls_in_unique_constraints = False
    can_introspect_autofield = True


    def _supports_transactions(self):
        # keep it compatible with Django 1.3 and 1.4
        return self.supports_transactions

class DatabaseWrapper(BaseDatabaseWrapper):
    _DJANGO_VERSION = _DJANGO_VERSION
    drv_name = None
    driver_supports_utf8 = None
    MARS_Connection = False
    unicode_results = False
    datefirst = 7
    Database = Database
    limit_table_list = False

    # Collations:       http://msdn2.microsoft.com/en-us/library/ms184391.aspx
    #                   http://msdn2.microsoft.com/en-us/library/ms179886.aspx
    # T-SQL LIKE:       http://msdn2.microsoft.com/en-us/library/ms179859.aspx
    # Full-Text search: http://msdn2.microsoft.com/en-us/library/ms142571.aspx
    #   CONTAINS:       http://msdn2.microsoft.com/en-us/library/ms187787.aspx
    #   FREETEXT:       http://msdn2.microsoft.com/en-us/library/ms176078.aspx

    vendor = 'microsoft'
    operators = {
        # Since '=' is used not only for string comparision there is no way
        # to make it case (in)sensitive. It will simply fallback to the
        # database collation.
        'exact': '= %s',
        'iexact': "= UPPER(%s)",
        'contains': "LIKE %s ESCAPE '\\'",
        'icontains': "LIKE UPPER(%s) ESCAPE '\\'",
        'gt': '> %s',
        'gte': '>= %s',
        'lt': '< %s',
        'lte': '<= %s',
        'startswith': "LIKE %s ESCAPE '\\'",
        'endswith': "LIKE %s ESCAPE '\\'",
        'istartswith': "LIKE UPPER(%s) ESCAPE '\\'",
        'iendswith': "LIKE UPPER(%s) ESCAPE '\\'",

        # TODO: remove, keep native T-SQL LIKE wildcards support
        # or use a "compatibility layer" and replace '*' with '%'
        # and '.' with '_'
        'regex': 'LIKE %s',
        'iregex': 'LIKE %s',

        # TODO: freetext, full-text contains...
    }

    # In Django 1.8 data_types was moved from DatabaseCreation to DatabaseWrapper.
    # See https://docs.djangoproject.com/en/1.10/releases/1.8/#database-backend-api
    data_types = DatabaseCreation.data_types

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)

        options = self.settings_dict.get('OPTIONS', None)

        if options:
            self.MARS_Connection = options.get('MARS_Connection', False)
            self.datefirst = options.get('datefirst', 7)
            self.unicode_results = options.get('unicode_results', False)
            self.encoding = options.get('encoding', 'utf-8')
            self.driver_supports_utf8 = options.get('driver_supports_utf8', None)
            self.driver_needs_utf8 = options.get('driver_needs_utf8', None)
            self.limit_table_list = options.get('limit_table_list', False)

            # make lookup operators to be collation-sensitive if needed
            self.collation = options.get('collation', None)
            if self.collation:
                self.operators = dict(self.__class__.operators)
                ops = {}
                for op in self.operators:
                    sql = self.operators[op]
                    if sql.startswith('LIKE '):
                        ops[op] = '%s COLLATE %s' % (sql, self.collation)
                self.operators.update(ops)

        self.test_create = self.settings_dict.get('TEST_CREATE', True)

        if _DJANGO_VERSION >= 13:
            self.features = DatabaseFeatures(self)
        else:
            self.features = DatabaseFeatures()
        self.ops = DatabaseOperations(self)
        self.client = DatabaseClient(self)
        self.creation = DatabaseCreation(self)
        self.introspection = DatabaseIntrospection(self)
        self.validation = BaseDatabaseValidation(self)
        self.connection = None


    def get_connection_params(self):
        settings_dict = self.settings_dict
        if not settings_dict['NAME']:
            from django.core.exceptions import ImproperlyConfigured
            raise ImproperlyConfigured(
                "settings.DATABASES is improperly configured. "
                "Please supply the NAME value.")
        conn_params = {
            'database': settings_dict['NAME'],
        }
        conn_params.update(settings_dict['OPTIONS'])
        if 'autocommit' in conn_params:
            del conn_params['autocommit']
        if settings_dict['USER']:
            conn_params['user'] = settings_dict['USER']
        if settings_dict['PASSWORD']:
            conn_params['password'] = settings_dict['PASSWORD']
        if settings_dict['HOST']:
            conn_params['host'] = settings_dict['HOST']
        if settings_dict['PORT']:
            conn_params['port'] = settings_dict['PORT']
        return conn_params

    def get_new_connection(self, conn_params):
        return Database.connect(**conn_params)

    def init_connection_state(self):
        pass

    def _set_autocommit(self, autocommit):
        pass

    def _get_connection_string(self):
        settings_dict = self.settings_dict
        db_str, user_str, passwd_str, port_str = None, None, "", None
        options = settings_dict['OPTIONS']
        if settings_dict['NAME']:
            db_str = settings_dict['NAME']
        if settings_dict['HOST']:
            host_str = settings_dict['HOST']
        else:
            host_str = 'localhost'
        if settings_dict['USER']:
            user_str = settings_dict['USER']
        if settings_dict['PASSWORD']:
            passwd_str = settings_dict['PASSWORD']
        if settings_dict['PORT']:
            port_str = settings_dict['PORT']

        if not db_str:
            raise ImproperlyConfigured('You need to specify NAME in your Django settings file.')

        cstr_parts = []
        if 'driver' in options:
            driver = options['driver']
        else:
            if os.name == 'nt':
                driver = 'SQL Server'
            else:
                driver = 'FreeTDS'

        if driver == 'FreeTDS' or driver.endswith('/libtdsodbc.so'):
            driver_is_freetds = True
        else:
            driver_is_freetds = False

        # Microsoft driver names assumed here are:
        # * SQL Server
        # * SQL Native Client
        # * SQL Server Native Client 10.0/11.0
        # * ODBC Driver 11 for SQL Server
        ms_drivers = re.compile('.*SQL (Server$|(Server )?Native Client)')

        if 'dsn' in options:
            cstr_parts.append('DSN=%s' % options['dsn'])
        else:
            # Only append DRIVER if DATABASE_ODBC_DSN hasn't been set
            if os.path.isabs(driver):
                cstr_parts.append('DRIVER=%s' % driver)
            else:
                cstr_parts.append('DRIVER={%s}' % driver)

            if ms_drivers.match(driver) or driver_is_freetds and \
                    options.get('host_is_server', False):
                if port_str:
                    host_str += ';PORT=%s' % port_str
                cstr_parts.append('SERVER=%s' % host_str)
            elif self.ops.is_openedge:
                if port_str:
                    host_str += ';PortNumber=%s' % port_str
                cstr_parts.append('HostName=%s' % host_str)
            else:
                cstr_parts.append('SERVERNAME=%s' % host_str)

        if user_str:
            cstr_parts.append('UID=%s;PWD=%s' % (user_str, passwd_str))
        else:
            if ms_drivers.match(driver):
                cstr_parts.append('Trusted_Connection=yes')
            else:
                cstr_parts.append('Integrated Security=SSPI')

        cstr_parts.append('DATABASE=%s' % db_str)

        if self.MARS_Connection:
            cstr_parts.append('MARS_Connection=yes')

        if 'extra_params' in options:
            cstr_parts.append(options['extra_params'])
        connectionstring = ';'.join(cstr_parts)
        return connectionstring

    def _cursor(self):
        new_conn = False
        settings_dict = self.settings_dict


        if self.connection is None:
            new_conn = True
            connstr = self._get_connection_string()#';'.join(cstr_parts)
            options = settings_dict['OPTIONS']
            autocommit = options.get('autocommit', False)
            if self.unicode_results:
                self.connection = Database.connect(connstr, \
                        autocommit=autocommit, \
                        unicode_results='True')
            else:
                self.connection = Database.connect(connstr, \
                        autocommit=autocommit)
            connection_created.send(sender=self.__class__, connection=self)

        cursor = self.connection.cursor()
        if new_conn:
            # Set date format for the connection. Also, make sure Sunday is
            # considered the first day of the week (to be consistent with the
            # Django convention for the 'week_day' Django lookup) if the user
            # hasn't told us otherwise

            if not self.ops.is_db2 and not self.ops.is_openedge:
                # IBM's DB2 doesn't support this syntax and a suitable
                # equivalent could not be found.
                cursor.execute("SET DATEFORMAT ymd; SET DATEFIRST %s" % self.datefirst)
            if self.ops.sql_server_ver < 2005:
                self.creation.data_types['TextField'] = 'ntext'
                self.data_types['TextField'] = 'ntext'
                self.features.can_return_id_from_insert = False

            ms_sqlncli = re.compile('^((LIB)?SQLN?CLI|LIBMSODBCSQL)')
            self.drv_name = self.connection.getinfo(Database.SQL_DRIVER_NAME).upper()

            # http://msdn.microsoft.com/en-us/library/ms131686.aspx
            if self.ops.sql_server_ver >= 2005 and ms_sqlncli.match(self.drv_name) and self.MARS_Connection:
                # How to to activate it: Add 'MARS_Connection': True
                # to the DATABASE_OPTIONS dictionary setting
                self.features.can_use_chunked_reads = True

            if self.drv_name.startswith('LIBTDSODBC'):
                # FreeTDS can't execute some sql queries like CREATE DATABASE etc.
                # in multi-statement, so we need to commit the above SQL sentence(s)
                # to avoid this
                if not self.connection.autocommit:
                    self.connection.commit()

                freetds_version = self.connection.getinfo(Database.SQL_DRIVER_VER)
                if self.driver_supports_utf8 is None:
                    try:
                        from distutils.version import LooseVersion
                    except ImportError:
                        warnings.warn(Warning('Using naive FreeTDS version detection. Install distutils to get better version detection.'))
                        self.driver_supports_utf8 = not freetds_version.startswith('0.82')
                    else:
                        # This is the minimum version that properly supports
                        # Unicode. Though it started in version 0.82, the
                        # implementation in that version was buggy.
                        self.driver_supports_utf8 = LooseVersion(freetds_version) >= LooseVersion('0.91')

            elif self.driver_supports_utf8 is None:
                self.driver_supports_utf8 = (self.drv_name == 'SQLSRV32.DLL'
                                             or ms_sqlncli.match(self.drv_name))

        return CursorWrapper(cursor, self.driver_supports_utf8, self.encoding)

    def _execute_foreach(self, sql, table_names=None):
        cursor = self.cursor()
        if not table_names:
            table_names = self.introspection.get_table_list(cursor)
        for table_name in table_names:
            cursor.execute(sql % self.ops.quote_name(table_name))

    def check_constraints(self, table_names=None):
        self._execute_foreach('ALTER TABLE %s WITH CHECK CHECK CONSTRAINT ALL', table_names)

    def disable_constraint_checking(self):
        # Windows Azure SQL Database doesn't support sp_msforeachtable
        #cursor.execute('EXEC sp_msforeachtable "ALTER TABLE ? NOCHECK CONSTRAINT ALL"')
        self._execute_foreach('ALTER TABLE %s NOCHECK CONSTRAINT ALL')
        return True

    def enable_constraint_checking(self):
        # Windows Azure SQL Database doesn't support sp_msforeachtable
        #cursor.execute('EXEC sp_msforeachtable "ALTER TABLE ? WITH CHECK CHECK CONSTRAINT ALL"')
        self.check_constraints()


class CursorWrapper(object):
    """
    A wrapper around the pyodbc's cursor that takes in account a) some pyodbc
    DB-API 2.0 implementation and b) some common ODBC driver particularities.
    """
    def __init__(self, cursor, driver_supports_utf8, encoding=""):
        self.cursor = cursor
        self.driver_supports_utf8 = driver_supports_utf8
        self.last_sql = ''
        self.last_params = ()
        self.encoding = encoding

    def close(self):
        try:
            self.cursor.close()
        except Database.ProgrammingError:
            pass

    def format_sql(self, sql, n_params=None):
        if not self.driver_supports_utf8 and isinstance(sql, text_type):
            # Older FreeTDS (and other ODBC drivers?) don't support Unicode yet, so
            # we need to encode the SQL clause itself in utf-8
            sql = sql.encode('utf-8')
        # pyodbc uses '?' instead of '%s' as parameter placeholder.
        if n_params is not None:
            try:
                sql = sql % tuple('?' * n_params)
            except:
                #Todo checkout whats happening here
                pass
        else:
            if '%s' in sql:
                sql = sql.replace('%s', '?')
        if sys.version.startswith('3') and type(sql) is not str:
            sql = sql.decode(self.encoding or sys.stdout.encoding)
        return sql

    def format_params(self, params):
        fp = []
        for p in params:
            if isinstance(p, text_type):
                if not self.driver_supports_utf8:
                    # Older FreeTDS (and other ODBC drivers?) doesn't support Unicode
                    # yet, so we need to encode parameters in utf-8
                    fp.append(p.encode('utf-8'))
                else:
                    fp.append(p)
            elif isinstance(p, binary_type):
                if not self.driver_supports_utf8:
                    fp.append(p.decode(self.encoding).encode('utf-8'))
                else:
                    fp.append(p)
            elif isinstance(p, type(True)):
                if p:
                    fp.append(1)
                else:
                    fp.append(0)
            else:
                fp.append(p)
        return tuple(fp)

    def execute(self, sql, params=()):
        self.last_sql = sql
        sql = self.format_sql(sql, len(params))
        params = self.format_params(params)
        self.last_params = params
        try:
            return self.cursor.execute(sql, params)
        except IntegrityError:
            e = sys.exc_info()[1]
            raise utils.IntegrityError(*e.args)
        except DatabaseError:
            e = sys.exc_info()[1]
            raise utils.DatabaseError(*e.args)

    def executemany(self, sql, params_list):
        sql = self.format_sql(sql)
        # pyodbc's cursor.executemany() doesn't support an empty param_list
        if not params_list:
            if '?' in sql:
                return
        else:
            raw_pll = params_list
            params_list = [self.format_params(p) for p in raw_pll]

        try:
            return self.cursor.executemany(sql, params_list)
        except IntegrityError:
            e = sys.exc_info()[1]
            raise utils.IntegrityError(*e.args)
        except DatabaseError:
            e = sys.exc_info()[1]
            raise utils.DatabaseError(*e.args)

    def format_results(self, rows):
        """
        Decode data coming from the database if needed and convert rows to tuples
        (pyodbc Rows are not sliceable).
        """
        needs_utc = _DJANGO_VERSION >= 14 and settings.USE_TZ
        if not (needs_utc or not self.driver_supports_utf8):
            return tuple(rows)
        # FreeTDS (and other ODBC drivers?) don't support Unicode yet, so we
        # need to decode UTF-8 data coming from the DB
        fr = []
        for row in rows:
            if not self.driver_supports_utf8 and isinstance(row, binary_type):
                row = row.decode(self.encoding)

            elif needs_utc and isinstance(row, datetime.datetime):
                row = row.replace(tzinfo=timezone.utc)
            fr.append(row)
        return tuple(fr)

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is not None:
            return self.format_results(row)
        return []

    def fetchmany(self, chunk):
        return [self.format_results(row) for row in self.cursor.fetchmany(chunk)]

    def fetchall(self):
        return [self.format_results(row) for row in self.cursor.fetchall()]

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return self.__dict__[attr]
        return getattr(self.cursor, attr)

    def __iter__(self):
        return iter(self.cursor)


    # # MS SQL Server doesn't support explicit savepoint commits; savepoints are
    # # implicitly committed with the transaction.
    # # Ignore them.
    def savepoint_commit(self, sid):
        # if something is populating self.queries, include a fake entry to avoid
        # issues with tests that use assertNumQueries.
        if self.queries:
            self.queries.append({
                'sql': '-- RELEASE SAVEPOINT %s -- (because assertNumQueries)' % self.ops.quote_name(sid),
                'time': '0.000',
            })
