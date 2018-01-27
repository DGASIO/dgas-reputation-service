import asyncio
import os
import sys
from dgas.handlers import BaseHandler
from tornado.testing import gen_test
from rq import Queue
import redis
import subprocess

from dgasrep.app import urls
from dgas.test.database import requires_database
from dgas.test.redis import requires_redis
from dgas.test.base import AsyncHandlerTest
from dgas.handlers import RequestVerificationMixin
from dgas.config import config

TEST_PRIVATE_KEY = "0xe8f32e723decf4051aefac8e2c93c9c5b214313817cdb01a1494b917c8436b35"
TEST_ADDRESS = "0x056db290f8ba3250ca64a45d16284d04bc6f5fbf"

TEST_ADDRESS_2 = "0x056db290f8ba3250ca64a45d16284d04bc000000"

def build_redis_url(**dsn):
    if 'unix_socket_path' in dsn and dsn['unix_socket_path'] is not None:
        if 'password' in dsn and dsn['password'] is not None:
            password = ':{}@'.format(dsn['password'])
        else:
            password = ''
        db = '?db={}'.format(dsn['db'] if 'db' in dsn and dsn['db'] is not None else 0)
        return 'unix://{}{}{}'.format(password, dsn['unix_socket_path'], db)
    elif 'url' in dsn:
        return dsn['url']
    raise NotImplementedError

def build_database_url(**dsn):
    if 'host' in dsn and dsn['host'] is not None:
        if 'user' in dsn and dsn['user'] is not None:
            username = '{}'.format(dsn['user'])
        else:
            username = ''
        if 'password' in dsn and dsn['password'] is not None:
            password = ':{}@'.format(dsn['password'])
        else:
            password = '@' if username else ''
        if 'database' not in dsn:
            raise Exception("Missing database from postgres dsn")
        if 'port' in dsn:
            port = ":{}".format(dsn['port'])
        else:
            port = ''
        return 'postgres://{}{}{}{}/{}'.format(username, password, dsn['host'], port, dsn['database'])
    elif 'url' in dsn:
        return dsn['url']
    raise NotImplementedError

class TestPushHandler(RequestVerificationMixin, BaseHandler):

    def post(self):

        address = self.verify_request()
        if address != TEST_ADDRESS:
            self.set_status(401)
            return

        self.application.test_request_queue.put_nowait(self.json)
        self.set_status(204)

class RatingsTest(AsyncHandlerTest):

    def get_urls(self):
        return urls + [("^/v1/__push/?$", TestPushHandler)]

    def get_url(self, path):
        path = "/v1{}".format(path)
        return super().get_url(path)

    @gen_test(timeout=30)
    @requires_database
    @requires_redis
    async def test_process_user_review(self):

        queue = self._app.test_request_queue = asyncio.Queue()

        config['reputation'] = {
            'push_url': self.get_url("/__push"),
            'signing_key': TEST_PRIVATE_KEY
        }
        # set multiple push urls
        self._app.rep_push_urls = [self.get_url("/__push"), self.get_url("/__push"), self.get_url("/__push")]

        env = os.environ.copy()

        env['PYTHONPATH'] = '.'
        env['REDIS_URL'] = build_redis_url(**config['redis'])
        env['DATABASE_URL'] = build_database_url(**config['database'])

        r = redis.from_url(env['REDIS_URL'])

        self._app.q = Queue(connection=r)

        p1 = subprocess.Popen([sys.executable, "dgasrep/worker.py"], env=env)

        await asyncio.sleep(2)

        score = 3.5
        message = "et fantastisk menneske"

        body = {
            "reviewee": TEST_ADDRESS_2,
            "rating": score,
            "review": message
        }

        resp = await self.fetch_signed("/review/submit", signing_key=TEST_PRIVATE_KEY, method="POST", body=body)
        self.assertResponseCodeEqual(resp, 204)

        # check that push server got updates (3x for each push url set above)
        update_request = await queue.get()
        self.assertEqual(update_request['review_count'], 1)
        self.assertEqual(update_request['average_rating'], 3.5)
        self.assertIn('reputation_score', update_request)
        await queue.get()
        await queue.get()

        p1.terminate()
        p1.wait()
