import os
import random
import iso8601
from tornado.testing import gen_test
from datetime import datetime, timedelta
from tokenrep.app import urls
from asyncpg.test.database import requires_database
from tokenservices.test.base import AsyncHandlerTest
from ethutils import data_decoder, private_key_to_address
from tornado.escape import json_decode
import urllib.parse

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
    async def test_update_review(self):

        message = "et fantastisk menneske"
        reviews = [
            (TEST_ADDRESS, TEST_ADDRESS_2, random.random() * 5, message,
                 datetime.utcnow() - timedelta(seconds=30),
                 datetime.utcnow() - timedelta(seconds=30))
        ]
        reviews.extend([
            (private_key_to_address(os.urandom(32)), TEST_ADDRESS_2,
             random.random() * 5, message,
             datetime.utcnow() - timedelta(minutes=60 - i),
             datetime.utcnow() - timedelta(minutes=60 - i)) for i in range(1, 61)
        ])
        reviews.append(
            (TEST_ADDRESS, reviews[-1][0], random.random() * 5, message,
                 datetime.utcnow() - timedelta(minutes=40),
                 datetime.utcnow() - timedelta(seconds=10)))

        async with self.pool.acquire() as con:
            for rev in reviews:
                await con.execute(
                    "INSERT INTO reviews (reviewer_address, reviewee_address, rating, review, created, updated) "
                    "VALUES ($1, $2, $3, $4, $5, $6)",
                    *rev)

        resp = await self.fetch_signed("/search/review?reviewee={}".format(TEST_ADDRESS_2), signing_key=TEST_PRIVATE_KEY, method="GET")
        self.assertResponseCodeEqual(resp, 200)

        results = json_decode(resp.body)

        # make sure dates are in reverse order
        last_date = datetime.now(iso8601.UTC)
        for review in results['reviews']:
            date = iso8601.parse_date(review['date'])
            self.assertLess(date, last_date)
            last_date = date

        self.assertEqual(results['total'], len(reviews) - 1) # - 1 as one review in tests is not for this reviewee
        self.assertEqual(results['limit'], len(results['reviews']),
                         "limit value returned does not represent the number of results returned")
        self.assertEqual(results['limit'], 10,
                         "expected default value of 10 for limit")
        self.assertEqual(results['offset'], 0,
                         "expected default value of 0 for offset")

        # check offset
        offset = results['limit']
        resp = await self.fetch_signed("/search/review?reviewee={}&offset={}".format(TEST_ADDRESS_2, offset), signing_key=TEST_PRIVATE_KEY, method="GET")
        self.assertResponseCodeEqual(resp, 200)
        results = json_decode(resp.body)

        # make sure dates continue on from the last request
        for review in results['reviews']:
            date = iso8601.parse_date(review['date'])
            self.assertLess(date, last_date)
            last_date = date

        # check oldest field
        resp = await self.fetch_signed("/search/review?reviewee={}&oldest={}".format(TEST_ADDRESS_2, urllib.parse.quote(last_date.isoformat())),
                                       signing_key=TEST_PRIVATE_KEY, method="GET")
        self.assertResponseCodeEqual(resp, 200)
        results = json_decode(resp.body)

        # make sure the total reflects the query (20 being the number of results before the previous)
        self.assertEqual(results['total'], 20)

        # make sure nothing is returned when the offset is past the limit
        resp = await self.fetch_signed("/search/review?reviewee={}&oldest={}&offset=20".format(TEST_ADDRESS_2, urllib.parse.quote(last_date.isoformat())),
                                       signing_key=TEST_PRIVATE_KEY, method="GET")
        self.assertResponseCodeEqual(resp, 200)
        results = json_decode(resp.body)
        self.assertEqual(len(results['reviews']), 0)

        # check limit
        limit = 3
        resp = await self.fetch_signed("/search/review?reviewee={}&limit={}".format(TEST_ADDRESS_2, limit), signing_key=TEST_PRIVATE_KEY, method="GET")
        self.assertResponseCodeEqual(resp, 200)
        results = json_decode(resp.body)
        self.assertEqual(len(results['reviews']), limit)

        # check searching by reviewer
        resp = await self.fetch_signed("/search/review?reviewer={}".format(TEST_ADDRESS), signing_key=TEST_PRIVATE_KEY, method="GET")
        self.assertResponseCodeEqual(resp, 200)
        results = json_decode(resp.body)
        self.assertEqual(len(results['reviews']), 2)

        # check that the first review by this user is the "edited" one
        # (that is it has a newer updated date than it's created)
        self.assertEqual(reviews[-1][-1].replace(tzinfo=iso8601.UTC), iso8601.parse_date(results['reviews'][0]['date']))
        self.assertEqual(reviews[0][-1].replace(tzinfo=iso8601.UTC), iso8601.parse_date(results['reviews'][1]['date']))
        self.assertEqual(results['reviews'][0]['reviewee'], reviews[-1][1])
        self.assertEqual(results['reviews'][1]['reviewee'], reviews[0][1])

        # check searching for both reviewer and reviewee
        resp = await self.fetch_signed("/search/review?reviewer={}&reviewee={}".format(TEST_ADDRESS, TEST_ADDRESS_2), signing_key=TEST_PRIVATE_KEY, method="GET")
        self.assertResponseCodeEqual(resp, 200)
        results = json_decode(resp.body)
        self.assertEqual(len(results['reviews']), 1)

        # check that no reviewer or reviewee
        resp = await self.fetch_signed("/search/review", signing_key=TEST_PRIVATE_KEY, method="GET")
        self.assertResponseCodeEqual(resp, 400)
