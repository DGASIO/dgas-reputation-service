import asyncio
import subprocess
import os
from functools import partial
from tokenrep import locations

def requires_geolite2_data(func=None):
    """runs the GeoLite2 import script before running the test"""
    def wrap(fn):

        async def wrapper(self, *args, **kwargs):

            if 'database' not in self._app.config:
                raise Exception("Missing @requires_database before @requires_geolite2_data")

            if 'dsn' in self._app.config['database']:
                db_url = self._app.config['database']['dsn']
            else:
                if 'user' in self._app.config['database']:
                    user = self._app.config['database']['user']
                else:
                    user = ''
                if 'password' in self._app.config['database']:
                    password = ':{}'.format(self._app.config['database']['password'])
                else:
                    password = ''
                if user or password:
                    user = '{}{}@'.format(user, password)
                if 'port' in self._app.config['database']:
                    port = ':{}'.format(self._app.config['database']['port'])
                else:
                    port = ''
                host = self._app.config['database'].get('host', '')
                db = self._app.config['database'].get('database', '')
                db_url = 'postgres://{}{}{}{}/{}'.format(user, password, host, port, db)

            env = os.environ.copy()
            env['DATABASE_URL'] = db_url
            env['USE_GEOLITE2'] = "1"

            with subprocess.Popen('./configure_environment.sh', env=env, cwd=os.path.abspath(os.curdir),
                                  shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
                print(p.stderr.read().decode('utf-8'))
                if p.returncode is not None:
                    raise Exception("Error loading GeoLite2 data: returncode = {}".format(p.returncode))

            self._app.store_location = partial(
                locations.store_review_location,
                locations.get_location_from_geolite2, self._app.connection_pool)

            f = fn(self, *args, **kwargs)
            if asyncio.iscoroutine(f):
                await f

        return wrapper

    if func is not None:
        return wrap(func)
    else:
        return wrap
