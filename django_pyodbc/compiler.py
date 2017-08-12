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

import re
from django.db.models.sql import compiler, where
import django
import types
from datetime import datetime, date
from django import VERSION as DjangoVersion

from django_pyodbc.compat import zip_longest

REV_ODIR = {
    'ASC': 'DESC',
    'DESC': 'ASC'
}

SQL_SERVER_8_LIMIT_QUERY = \
"""SELECT *
FROM (
  SELECT TOP %(limit)s *
  FROM (
    %(orig_sql)s
    ORDER BY %(ord)s
  ) AS %(table)s
  ORDER BY %(rev_ord)s
) AS %(table)s
ORDER BY %(ord)s"""

SQL_SERVER_8_NO_LIMIT_QUERY = \
"""SELECT *
FROM %(table)s
WHERE %(key)s NOT IN (
  %(orig_sql)s
  ORDER BY %(ord)s
)"""

# Strategies for handling limit+offset emulation:
USE_ROW_NUMBER = 0 # For SQL Server >= 2005
USE_TOP_HMARK = 1 # For SQL Server 2000 when both limit and offset are provided
USE_TOP_LMARK = 2 # For SQL Server 2000 when offset but no limit is provided


# Pattern to scan a column data type string and split the data type from any
# constraints or other included parts of a column definition. Based upon
# <column_definition> from http://msdn.microsoft.com/en-us/library/ms174979.aspx
_re_data_type_terminator = re.compile(
    r'\s*\b(?:' +
    r'filestream|collate|sparse|not|null|constraint|default|identity|rowguidcol' +
    r'|primary|unique|clustered|nonclustered|with|on|foreign|references|check' +
    ')',
    re.IGNORECASE,
)


_re_order_limit_offset = re.compile(
    r'(?:ORDER BY\s+(.+?))?\s*(?:LIMIT\s+(\d+))?\s*(?:OFFSET\s+(\d+))?$')

# Pattern used in column aliasing to find sub-select placeholders
_re_col_placeholder = re.compile(r'\{_placeholder_(\d+)\}')

_re_find_order_direction = re.compile(r'\s+(asc|desc)\s*$', re.IGNORECASE)

def _remove_order_limit_offset(sql):
    return _re_order_limit_offset.sub('',sql).split(None, 1)[1]

def _break(s, find):
    """Break a string s into the part before the substring to find,
    and the part including and after the substring."""
    i = s.find(find)
    return s[:i], s[i:]

def _get_order_limit_offset(sql):
    return _re_order_limit_offset.search(sql).groups()

def where_date(self, compiler, connection):
    query, data = self.as_sql(compiler, connection)
    if len(data) != 1:
        raise Error('Multiple data items in date condition') # I don't think this can happen but I'm adding an exception just in case
    if type(self.rhs) == date:
        return [query, [self.rhs]]
    elif type(self.lhs) == date:
        return [query, [self.lhs]]

class SQLCompiler(compiler.SQLCompiler):
    def __init__(self,*args,**kwargs):
        super(SQLCompiler,self).__init__(*args,**kwargs)
        # Pattern to find the quoted column name at the end of a field
        # specification
        #
        # E.g., if you're talking to MS SQL this regex would become
        #     \[([^\[]+)\]$
        #
        # This would match the underlined part of the following string:
        #   [foo_table][bar_column]
        #              ^^^^^^^^^^^^
        self._re_pat_col = re.compile(
            r"\{left_sql_quote}([^\{left_sql_quote}]+)\{right_sql_quote}$".format(
                left_sql_quote=self.connection.ops.left_sql_quote,
                right_sql_quote=self.connection.ops.right_sql_quote))

    def compile(self, node, select_format=False):
        if self.connection.ops.is_openedge and type(node) is where.WhereNode:
            for val in node.children:
                # If we too many more of these special cases we should probably move them to another file
                if type(val.rhs) == date or type(val.lhs) == date:
                    setattr(val, 'as_microsoft', types.MethodType(where_date, val))

        args = [node]
        if select_format:
            args.append(select_format)
        return super(SQLCompiler, self).compile(*args)

    def resolve_columns(self, row, fields=()):
        # If the results are sliced, the resultset will have an initial
        # "row number" column. Remove this column before the ORM sees it.
        if getattr(self, '_using_row_number', False):
            row = row[1:]
        values = []
        index_extra_select = len(self.query.extra_select)
        for value, field in zip_longest(row[index_extra_select:], fields):
            # print '\tfield=%s\tvalue=%s' % (repr(field), repr(value))
            if field:
                try:
                    value = self.connection.ops.convert_values(value, field)
                except ValueError:
                    pass
            values.append(value)
        return row[:index_extra_select] + tuple(values)

    def _fix_aggregates(self):
        """
        MSSQL doesn't match the behavior of the other backends on a few of
        the aggregate functions; different return type behavior, different
        function names, etc.

        MSSQL's implementation of AVG maintains datatype without proding. To
        match behavior of other django backends, it needs to not drop remainders.
        E.g. AVG([1, 2]) needs to yield 1.5, not 1
        """
        for alias, aggregate in self.query.aggregate_select.items():
            if not hasattr(aggregate, 'sql_function'):
                continue
            if aggregate.sql_function == 'AVG':# and self.connection.cast_avg_to_float:
                # Embed the CAST in the template on this query to
                # maintain multi-db support.
                self.query.aggregate_select[alias].sql_template = \
                    '%(function)s(CAST(%(field)s AS FLOAT))'
            # translate StdDev function names
            elif aggregate.sql_function == 'STDDEV_SAMP':
                self.query.aggregate_select[alias].sql_function = 'STDEV'
            elif aggregate.sql_function == 'STDDEV_POP':
                self.query.aggregate_select[alias].sql_function = 'STDEVP'
            # translate Variance function names
            elif aggregate.sql_function == 'VAR_SAMP':
                self.query.aggregate_select[alias].sql_function = 'VAR'
            elif aggregate.sql_function == 'VAR_POP':
                self.query.aggregate_select[alias].sql_function = 'VARP'

    def as_sql(self, with_limits=True, with_col_aliases=False):
        # Django #12192 - Don't execute any DB query when QS slicing results in limit 0
        if with_limits and self.query.low_mark == self.query.high_mark:
            return '', ()

        self._fix_aggregates()

        self._using_row_number = False

        # Get out of the way if we're not a select query or there's no limiting involved.
        check_limits = with_limits and (self.query.low_mark or self.query.high_mark is not None)
        if not check_limits:
            # The ORDER BY clause is invalid in views, inline functions,
            # derived tables, subqueries, and common table expressions,
            # unless TOP or FOR XML is also specified.
            try:
                setattr(self.query, '_mssql_ordering_not_allowed', with_col_aliases)
                result = super(SQLCompiler, self).as_sql(with_limits, with_col_aliases)
            finally:
                # remove in case query is every reused
                delattr(self.query, '_mssql_ordering_not_allowed')
            return result

        raw_sql, fields = super(SQLCompiler, self).as_sql(False, with_col_aliases)

        # Check for high mark only and replace with "TOP"
        if self.query.high_mark is not None and not self.query.low_mark:
            if self.connection.ops.is_db2:
                sql = self._select_top('', raw_sql, self.query.high_mark)
            else:
                _select = 'SELECT'
                if self.query.distinct:
                    _select += ' DISTINCT'
                sql = re.sub(r'(?i)^{0}'.format(_select), '{0} TOP {1}'.format(_select, self.query.high_mark), raw_sql, 1)
            return sql, fields

        # Else we have limits; rewrite the query using ROW_NUMBER()
        self._using_row_number = True

        # Lop off ORDER... and the initial "SELECT"
        inner_select = _remove_order_limit_offset(raw_sql)
        outer_fields, inner_select = self._alias_columns(inner_select)

        order = _get_order_limit_offset(raw_sql)[0]

        qn = self.connection.ops.quote_name
        inner_table_name = qn('AAAA')

        outer_fields, inner_select, order = self._fix_slicing_order(outer_fields, inner_select, order, inner_table_name)

        # map a copy of outer_fields for injected subselect
        f = []
        for x in outer_fields.split(','):
            i = x.upper().find(' AS ')
            if i != -1:
                x = x[i+4:]
            if x.find('.') != -1:
                tbl, col = x.rsplit('.', 1)
            else:
                col = x
            f.append('{0}.{1}'.format(inner_table_name, col.strip()))

        # inject a subselect to get around OVER requiring ORDER BY to come from FROM
        inner_select = '{fields} FROM ( SELECT {inner} ) AS {inner_as}'.format(
            fields=', '.join(f),
            inner=inner_select,
            inner_as=inner_table_name,
        )

        # IBM's DB2 cannot have a prefix of `_` for column names
        row_num_col = 'django_pyodbc_row_num' if self.connection.ops.is_db2 else '_row_num'
        where_row_num = '{0} < {row_num_col}'.format(self.query.low_mark, row_num_col=row_num_col)
        if self.query.high_mark:
            where_row_num += ' and {row_num_col} <= {0}'.format(self.query.high_mark, row_num_col=row_num_col)

        # SQL Server 2000 doesn't support the `ROW_NUMBER()` function, thus it
        # is necessary to use the `TOP` construct with `ORDER BY` so we can
        # slice out a particular range of results.
        if self.connection.ops.sql_server_ver < 2005 and not self.connection.ops.is_db2:
            num_to_select = self.query.high_mark - self.query.low_mark
            order_by_col_with_prefix,order_direction = order.rsplit(' ',1)
            order_by_col = order_by_col_with_prefix.rsplit('.',1)[-1]
            opposite_order_direction = REV_ODIR[order_direction]
            sql = r'''
                SELECT
                1, -- placeholder for _row_num
                * FROM
                (
                    SELECT TOP
                    -- num_to_select
                    {num_to_select}
                    *
                    FROM
                    (
                        SELECT TOP
                        -- high_mark
                        {high_mark}
                        -- inner
                        {inner}
                        ORDER BY (
                        -- order_by_col
                        {left_sql_quote}AAAA{right_sql_quote}.{order_by_col}
                        )
                        -- order_direction
                        {order_direction}
                    ) AS BBBB ORDER BY ({left_sql_quote}BBBB{right_sql_quote}.{order_by_col}) {opposite_order_direction}
                ) AS QQQQ ORDER BY ({left_sql_quote}QQQQ{right_sql_quote}.{order_by_col}) {order_direction}
                '''.format(
                    inner=inner_select,
                    num_to_select=num_to_select,
                    high_mark=self.query.high_mark,
                    order_by_col=order_by_col,
                    order_direction=order_direction,
                    opposite_order_direction=opposite_order_direction,
                    left_sql_quote=self.connection.ops.left_sql_quote,
                    right_sql_quote=self.connection.ops.right_sql_quote,
                )
        else:
            sql = "SELECT {row_num_col}, {outer} FROM ( SELECT ROW_NUMBER() OVER ( ORDER BY {order}) as {row_num_col}, {inner}) as QQQ where {where}".format(
                outer=outer_fields,
                order=order,
                inner=inner_select,
                where=where_row_num,
                row_num_col=row_num_col
            )


        return sql, fields

    def _select_top(self,select,inner_sql,number_to_fetch):
        if self.connection.ops.is_db2:
            return "{select} {inner_sql} FETCH FIRST {number_to_fetch} ROWS ONLY".format(
                select=select, inner_sql=inner_sql, number_to_fetch=number_to_fetch)
        else:
            return "{select} TOP {number_to_fetch} {inner_sql}".format(
                select=select, inner_sql=inner_sql, number_to_fetch=number_to_fetch)

    def _fix_slicing_order(self, outer_fields, inner_select, order, inner_table_name):
        """
        Apply any necessary fixes to the outer_fields, inner_select, and order
        strings due to slicing.
        """
        # Using ROW_NUMBER requires an ordering
        if order is None:
            meta = self.query.get_meta()
            column = meta.pk.db_column or meta.pk.get_attname()
            order = '{0}.{1} ASC'.format(
                inner_table_name,
                self.connection.ops.quote_name(column),
            )
        else:
            alias_id = 0
            # remap order for injected subselect
            new_order = []
            for x in order.split(','):
                # find the ordering direction
                m = _re_find_order_direction.search(x)
                if m:
                    direction = m.groups()[0]
                else:
                    direction = 'ASC'
                # remove the ordering direction
                x = _re_find_order_direction.sub('', x)
                # remove any namespacing or table name from the column name
                col = x.rsplit('.', 1)[-1]
                # Is the ordering column missing from the inner select?
                # 'inner_select' contains the full query without the leading 'SELECT '.
                # It's possible that this can get a false hit if the ordering
                # column is used in the WHERE while not being in the SELECT. It's
                # not worth the complexity to properly handle that edge case.
                if x not in inner_select:
                    # Ordering requires the column to be selected by the inner select
                    alias_id += 1
                    # alias column name
                    col = '{left_sql_quote}{0}___o{1}{right_sql_quote}'.format(
                        col.strip(self.connection.ops.left_sql_quote+self.connection.ops.right_sql_quote),
                        alias_id,
                        left_sql_quote=self.connection.ops.left_sql_quote,
                        right_sql_quote=self.connection.ops.right_sql_quote,
                    )
                    # add alias to inner_select
                    inner_select = '({0}) AS {1}, {2}'.format(x, col, inner_select)
                new_order.append('{0}.{1} {2}'.format(inner_table_name, col, direction))
            order = ', '.join(new_order)
        return outer_fields, inner_select, order

    def _alias_columns(self, sql):
        """Return tuple of SELECT and FROM clauses, aliasing duplicate column names."""
        qn = self.connection.ops.quote_name

        outer = list()
        inner = list()
        names_seen = list()

        # replace all parens with placeholders
        paren_depth, paren_buf = 0, ['']
        parens, i = {}, 0
        for ch in sql:
            if ch == '(':
                i += 1
                paren_depth += 1
                paren_buf.append('')
            elif ch == ')':
                paren_depth -= 1
                key = '_placeholder_{0}'.format(i)
                buf = paren_buf.pop()

                # store the expanded paren string
                buf = re.sub(r'%([^\(])', r'$$$\1', buf)
                parens[key] = buf% parens
                parens[key] = re.sub(r'\$\$\$([^\(])', r'%\1', parens[key])
                #cannot use {} because IBM's DB2 uses {} as quotes
                paren_buf[paren_depth] += '(%(' + key + ')s)'
            else:
                paren_buf[paren_depth] += ch

        def _replace_sub(col):
            """Replace all placeholders with expanded values"""
            while _re_col_placeholder.search(col):
                col = col.format(**parens)
            return col

        temp_sql = ''.join(paren_buf)

        # replace any bare %s with placeholders.  Needed when the WHERE
        # clause only contains one condition, and isn't wrapped in parens.
        # the placeholder_data is used to prevent the variable "i" from
        # being interpreted as a local variable in the replacement function
        placeholder_data = { "i": i }
        def _alias_placeholders(val):
            i = placeholder_data["i"]
            i += 1
            placeholder_data["i"] = i
            key = "_placeholder_{0}".format(i)
            parens[key] = "%s"
            return "%(" + key + ")s"

        temp_sql = re.sub("%s", _alias_placeholders, temp_sql)

        select_list, from_clause = _break(temp_sql, ' FROM ' + self.connection.ops.left_sql_quote)

        for col in [x.strip() for x in select_list.split(',')]:
            match = self._re_pat_col.search(col)
            if match:
                col_name = match.group(1)
                col_key = col_name.lower()

                if col_key in names_seen:
                    alias = qn('{0}___{1}'.format(col_name, names_seen.count(col_key)))
                    outer.append(alias)
                    inner.append('{0} as {1}'.format(_replace_sub(col), alias))
                else:
                    outer.append(qn(col_name))
                    inner.append(_replace_sub(col))

                names_seen.append(col_key)
            else:
                raise Exception('Unable to find a column name when parsing SQL: {0}'.format(col))

        return ', '.join(outer), ', '.join(inner) + (from_clause % parens)
        #                                            ^^^^^^^^^^^^^^^^^^^^^
        # We can't use `format` here, because `format` uses `{}` as special
        # characters, but those happen to also be the quoting tokens for IBM's
        # DB2


    def get_ordering(self):
        # The ORDER BY clause is invalid in views, inline functions,
        # derived tables, subqueries, and common table expressions,
        # unless TOP or FOR XML is also specified.
        if getattr(self.query, '_mssql_ordering_not_allowed', False):
            if django.VERSION[0] == 1 and django.VERSION[1] < 6:
                return (None, [])
            return (None, [], [])
        return super(SQLCompiler, self).get_ordering()



class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    # search for after table/column list
    _re_values_sub = re.compile(r'(?P<prefix>\)|\])(?P<default>\s*|\s*default\s*)values(?P<suffix>\s*|\s+\()?', re.IGNORECASE)
    # ... and insert the OUTPUT clause between it and the values list (or DEFAULT VALUES).
    _values_repl = r'\g<prefix> OUTPUT INSERTED.{col} INTO @sqlserver_ado_return_id\g<default>VALUES\g<suffix>'

    def as_sql(self, *args, **kwargs):
        # Fix for Django ticket #14019
        if not hasattr(self, 'return_id'):
            self.return_id = False

        result = super(SQLInsertCompiler, self).as_sql(*args, **kwargs)
        if isinstance(result, list):
            # Django 1.4 wraps return in list
            return [self._fix_insert(x[0], x[1]) for x in result]

        sql, params = result
        return self._fix_insert(sql, params)

    def _fix_insert(self, sql, params):
        """
        Wrap the passed SQL with IDENTITY_INSERT statements and apply
        other necessary fixes.
        """
        meta = self.query.get_meta()

        if meta.has_auto_field:
            if hasattr(self.query, 'fields'):
                # django 1.4 replaced columns with fields
                fields = self.query.fields
                auto_field = meta.auto_field
            else:
                # < django 1.4
                fields = self.query.columns
                auto_field = meta.auto_field.db_column or meta.auto_field.column

            auto_in_fields = auto_field in fields

            quoted_table = self.connection.ops.quote_name(meta.db_table)
            if not fields or (auto_in_fields and len(fields) == 1 and not params):
                # convert format when inserting only the primary key without
                # specifying a value
                sql = 'INSERT INTO {0} DEFAULT VALUES'.format(
                    quoted_table
                )
                params = []
            elif auto_in_fields:
                # wrap with identity insert
                sql = 'SET IDENTITY_INSERT {table} ON;{sql};SET IDENTITY_INSERT {table} OFF'.format(
                    table=quoted_table,
                    sql=sql,
                )

        # mangle SQL to return ID from insert
        # http://msdn.microsoft.com/en-us/library/ms177564.aspx
        if self.return_id and self.connection.features.can_return_id_from_insert:
            col = self.connection.ops.quote_name(meta.pk.db_column or meta.pk.get_attname())

            # Determine datatype for use with the table variable that will return the inserted ID
            pk_db_type = _re_data_type_terminator.split(meta.pk.db_type(self.connection))[0]

            # NOCOUNT ON to prevent additional trigger/stored proc related resultsets
            sql = 'SET NOCOUNT ON;{declare_table_var};{sql};{select_return_id}'.format(
                sql=sql,
                declare_table_var="DECLARE @sqlserver_ado_return_id table ({col_name} {pk_type})".format(
                    col_name=col,
                    pk_type=pk_db_type,
                ),
                select_return_id="SELECT * FROM @sqlserver_ado_return_id",
            )

            output = self._values_repl.format(col=col)
            sql = self._re_values_sub.sub(output, sql)

        return sql, params

class SQLInsertCompiler2(compiler.SQLInsertCompiler, SQLCompiler):

    def as_sql_legacy(self):
        # We don't need quote_name_unless_alias() here, since these are all
        # going to be column names (so we can avoid the extra overhead).
        qn = self.connection.ops.quote_name
        opts = self.query.model._meta
        returns_id = bool(self.return_id and
                          self.connection.features.can_return_id_from_insert)

        result = ['INSERT INTO %s' % qn(opts.db_table)]
        result.append('(%s)' % ', '.join([qn(c) for c in self.query.columns]))

        if returns_id:
            result.append('OUTPUT inserted.%s' % qn(opts.pk.column))

        values = [self.placeholder(*v) for v in self.query.values]
        result.append('VALUES (%s)' % ', '.join(values))

        params = self.query.params
        sql = ' '.join(result)

        meta = self.query.get_meta()
        if meta.has_auto_field:
            # db_column is None if not explicitly specified by model field
            auto_field_column = meta.auto_field.db_column or meta.auto_field.column

            if auto_field_column in self.query.columns:
                quoted_table = self.connection.ops.quote_name(meta.db_table)

                if len(self.query.columns) == 1 and not params:
                    result = ['INSERT INTO %s' % quoted_table]
                    if returns_id:
                        result.append('OUTPUT inserted.%s' % qn(opts.pk.column))
                    result.append('DEFAULT VALUES')
                    sql = ' '.join(result)
                else:
                    sql = "SET IDENTITY_INSERT %s ON;\n%s;\nSET IDENTITY_INSERT %s OFF" % \
                        (quoted_table, sql, quoted_table)

        return sql, params

    def as_sql(self):
        if self.connection._DJANGO_VERSION < 14:
            return self.as_sql_legacy()

        # We don't need quote_name_unless_alias() here, since these are all
        # going to be column names (so we can avoid the extra overhead).
        qn = self.connection.ops.quote_name
        opts = self.query.model._meta
        result = ['INSERT INTO %s' % qn(opts.db_table)]

        has_fields = bool(self.query.fields)
        fields = self.query.fields if has_fields else [opts.pk]
        columns = [f.column for f in fields]

        result.append('(%s)' % ', '.join([qn(c) for c in columns]))

        if has_fields:
            params = values = [
                [
                    f.get_db_prep_save(getattr(obj, f.attname) if self.query.raw else f.pre_save(obj, True), connection=self.connection)
                    for f in fields
                ]
                for obj in self.query.objs
            ]
        else:
            values = [[self.connection.ops.pk_default_value()] for obj in self.query.objs]
            params = [[]]
            fields = [None]

        placeholders = [
            [self.placeholder(field, v) for field, v in zip(fields, val)]
            for val in values
        ]

        if self.return_id and self.connection.features.can_return_id_from_insert:
            params = params[0]
            output = 'OUTPUT inserted.%s' % qn(opts.pk.column)
            result.append(output)
            result.append("VALUES (%s)" % ", ".join(placeholders[0]))
            return [(" ".join(result), tuple(params))]

        items = [
            (" ".join(result + ["VALUES (%s)" % ", ".join(p)]), vals)
            for p, vals in zip(placeholders, params)
        ]

        # This section deals with specifically setting the primary key,
        # or using default values if necessary
        meta = self.query.get_meta()
        if meta.has_auto_field:
            # db_column is None if not explicitly specified by model field
            auto_field_column = meta.auto_field.db_column or meta.auto_field.column
            out = []
            for sql, params in items:
                if auto_field_column in columns:
                    quoted_table = self.connection.ops.quote_name(meta.db_table)
                    # If there are no fields specified in the insert..
                    if not has_fields:
                        sql = "INSERT INTO %s DEFAULT VALUES" % quoted_table
                    else:
                        sql = "SET IDENTITY_INSERT %s ON;\n%s;\nSET IDENTITY_INSERT %s OFF" % \
                            (quoted_table, sql, quoted_table)
                out.append([sql, params])
            items = out
        return items


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):
    pass

class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):
    pass

class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    def as_sql(self, qn=None):
        self._fix_aggregates()
        return super(SQLAggregateCompiler, self).as_sql(qn=qn)

# django's compiler.SQLDateCompiler was removed in 1.8
if DjangoVersion[0] >= 1 and DjangoVersion[1] >= 8:

    import warnings

    class DeprecatedMeta(type):
        def __new__(cls, name, bases, attrs):
            # if the metaclass is defined on the current class, it's not
            # a subclass so we don't want to warn.
            if attrs.get('__metaclass__') is not cls:
                msg = ('In the 1.8 release of django, `SQLDateCompiler` was ' +
                    'removed.  This was a parent class of `' + name +
                    '`, and thus `' + name + '` needs to be changed.')
                raise ImportError(msg)
            return super(DeprecatedMeta, cls).__new__(cls, name, bases, attrs)

    class SQLDateCompiler(object):
        __metaclass__ = DeprecatedMeta

    class SQLDateTimeCompiler(object):
        __metaclass__ = DeprecatedMeta

else:
    class SQLDateCompiler(compiler.SQLDateCompiler, SQLCompiler):
        pass

    class SQLDateTimeCompiler(compiler.SQLDateCompiler, SQLCompiler):
        pass
