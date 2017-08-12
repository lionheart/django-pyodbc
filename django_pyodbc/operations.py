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

import datetime
import decimal
import time
try:
    import pytz
except:
    pytz = None

from django.conf import settings
try:
    from django.db.backends.base.operations import BaseDatabaseOperations
except ImportError:
    # import location prior to Django 1.8
    from django.db.backends import BaseDatabaseOperations


from django_pyodbc.compat import smart_text, string_types, timezone

EDITION_AZURE_SQL_DB = 5

class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = "django_pyodbc.compiler"
    def __init__(self, connection):
        if connection._DJANGO_VERSION >= 14:
            super(DatabaseOperations, self).__init__(connection)
        else:
            super(DatabaseOperations, self).__init__()

        self.connection = connection
        self._ss_ver = None
        self._ss_edition = None
        self._is_db2 = None
        self._is_openedge = None
        self._left_sql_quote = None
        self._right_sql_quote = None

    @property
    def is_db2(self):
        if self._is_db2 is None:
            cur = self.connection.cursor()
            try:
                cur.execute("SELECT * FROM SYSIBM.COLUMNS FETCH FIRST 1 ROWS ONLY")
                self._is_db2 = True
            except Exception:
                self._is_db2 = False

        return self._is_db2

    @property
    def is_openedge(self):
        if self._is_openedge is None:
            options = self.connection.settings_dict.get('OPTIONS', {})
            self._is_openedge = options.get('openedge', False)
        return self._is_openedge

    @property
    def left_sql_quote(self):
        if self._left_sql_quote is None:
            options = self.connection.settings_dict.get('OPTIONS', {})
            q = options.get('left_sql_quote', None)
            if q is not None:
                self._left_sql_quote = q
            elif self.is_db2:
                self._left_sql_quote = '{'
            elif self.is_openedge:
                self._left_sql_quote = '"'
            else:
                self._left_sql_quote = '['
        return self._left_sql_quote

    @property
    def right_sql_quote(self):
        if self._right_sql_quote is None:
            options = self.connection.settings_dict.get('OPTIONS', {})
            q = options.get('right_sql_quote', None)
            if q is not None:
                self._right_sql_quote = q
            elif self.is_db2: 
                self._right_sql_quote = '}'
            elif self.is_openedge:
                self._right_sql_quote = '"'
            else:
                self._right_sql_quote = ']'
        return self._right_sql_quote

    def _get_sql_server_ver(self):
        """
        Returns the version of the SQL Server in use:
        """
        if self._ss_ver is not None:
            return self._ss_ver
        cur = self.connection.cursor()
        ver_code = None
        if not self.is_db2 and not self.is_openedge:
            cur.execute("SELECT CAST(SERVERPROPERTY('ProductVersion') as varchar)")
            ver_code = cur.fetchone()[0]
            ver_code = int(ver_code.split('.')[0])
        else:
            ver_code = 0
        if ver_code >= 11:
            self._ss_ver = 2012
        elif ver_code == 10:
            self._ss_ver = 2008
        elif ver_code == 9:
            self._ss_ver = 2005
        else:
            self._ss_ver = 2000
        return self._ss_ver
    sql_server_ver = property(_get_sql_server_ver)

    def _on_azure_sql_db(self):
        if self._ss_edition is not None:
            return self._ss_edition == EDITION_AZURE_SQL_DB
        cur = self.connection.cursor()
        cur.execute("SELECT CAST(SERVERPROPERTY('EngineEdition') as integer)")
        self._ss_edition = cur.fetchone()[0]
        return self._ss_edition == EDITION_AZURE_SQL_DB
    on_azure_sql_db = property(_on_azure_sql_db)

    def date_extract_sql(self, lookup_type, field_name):
        """
        Given a lookup_type of 'year', 'month', 'day' or 'week_day', returns
        the SQL that extracts a value from the given date field field_name.
        """
        if lookup_type == 'week_day':
            return "DATEPART(dw, %s)" % field_name
        else:
            return "DATEPART(%s, %s)" % (lookup_type, field_name)

    def date_trunc_sql(self, lookup_type, field_name):
        return "DATEADD(%s, DATEDIFF(%s, 0, %s), 0)" % (lookup_type, lookup_type, field_name)

    def _switch_tz_offset_sql(self, field_name, tzname):
        """
        Returns the SQL that will convert field_name to UTC from tzname.
        """
        field_name = self.quote_name(field_name)
        if settings.USE_TZ:
            if pytz is None:
                from django.core.exceptions import ImproperlyConfigured
                raise ImproperlyConfigured("This query requires pytz, "
                                           "but it isn't installed.")
            tz = pytz.timezone(tzname)
            td = tz.utcoffset(datetime.datetime(2000, 1, 1))

            def total_seconds(td):
                if hasattr(td, 'total_seconds'):
                    return td.total_seconds()
                else:
                    return td.days * 24 * 60 * 60 + td.seconds

            total_minutes = total_seconds(td) // 60
            hours, minutes = divmod(total_minutes, 60)
            tzoffset = "%+03d:%02d" % (hours, minutes)
            field_name = "CAST(SWITCHOFFSET(TODATETIMEOFFSET(%s, '+00:00'), '%s') AS DATETIME2)" % (field_name, tzoffset)
        return field_name

    def datetime_trunc_sql(self, lookup_type, field_name, tzname):
        """
        Given a lookup_type of 'year', 'month', 'day', 'hour', 'minute' or
        'second', returns the SQL that truncates the given datetime field
        field_name to a datetime object with only the given specificity, and
        a tuple of parameters.
        """
        field_name = self._switch_tz_offset_sql(field_name, tzname)
        reference_date = '0' # 1900-01-01
        if lookup_type in ['minute', 'second']:
            # Prevent DATEDIFF overflow by using the first day of the year as
            # the reference point. Only using for minute and second to avoid any
            # potential performance hit for queries against very large datasets.
            reference_date = "CONVERT(datetime2, CONVERT(char(4), {field_name}, 112) + '0101', 112)".format(
                field_name=field_name,
            )
        sql = "DATEADD({lookup}, DATEDIFF({lookup}, {reference_date}, {field_name}), {reference_date})".format(
            lookup=lookup_type,
            field_name=field_name,
            reference_date=reference_date,
        )
        return sql, []

    def field_cast_sql(self, db_type, internal_type=None):
        """
        Given a column type (e.g. 'BLOB', 'VARCHAR'), returns the SQL necessary
        to cast it before using it in a WHERE statement. Note that the
        resulting string should contain a '%s' placeholder for the column being
        searched against.

        TODO: verify that db_type and internal_type do not affect T-SQL CAST statement
        """
        if self.sql_server_ver < 2005 and db_type and db_type.lower() == 'ntext':
            return 'CAST(%s as nvarchar)'
        return '%s'

    def fulltext_search_sql(self, field_name):
        """
        Returns the SQL WHERE clause to use in order to perform a full-text
        search of the given field_name. Note that the resulting string should
        contain a '%s' placeholder for the value being searched against.
        """
        return 'CONTAINS(%s, %%s)' % field_name

    def last_insert_id(self, cursor, table_name, pk_name):
        """
        Given a cursor object that has just performed an INSERT statement into
        a table that has an auto-incrementing ID, returns the newly created ID.

        This method also receives the table name and the name of the primary-key
        column.
        """
        # TODO: Check how the `last_insert_id` is being used in the upper layers
        #       in context of multithreaded access, compare with other backends

        # IDENT_CURRENT:  http://msdn2.microsoft.com/en-us/library/ms175098.aspx
        # SCOPE_IDENTITY: http://msdn2.microsoft.com/en-us/library/ms190315.aspx
        # @@IDENTITY:     http://msdn2.microsoft.com/en-us/library/ms187342.aspx

        # IDENT_CURRENT is not limited by scope and session; it is limited to
        # a specified table. IDENT_CURRENT returns the value generated for
        # a specific table in any session and any scope.
        # SCOPE_IDENTITY and @@IDENTITY return the last identity values that
        # are generated in any table in the current session. However,
        # SCOPE_IDENTITY returns values inserted only within the current scope;
        # @@IDENTITY is not limited to a specific scope.

        table_name = self.quote_name(table_name)
        cursor.execute("SELECT CAST(IDENT_CURRENT(%s) as bigint)", [table_name])
        return cursor.fetchone()[0]

    def fetch_returned_insert_id(self, cursor):
        """
        Given a cursor object that has just performed an INSERT/OUTPUT statement
        into a table that has an auto-incrementing ID, returns the newly created
        ID.
        """
        return cursor.fetchone()[0]

    def lookup_cast(self, lookup_type, internal_type=None):
        if lookup_type in ('iexact', 'icontains', 'istartswith', 'iendswith'):
            return "UPPER(%s)"
        return "%s"

    def max_name_length(self):
        return 128

    def quote_name(self, name):
        """
        Returns a quoted version of the given table, index or column name. Does
        not quote the given name if it's already been quoted.
        """
        if name.startswith(self.left_sql_quote) and name.endswith(self.right_sql_quote):
            return name # Quoting once is enough.
        return '%s%s%s' % (self.left_sql_quote, name, self.right_sql_quote)

    def random_function_sql(self):
        """
        Returns a SQL expression that returns a random value.
        """
        return "RAND()"

    def last_executed_query(self, cursor, sql, params):
        """
        Returns a string of the query last executed by the given cursor, with
        placeholders replaced with actual values.

        `sql` is the raw query containing placeholders, and `params` is the
        sequence of parameters. These are used by default, but this method
        exists for database backends to provide a better implementation
        according to their own quoting schemes.
        """
        return super(DatabaseOperations, self).last_executed_query(cursor, cursor.last_sql, cursor.last_params)

    def savepoint_create_sql(self, sid):
       """
       Returns the SQL for starting a new savepoint. Only required if the
       "uses_savepoints" feature is True. The "sid" parameter is a string
       for the savepoint id.
       """
       return "SAVE TRANSACTION %s" % sid

    def savepoint_commit_sql(self, sid):
       """
       Returns the SQL for committing the given savepoint.
       """
       return "COMMIT TRANSACTION %s" % sid

    def savepoint_rollback_sql(self, sid):
       """
       Returns the SQL for rolling back the given savepoint.
       """
       return "ROLLBACK TRANSACTION %s" % sid

    def sql_flush(self, style, tables, sequences, allow_cascade=False):
        """
        Returns a list of SQL statements required to remove all data from
        the given database tables (without actually removing the tables
        themselves).

        The `style` argument is a Style object as returned by either
        color_style() or no_style() in django.core.management.color.
        """
        if tables:
            # Cannot use TRUNCATE on tables that are referenced by a FOREIGN KEY
            # So must use the much slower DELETE
            from django.db import connections
            cursor = connections[self.connection.alias].cursor()
            # Try to minimize the risks of the braindeaded inconsistency in
            # DBCC CHEKIDENT(table, RESEED, n) behavior.
            seqs = []
            for seq in sequences:
                cursor.execute("SELECT COUNT(*) FROM %s" % self.quote_name(seq["table"]))
                rowcnt = cursor.fetchone()[0]
                elem = {}
                if rowcnt:
                    elem['start_id'] = 0
                else:
                    elem['start_id'] = 1
                elem.update(seq)
                seqs.append(elem)
            cursor.execute("SELECT TABLE_NAME, CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS WHERE CONSTRAINT_TYPE not in ('PRIMARY KEY','UNIQUE')")
            fks = cursor.fetchall()
            sql_list = ['ALTER TABLE %s NOCHECK CONSTRAINT %s;' % \
                    (self.quote_name(fk[0]), self.quote_name(fk[1])) for fk in fks]
            sql_list.extend(['%s %s %s;' % (style.SQL_KEYWORD('DELETE'), style.SQL_KEYWORD('FROM'),
                             style.SQL_FIELD(self.quote_name(table)) ) for table in tables])

            if self.on_azure_sql_db:
                import warnings
                warnings.warn("The identity columns will never be reset " \
                              "on Windows Azure SQL Database.",
                              RuntimeWarning)
            else:
                # Then reset the counters on each table.
                sql_list.extend(['%s %s (%s, %s, %s) %s %s;' % (
                    style.SQL_KEYWORD('DBCC'),
                    style.SQL_KEYWORD('CHECKIDENT'),
                    style.SQL_FIELD(self.quote_name(seq["table"])),
                    style.SQL_KEYWORD('RESEED'),
                    style.SQL_FIELD('%d' % seq['start_id']),
                    style.SQL_KEYWORD('WITH'),
                    style.SQL_KEYWORD('NO_INFOMSGS'),
                    ) for seq in seqs])

            sql_list.extend(['ALTER TABLE %s CHECK CONSTRAINT %s;' % \
                    (self.quote_name(fk[0]), self.quote_name(fk[1])) for fk in fks])
            return sql_list
        else:
            return []

    #def sequence_reset_sql(self, style, model_list):
    #    """
    #    Returns a list of the SQL statements required to reset sequences for
    #    the given models.
    #
    #    The `style` argument is a Style object as returned by either
    #    color_style() or no_style() in django.core.management.color.
    #    """
    #    from django.db import models
    #    output = []
    #    for model in model_list:
    #        for f in model._meta.local_fields:
    #            if isinstance(f, models.AutoField):
    #                output.append(...)
    #                break # Only one AutoField is allowed per model, so don't bother continuing.
    #        for f in model._meta.many_to_many:
    #            output.append(...)
    #    return output

    def start_transaction_sql(self):
        """
        Returns the SQL statement required to start a transaction.
        """
        return "BEGIN TRANSACTION"

    def sql_for_tablespace(self, tablespace, inline=False):
        """
        Returns the SQL that will be appended to tables or rows to define
        a tablespace. Returns '' if the backend doesn't use tablespaces.
        """
        return "ON %s" % self.quote_name(tablespace)

    def prep_for_like_query(self, x):
        """Prepares a value for use in a LIKE query."""
        # http://msdn2.microsoft.com/en-us/library/ms179859.aspx
        return smart_text(x).replace('\\', '\\\\').replace('[', '[[]').replace('%', '[%]').replace('_', '[_]')

    def prep_for_iexact_query(self, x):
        """
        Same as prep_for_like_query(), but called for "iexact" matches, which
        need not necessarily be implemented using "LIKE" in the backend.
        """
        return x

    def value_to_db_datetime(self, value):
        """
        Transform a datetime value to an object compatible with what is expected
        by the backend driver for datetime columns.
        """
        if value is None:
            return None
        if self.connection._DJANGO_VERSION >= 14 and settings.USE_TZ:
            if timezone.is_aware(value):
                # pyodbc donesn't support datetimeoffset
                value = value.astimezone(timezone.utc)
        if not self.connection.features.supports_microsecond_precision:
            value = value.replace(microsecond=0)
        return value

    def value_to_db_time(self, value):
        """
        Transform a time value to an object compatible with what is expected
        by the backend driver for time columns.
        """
        if value is None:
            return None
        # SQL Server doesn't support microseconds
        if isinstance(value, string_types):
            return datetime.datetime(*(time.strptime(value, '%H:%M:%S')[:6]))
        return datetime.datetime(1900, 1, 1, value.hour, value.minute, value.second)

    def year_lookup_bounds(self, value):
        """
        Returns a two-elements list with the lower and upper bound to be used
        with a BETWEEN operator to query a field value using a year lookup

        `value` is an int, containing the looked-up year.
        """
        first = '%s-01-01 00:00:00'
        # SQL Server doesn't support microseconds
        last = '%s-12-31 23:59:59'
        return [first % value, last % value]

    def value_to_db_decimal(self, value, max_digits, decimal_places):
        """
        Transform a decimal.Decimal value to an object compatible with what is
        expected by the backend driver for decimal (numeric) columns.
        """
        if value is None:
            return None
        if isinstance(value, decimal.Decimal):
            context = decimal.getcontext().copy()
            context.prec = max_digits
            #context.rounding = ROUND_FLOOR
            return "%.*f" % (decimal_places + 1, value.quantize(decimal.Decimal(".1") ** decimal_places, context=context))
        else:
            return "%.*f" % (decimal_places + 1, value)

    def convert_values(self, value, field):
        """
        Coerce the value returned by the database backend into a consistent
        type that is compatible with the field type.

        In our case, cater for the fact that SQL Server < 2008 has no
        separate Date and Time data types.
        TODO: See how we'll handle this for SQL Server >= 2008
        """
        if value is None:
            return None
        if field and field.get_internal_type() == 'DateTimeField':
            return value
        elif field and field.get_internal_type() == 'DateField' and isinstance(value, datetime.datetime):
            value = value.date() # extract date
        elif field and field.get_internal_type() == 'TimeField' or (isinstance(value, datetime.datetime) and value.year == 1900 and value.month == value.day == 1):
            value = value.time() # extract time
        # Some cases (for example when select_related() is used) aren't
        # caught by the DateField case above and date fields arrive from
        # the DB as datetime instances.
        # Implement a workaround stealing the idea from the Oracle
        # backend. It's not perfect so the same warning applies (i.e. if a
        # query results in valid date+time values with the time part set
        # to midnight, this workaround can surprise us by converting them
        # to the datetime.date Python type).
        elif isinstance(value, datetime.datetime) and value.hour == value.minute == value.second == value.microsecond == 0:
            value = value.date()
        # Force floats to the correct type
        elif value is not None and field and field.get_internal_type() == 'FloatField':
            value = float(value)
        return value

    def return_insert_id(self):
        """
        MSSQL implements the RETURNING SQL standard extension differently from
        the core database backends and this function is essentially a no-op.
        The SQL is altered in the SQLInsertCompiler to add the necessary OUTPUT
        clause.
        """
        if self.connection._DJANGO_VERSION < 15:
            # This gets around inflexibility of SQLInsertCompiler's need to
            # append an SQL fragment at the end of the insert query, which also must
            # expect the full quoted table and column name.
            return ('/* %s */', '')

        # Django #19096 - As of Django 1.5, can return None, None to bypass the
        # core's SQL mangling.
        return (None, None)
