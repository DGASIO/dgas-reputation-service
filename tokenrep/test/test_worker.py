import asyncio
import os
import sys
from asyncpg.handlers import BaseHandler
from tornado.testing import gen_test
from rq import Queue
import redis
import subprocess

from tokenrep.app import urls
from asyncpg.test.database import requires_database
from asyncpg.test.redis import requires_redis
from tokenservices.test.base import AsyncHandlerTest
from tokenservices.handlers import RequestVerificationMixin
from ethutils import data_decoder, private_key_to_address
from asyncpg.redis import build_redis_url

TEST_PRIVATE_KEY = "0xe8f32e723decf4051aefac8e2c93c9c5b214313817cdb01a1494b917c8436b35"
TEST_ADDRESS = "0x056db290f8ba3250ca64a45d16284d04bc6f5fbf"

TEST_ADDRESS_2 = "0x056db290f8ba3250ca64a45d16284d04bc000000"

# def run_worker(conn):
#     with Connection(conn):
#         w = Worker(map(Queue, worker.listen))
#         print('working...')
#         w.work()

class TestPushHandler(RequestVerificationMixin, BaseHandler):

    def post(self):

        address = self.verify_request()
        if address != TEST_ADDRESS:
            self.set_status(401)
            return

        print(self.request.body)
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

        self._app.config['reputation'] = {
            'push_url': self.get_url("/__push"),
            'signing_key': TEST_PRIVATE_KEY
        }

        env = os.environ.copy()

        env['PYTHONPATH'] = '.'
        env['REDIS_URL'] = build_redis_url(**self._app.config['redis'])

        r = redis.from_url(env['REDIS_URL'])

        self._app.q = Queue(connection=r)

        p1 = subprocess.Popen([sys.executable, "tokenrep/worker.py"], env=env)

        await asyncio.sleep(2)

        score = 3.5
        message = "et fantastisk menneske"

        body = {
            "reviewee": TEST_ADDRESS_2,
            "score": score,
            "review": message
        }

        resp = await self.fetch_signed("/review/submit", signing_key=TEST_PRIVATE_KEY, method="POST", body=body)
        self.assertResponseCodeEqual(resp, 204)

        req = await queue.get()

        p1.terminate()
        p1.wait()
