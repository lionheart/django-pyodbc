from django.db.backends import BaseDatabaseIntrospection
import pyodbc as Database

SQL_AUTOFIELD = -777555

class DatabaseIntrospection(BaseDatabaseIntrospection):
    # Map type codes to Django Field types.
    data_types_reverse = {
        SQL_AUTOFIELD:                  'IntegerField',
        Database.SQL_BIGINT:            'BigIntegerField',
        Database.SQL_BINARY:            'BinaryField',
        Database.SQL_BIT:               'NullBooleanField',
        Database.SQL_CHAR:              'CharField',
        Database.SQL_DECIMAL:           'DecimalField',
        Database.SQL_DOUBLE:            'FloatField',
        Database.SQL_FLOAT:             'FloatField',
        Database.SQL_GUID:              'TextField',
        Database.SQL_INTEGER:           'IntegerField',
        Database.SQL_LONGVARBINARY:     'BinaryField',
        #Database.SQL_LONGVARCHAR:       ,
        Database.SQL_NUMERIC:           'DecimalField',
        Database.SQL_REAL:              'FloatField',
        Database.SQL_SMALLINT:          'SmallIntegerField',
        Database.SQL_TINYINT:           'SmallIntegerField',
        Database.SQL_TYPE_DATE:         'DateField',
        Database.SQL_TYPE_TIME:         'TimeField',
        Database.SQL_TYPE_TIMESTAMP:    'DateTimeField',
        Database.SQL_VARBINARY:         'BinaryField',
        Database.SQL_VARCHAR:           'TextField',
        Database.SQL_WCHAR:             'CharField',
        Database.SQL_WLONGVARCHAR:      'TextField',
        Database.SQL_WVARCHAR:          'TextField',
    }

    def get_table_list(self, cursor):
        """
        Returns a list of table names in the current database.
        """
        # TABLES: http://msdn2.microsoft.com/en-us/library/ms186224.aspx

        cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
        return [row[0] for row in cursor.fetchall()]

        # Or pyodbc specific:
        #return [row[2] for row in cursor.tables(tableType='TABLE')]

    def _is_auto_field(self, cursor, table_name, column_name):
        """
        Checks whether column is Identity
        """
        # COLUMNPROPERTY: http://msdn2.microsoft.com/en-us/library/ms174968.aspx

        #from django.db import connection
        #cursor.execute("SELECT COLUMNPROPERTY(OBJECT_ID(%s), %s, 'IsIdentity')",
        #                 (connection.ops.quote_name(table_name), column_name))
        cursor.execute("SELECT COLUMNPROPERTY(OBJECT_ID(%s), %s, 'IsIdentity')",
                         (self.connection.ops.quote_name(table_name), column_name))
        return cursor.fetchall()[0][0]



    def get_table_description(self, cursor, table_name, identity_check=True):
        """Returns a description of the table, with DB-API cursor.description interface.

        The 'auto_check' parameter has been added to the function argspec.
        If set to True, the function will check each of the table's fields for the
        IDENTITY property (the IDENTITY property is the MSSQL equivalent to an AutoField).

        When a field is found with an IDENTITY property, it is given a custom field number
        of SQL_AUTOFIELD, which maps to the 'AutoField' value in the DATA_TYPES_REVERSE dict.
        """

        # map pyodbc's cursor.columns to db-api cursor description
        columns = [[c[3], c[4], None, c[6], c[6], c[8], c[10]] for c in cursor.columns(table=table_name)]
        items = []
        for column in columns:
            if identity_check and self._is_auto_field(cursor, table_name, column[0]):
                column[1] = SQL_AUTOFIELD
            # The conversion from TextField to CharField below is unwise.
            #   A SQLServer db field of type "Text" is not interchangeable with a CharField, no matter how short its max_length.
            #   For example, model.objects.values(<text_field_name>).count() will fail on a sqlserver 'text' field
            if column[1] == Database.SQL_WVARCHAR and column[3] < 4000:
                column[1] = Database.SQL_WCHAR
            items.append(column)
        return items

    def _name_to_index(self, cursor, table_name):
        """
        Returns a dictionary of {field_name: field_index} for the given table.
        Indexes are 0-based.
        """
        return dict([(d[0], i) for i, d in enumerate(self.get_table_description(cursor, table_name, identity_check=False))])

    def get_relations(self, cursor, table_name):
        """
        Returns a dictionary of {field_index: (field_index_other_table, other_table)}
        representing all relationships to the given table. Indexes are 0-based.
        """
        # CONSTRAINT_COLUMN_USAGE: http://msdn2.microsoft.com/en-us/library/ms174431.aspx
        # CONSTRAINT_TABLE_USAGE:  http://msdn2.microsoft.com/en-us/library/ms179883.aspx
        # REFERENTIAL_CONSTRAINTS: http://msdn2.microsoft.com/en-us/library/ms179987.aspx
        # TABLE_CONSTRAINTS:       http://msdn2.microsoft.com/en-us/library/ms181757.aspx

        table_index = self._name_to_index(cursor, table_name)
        sql = """
SELECT e.COLUMN_NAME AS column_name,
  c.TABLE_NAME AS referenced_table_name,
  d.COLUMN_NAME AS referenced_column_name
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS a
INNER JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS AS b
  ON a.CONSTRAINT_NAME = b.CONSTRAINT_NAME
INNER JOIN INFORMATION_SCHEMA.CONSTRAINT_TABLE_USAGE AS c
  ON b.UNIQUE_CONSTRAINT_NAME = c.CONSTRAINT_NAME
INNER JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE AS d
  ON c.CONSTRAINT_NAME = d.CONSTRAINT_NAME
INNER JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE AS e
  ON a.CONSTRAINT_NAME = e.CONSTRAINT_NAME
WHERE a.TABLE_NAME = %s AND a.CONSTRAINT_TYPE = 'FOREIGN KEY'"""
        cursor.execute(sql, (table_name,))
        return dict([(table_index[item[0]], (self._name_to_index(cursor, item[1])[item[2]], item[1]))
                     for item in cursor.fetchall()])

    def get_indexes(self, cursor, table_name):
    #    Returns a dictionary of fieldname -> infodict for the given table,
    #    where each infodict is in the format:
    #        {'primary_key': boolean representing whether it's the primary key,
    #         'unique': boolean representing whether it's a unique index}
        sql = """
            select
            C.name as [column_name],
            IX.is_unique as [unique],
            IX.is_primary_key as [primary_key]
            from
            sys.tables T
            join sys.index_columns IC on IC.object_id = T.object_id
            join sys.columns C on C.object_id = T.object_id and C.column_id = IC.column_id
            join sys.indexes IX on IX.object_id = T.object_id and IX.index_id = IC.index_id
            where
            T.name = %s
            -- Omit multi-column keys
            and not exists (
                select *
                from sys.index_columns cols
                where
                    cols.object_id = T.object_id
                    and cols.index_id = IC.index_id
                    and cols.key_ordinal > 1
            )
        """
        cursor.execute(sql,[table_name])
        constraints = cursor.fetchall()
        indexes = dict()

        for column_name, unique, primary_key in constraints:
            indexes[column_name.lower()] = {"primary_key":primary_key, "unique":unique}

        return indexes

    #def get_collations_list(self, cursor):
    #    """
    #    Returns list of available collations and theirs descriptions.
    #    """
    #    # http://msdn2.microsoft.com/en-us/library/ms184391.aspx
    #    # http://msdn2.microsoft.com/en-us/library/ms179886.aspx
    #
    #    cursor.execute("SELECT name, description FROM ::fn_helpcollations()")
    #    return [tuple(row) for row in cursor.fetchall()]

    def get_key_columns(self, cursor, table_name):
        """
        Backends can override this to return a list of (column_name, referenced_table_name,
        referenced_column_name) for all key columns in given table.
        """
        source_field_dict = self._name_to_index(cursor, table_name)

        sql = """
select
    COLUMN_NAME = fk_cols.COLUMN_NAME,
    REFERENCED_TABLE_NAME = pk.TABLE_NAME,
    REFERENCED_COLUMN_NAME = pk_cols.COLUMN_NAME
from INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS ref_const
join INFORMATION_SCHEMA.TABLE_CONSTRAINTS fk
    on ref_const.CONSTRAINT_CATALOG = fk.CONSTRAINT_CATALOG
    and ref_const.CONSTRAINT_SCHEMA = fk.CONSTRAINT_SCHEMA
    and ref_const.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
    and fk.CONSTRAINT_TYPE = 'FOREIGN KEY'

join INFORMATION_SCHEMA.TABLE_CONSTRAINTS pk
    on ref_const.UNIQUE_CONSTRAINT_CATALOG = pk.CONSTRAINT_CATALOG
    and ref_const.UNIQUE_CONSTRAINT_SCHEMA = pk.CONSTRAINT_SCHEMA
    and ref_const.UNIQUE_CONSTRAINT_NAME = pk.CONSTRAINT_NAME
    And pk.CONSTRAINT_TYPE = 'PRIMARY KEY'

join INFORMATION_SCHEMA.KEY_COLUMN_USAGE fk_cols
    on ref_const.CONSTRAINT_NAME = fk_cols.CONSTRAINT_NAME

join INFORMATION_SCHEMA.KEY_COLUMN_USAGE pk_cols
    on pk.CONSTRAINT_NAME = pk_cols.CONSTRAINT_NAME
where
    fk.TABLE_NAME = %s"""

        cursor.execute(sql,[table_name])
        relations = cursor.fetchall()

        key_columns = []
        key_columns.extend([(source_column, target_table, target_column) \
            for source_column, target_table, target_column in relations])
        return key_columns