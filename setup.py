#!/usr/bin/env python

# Copyright 2013 Lionheart Software LLC
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

metadata = {}
metadata_file = "django_pyodbc/metadata.py"
exec(compile(open(metadata_file).read(), metadata_file, 'exec'), metadata)

# http://pypi.python.org/pypi?:action=list_classifiers
classifiers = [
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: BSD License",
    "Natural Language :: English",
    "Operating System :: Unix",
    "Operating System :: MacOS :: MacOS X",
    "Programming Language :: Python :: 2.7",
    "Topic :: Software Development :: Libraries",
]

setup(
    name='django-pyodbc',
    long_description=long_description,
    version=metadata['__version__'],
    license=metadata['__license__'],
    maintainer=metadata['__maintainer__'],
    maintainer_email=metadata['__maintainer_email__'],
    description="Django 1.5-1.10 SQL Server backend using pyodbc.",
    url='https://github.com/lionheart/django-pyodbc',
    package_data={'': ['LICENSE', 'README.rst']},
    packages=[
        'django_pyodbc',
        'django_pyodbc.management',
        'django_pyodbc.management.commands'
    ],
    install_requires=[
        'pyodbc>=3.0.6,<4.1',
    ]
)
