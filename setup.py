#!/usr/bin/env python

import os
from django_pyodbc import metadata

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name='django-pyodbc',
    version=metadata.__version__,
    license=metadata.__license__,
    maintainer=metadata.__maintainer__,
    maintainer_email=metadata.__maintainer_email__,
    description="Django 1.5 SQL Server backend using pyodbc.",
    url='https://github.com/aurorasoftware/django-pyodbc',
    packages=[
        'django_pyodbc',
        'django_pyodbc.management',
        'django_pyodbc.management.commands'
    ],
    install_requires=[
        'pyodbc>=3.0.6,<3.1',
    ]
)
