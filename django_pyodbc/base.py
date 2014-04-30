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
    import pytds as Database
except ImportError:
    e = sys.exc_info()[1]
    raise ImproperlyConfigured("Error loading pyodbc module: %s" % e)

from django.db import utils
from django.db.backends import BaseDatabaseWrapper, BaseDatabaseFeatures, BaseDatabaseValidation
from django.db.backends.signals import connection_created
from django.conf import settings
try:
    from django.utils.timezone import utc
except:
    pass
from django import VERSION as DjangoVersion
if DjangoVersion[:2] == (1, 7):
    _DJANGO_VERSION = 17
elif DjangoVersion[:2] == (1, 6):
    _DJANGO_VERSION = 16
elif DjangoVersion[:2] == (1, 5):
    _DJANGO_VERSION = 15
elif DjangoVersion[:2] == (1, 4):
    _DJANGO_VERSION = 14
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
    use_mars = False
    datefirst = 7
    Database = Database

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

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)

        options = self.settings_dict.get('OPTIONS', None)

        if options:
            self.use_mars = options.get('use_mars', False)
            self.datefirst = options.get('datefirst', 7)
            self.encoding = options.get('encoding', 'utf-8')

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

    def _cursor(self):
        new_conn = False
        settings_dict = self.settings_dict
        try:
            self.command_timeout = int(self.settings_dict.get('COMMAND_TIMEOUT', 30))
        except ValueError:
            self.command_timeout = 30

        if self.connection is None:
            new_conn = True
            options = settings_dict['OPTIONS']
            autocommit = options.get('autocommit', False)   
            self.connection = Database.connect(
                server=settings_dict['HOST'],
                database=settings_dict['NAME'],
                user=settings_dict['USER'],
                password=settings_dict['PASSWORD'],
                timeout=self.command_timeout,
                autocommit=autocommit,
                use_mars=options.get('use_mars', False),
                load_balancer=options.get('load_balancer', None),
                use_tz=utc if getattr(settings, 'USE_TZ', False) else None
            )
            connection_created.send(sender=self.__class__, connection=self)

        cursor = self.connection.cursor()
        if new_conn:
            # Set date format for the connection. Also, make sure Sunday is
            # considered the first day of the week (to be consistent with the
            # Django convention for the 'week_day' Django lookup) if the user
            # hasn't told us otherwise
            cursor.execute("SET DATEFORMAT ymd; SET DATEFIRST %s" % self.datefirst)
            if self.ops.sql_server_ver < 2005:
                self.creation.data_types['TextField'] = 'ntext'
                self.features.can_return_id_from_insert = False

            ms_sqlncli = re.compile('^((LIB)?SQLN?CLI|LIBMSODBCSQL)')

            # http://msdn.microsoft.com/en-us/library/ms131686.aspx
            if self.ops.sql_server_ver >= 2005 and self.use_mars:
                # How to to activate it: Add 'use_mars': True
                # to the DATABASE_OPTIONS dictionary setting
                self.features.can_use_chunked_reads = True

        return CursorWrapper(cursor, self.encoding)

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
    def __init__(self, cursor, encoding=""):
        self.cursor = cursor
        self.last_sql = ''
        self.last_params = ()
        self.encoding = encoding

    def format_sql(self, sql, n_params=None):
        return sql

    def format_params(self, params):
        fp = []
        for p in params:
            if isinstance(p, text_type):
                fp.append(p)
            elif isinstance(p, binary_type):
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
        #TODO: better here
        needs_utc = _DJANGO_VERSION >= 14 and settings.USE_TZ
        if not needs_utc:
            return tuple(rows)

        else:
            fr = []
            for row in rows:
                if isinstance(row, datetime.datetime):
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
