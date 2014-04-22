# This is an example test settings file for use with the Django test suite.
#
# The 'sqlite3' backend requires only the ENGINE setting (an in-
# memory database will be used). All other backends will require a
# NAME and potentially authentication information. See the
# following section in the docs for more information:
#
# https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/unit-tests/
#
# The different databases that Django supports behave differently in certain
# situations, so it is recommended to run the test suite against as many
# database backends as possible.  You may want to create a separate settings
# file for each of the backends you test against.
DATABASES = {
    'default': {
       'ENGINE': "django_pyodbc",
       'HOST': "10.37.129.3",
       'USER': "sa",
       'PASSWORD': "admin",
       'NAME': "defaultdb",
       'OPTIONS': {
           'host_is_server': True,
           'autocommit': True,
       },
    },
   'other': {
       'ENGINE': "django_pyodbc",
       'HOST': "10.37.129.3",
       'USER': "sa",
       'PASSWORD': "admin",
       'NAME': "otherdb",
       'OPTIONS': {
           'host_is_server': True,
           'autocommit': True,
       },
    }, 
}
SECRET_KEY = "django_tests_secret_key"

# Use a fast hasher to speed up tests.
PASSWORD_HASHERS = (
    'django.contrib.auth.hashers.MD5PasswordHasher',
)
