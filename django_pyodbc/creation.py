import base64
import random

from django.db.backends.creation import BaseDatabaseCreation

from django_pyodbc.compat import b, md5_constructor

class DataTypesWrapper(dict):
    def __getitem__(self, item):
        if item in ('PositiveIntegerField', 'PositiveSmallIntegerField'):
            # The check name must be unique for the database. Add a random
            # component so the regresion tests don't complain about duplicate names
            fldtype = {'PositiveIntegerField': 'int', 'PositiveSmallIntegerField': 'smallint'}[item]
            rnd_hash = md5_constructor(b(str(random.random()))).hexdigest()
            unique = base64.b64encode(b(rnd_hash), b('__'))[:6]
            return '%(fldtype)s CONSTRAINT [CK_%(fldtype)s_pos_%(unique)s_%%(column)s] CHECK ([%%(column)s] >= 0)' % locals()
        return super(DataTypesWrapper, self).__getitem__(item)

class DatabaseCreation(BaseDatabaseCreation):
    # This dictionary maps Field objects to their associated MS SQL column
    # types, as strings. Column-type strings can contain format strings; they'll
    # be interpolated against the values of Field.__dict__ before being output.
    # If a column type is set to None, it won't be included in the output.
    #
    # Any format strings starting with "qn_" are quoted before being used in the
    # output (the "qn_" prefix is stripped before the lookup is performed.

    data_types = DataTypesWrapper({
        'AutoField':                    'int IDENTITY (1, 1)',
        'BigAutoField':                 'bigint IDENTITY (1, 1)',
        'BigIntegerField':              'bigint',
        'BinaryField':                  'varbinary(max)',
        'BooleanField':                 'bit',
        'CharField':                    'nvarchar(%(max_length)s)',
        'CommaSeparatedIntegerField':   'nvarchar(%(max_length)s)',
        'DateField':                    'date',
        'DateTimeField':                'datetime',
        'DateTimeOffsetField':          'datetimeoffset',
        'DecimalField':                 'decimal(%(max_digits)s, %(decimal_places)s)',
        'FileField':                    'nvarchar(%(max_length)s)',
        'FilePathField':                'nvarchar(%(max_length)s)',
        'FloatField':                   'double precision',
        'GenericIPAddressField':        'nvarchar(39)',
        'IntegerField':                 'int',
        'IPAddressField':               'nvarchar(15)',
        'LegacyDateField':              'datetime',
        'LegacyDateTimeField':          'datetime',
        'LegacyTimeField':              'time',
        'NewDateField':                 'date',
        'NewDateTimeField':             'datetime2',
        'NewTimeField':                 'time',
        'NullBooleanField':             'bit',
        'OneToOneField':                'int',
        'PositiveIntegerField':         'int CHECK ([%(column)s] >= 0)',
        'PositiveSmallIntegerField':    'smallint CHECK ([%(column)s] >= 0)',
        'SlugField':                    'nvarchar(%(max_length)s)',
        'SmallIntegerField':            'smallint',
        'TextField':                    'nvarchar(max)',
        'TimeField':                    'time',        
    })

    def _create_test_db(self, verbosity, autoclobber):
        settings_dict = self.connection.settings_dict

        if self.connection._DJANGO_VERSION >= 13:
            test_name = self._get_test_db_name()
        else:
            if settings_dict['TEST_NAME']:
                test_name = settings_dict['TEST_NAME']
            else:
                from django.db.backends.creation import TEST_DATABASE_PREFIX
                test_name = TEST_DATABASE_PREFIX + settings_dict['NAME']
        if not settings_dict['TEST_NAME']:
            settings_dict['TEST_NAME'] = test_name

        if not self.connection.test_create:
            # use the existing database instead of creating a new one
            if verbosity >= 1:
                print("Dropping tables ... ")

            self.connection.close()
            settings_dict["NAME"] = test_name
            cursor = self.connection.cursor()
            qn = self.connection.ops.quote_name
            sql = "SELECT TABLE_NAME, CONSTRAINT_NAME " \
                  "FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS " \
                  "WHERE CONSTRAINT_TYPE = 'FOREIGN KEY'"
            for row in cursor.execute(sql).fetchall():
                objs = (qn(row[0]), qn(row[1]))
                cursor.execute("ALTER TABLE %s DROP CONSTRAINT %s" % objs)
            for table in self.connection.introspection.get_table_list(cursor):
                if verbosity >= 1:
                    print("Dropping table %s" % table)
                cursor.execute('DROP TABLE %s' % qn(table))
            self.connection.connection.commit()
            return test_name

        if self.connection.ops.on_azure_sql_db:
            self.connection.close()
            settings_dict["NAME"] = 'master'
        return super(DatabaseCreation, self)._create_test_db(verbosity, autoclobber)

    def _destroy_test_db(self, test_database_name, verbosity):
        "Internal implementation - remove the test db tables."
        if self.connection.test_create:
            if self.connection.ops.on_azure_sql_db:
                self.connection.close()
                self.connection.settings_dict["NAME"] = 'master'

            cursor = self.connection.cursor()
            self.connection.connection.autocommit = True
            #time.sleep(1) # To avoid "database is being accessed by other users" errors.
            if not self.connection.ops.on_azure_sql_db:
                cursor.execute("ALTER DATABASE %s SET SINGLE_USER WITH ROLLBACK IMMEDIATE " % \
                        self.connection.ops.quote_name(test_database_name))
            cursor.execute("DROP DATABASE %s" % \
                    self.connection.ops.quote_name(test_database_name))
        else:
            if verbosity >= 1:
                test_db_repr = ''
                if verbosity >= 2:
                    test_db_repr = " ('%s')" % test_database_name
                print("The database is left undestroyed%s." % test_db_repr)

        self.connection.close()

    def _prepare_for_test_db_ddl(self):
        self.connection.connection.rollback()
        self.connection.connection.autocommit = True

    def _rollback_works(self):
        # keep it compatible with Django 1.2
        return self.connection.features.supports_transactions

    def sql_table_creation_suffix(self):
        suffix = []
        if self.connection.settings_dict['TEST_COLLATION']:
            suffix.append('COLLATE %s' % self.connection.settings_dict['TEST_COLLATION'])
        return ' '.join(suffix)
