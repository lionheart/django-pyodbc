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

try:
    from django.db.backends.base.client import BaseDatabaseClient
except ImportError:
    # import location prior to Django 1.8
    from django.db.backends import BaseDatabaseClient
import os
import sys

class DatabaseClient(BaseDatabaseClient):
    if os.name == 'nt':
        executable_name = 'osql'
    else:
        executable_name = 'isql'

    def runshell(self):
        settings_dict = self.connection.settings_dict
        user = settings_dict['OPTIONS'].get('user', settings_dict['USER'])
        password = settings_dict['OPTIONS'].get('passwd', settings_dict['PASSWORD'])
        if os.name == 'nt':
            db = settings_dict['OPTIONS'].get('db', settings_dict['NAME'])
            server = settings_dict['OPTIONS'].get('host', settings_dict['HOST'])
            port = settings_dict['OPTIONS'].get('port', settings_dict['PORT'])
            defaults_file = settings_dict['OPTIONS'].get('read_default_file')

            args = [self.executable_name]
            if server:
                args += ["-S", server]
            if user:
                args += ["-U", user]
                if password:
                    args += ["-P", password]
            else:
                args += ["-E"] # Try trusted connection instead
            if db:
                args += ["-d", db]
            if defaults_file:
                args += ["-i", defaults_file]
        else:
            dsn = settings_dict['OPTIONS'].get('dsn', settings_dict.get('ODBC_DSN'))
            args = ['%s -v %s %s %s' % (self.executable_name, dsn, user, password)]

        # XXX: This works only with Python >= 2.4 because subprocess was added
        # in that release
        import subprocess
        try:
            subprocess.call(args, shell=True)
        except KeyboardInterrupt:
            pass
