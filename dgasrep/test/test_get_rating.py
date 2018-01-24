import os
from tornado.escape import json_decode
from tornado.testing import gen_test

from dgasrep.app import urls
from dgasrep.tasks import starsort
from dgas.test.database import requires_database
from dgas.test.base import AsyncHandlerTest
from dgas.ethereum.utils import data_decoder, data_encoder, private_key_to_address

TEST_PRIVATE_KEY = data_decoder("0xe8f32e723decf4051aefac8e2c93c9c5b214313817cdb01a1494b917c8436b35")
TEST_ADDRESS = "0x056db290f8ba3250ca64a45d16284d04bc6f5fbf"

TEST_ADDRESS_2 = "0x056db290f8ba3250ca64a45d16284d04bc000000"

class RatingsTest(AsyncHandlerTest):

    def get_urls(self):
        return urls

    def get_url(self, path):
        path = "/v1{}".format(path)
        return super().get_url(path)

    @gen_test
    @requires_database
    async def test_get_user_rating(self):

        message = "et fantastisk menneske"
        reviews = [
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 0, message),
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 1, message),
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 1.9, message),
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 2, message),
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 2.5, message),
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 2.9, message),
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 3, message),
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 3.1, message),
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 3.2, message),
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 3.9, message),
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2, 5, message)
        ]
        score = starsort((1, 0, 4, 3, 3))
        score = round(score * 10) / 10
        average = sum([x[2] for x in reviews]) / len(reviews)
        average = round(average * 10) / 10

        async with self.pool.acquire() as con:
            for rev in reviews:
                await con.execute(
                    "INSERT INTO reviews (reviewer_id, reviewee_id, rating, review) "
                    "VALUES ($1, $2, $3, $4)",
                    *rev)

        resp = await self.fetch("/user/{}".format(TEST_ADDRESS_2), method="GET")
        self.assertResponseCodeEqual(resp, 200)

        body = json_decode(resp.body)
        print(body)

        self.assertEqual(body['reputation_score'], score)
        self.assertEqual(body['review_count'], len(reviews))
        self.assertEqual(body['average_rating'], average)
        self.assertEqual(body['stars']["1"], 3)
        self.assertEqual(body['stars']["2"], 3)
        self.assertEqual(body['stars']["3"], 4)
        self.assertEqual(body['stars']["4"], 0)
        self.assertEqual(body['stars']["5"], 1)
