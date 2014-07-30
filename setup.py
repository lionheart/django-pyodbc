#!/usr/bin/env python

import re
import os
from django_pyodbc import metadata

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

with open(os.path.join(os.path.dirname(__file__), "README.rst")) as file:
    long_description = file.read()

    id_regex = re.compile(r"<\#([\w-]+)>")
    link_regex = re.compile(r"<(\w+)>")
    link_alternate_regex = re.compile(r"   :target: (\w+)")

    long_description = id_regex.sub(r"<https://github.com/lionheart/django-pyodbc#\1>", long_description)
    long_description = link_regex.sub(r"<https://github.com/lionheart/django-pyodbc/blob/master/\1>", long_description)
    long_description = link_regex.sub(r"<https://github.com/lionheart/django-pyodbc/blob/master/\1>", long_description)
    long_description = link_alternate_regex.sub(r"   :target: https://github.com/lionheart/django-pyodbc/blob/master/\1", long_description)

setup(
    name='django-pyodbc',
    long_description=long_description,
    version=metadata.__version__,
    license=metadata.__license__,
    maintainer=metadata.__maintainer__,
    maintainer_email=metadata.__maintainer_email__,
    description="Django 1.5 SQL Server backend using pyodbc.",
    url='https://github.com/aurorasoftware/django-pyodbc',
    package_data={'': ['LICENSE', 'README.rst']},
    packages=[
        'django_pyodbc',
        'django_pyodbc.management',
        'django_pyodbc.management.commands'
    ],
    install_requires=[
        'pyodbc>=3.0.6,<3.1',
    ]
)
