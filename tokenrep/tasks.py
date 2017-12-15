import asyncio
import asyncpg
import aiohttp
import json
import time
import os
import logging

from tokenservices.ethereum.utils import private_key_to_address
from tokenservices.request import sign_request
from tokenservices.handlers import (
    TOKEN_TIMESTAMP_HEADER,
    TOKEN_SIGNATURE_HEADER,
    TOKEN_ID_ADDRESS_HEADER)

log = logging.getLogger('worker.log')

async def calculate_user_reputation(con, reviewee_id):
    row = await con.fetchrow(
        "SELECT AVG(rating), COUNT(rating) FROM reviews WHERE reviewee_id = $1",
        reviewee_id)

    if row['count'] == 0:
        count = 0
        avg = None
        stars = {
            "0": 0,
            "1": 0,
            "2": 0,
            "3": 0,
            "4": 0,
            "5": 0
        }
    else:
        count = row['count']
        avg = row['avg']
        avg = round(avg * 10) / 10

        # TODO: perhaps be smarter here (i.e. try do it in a single query)
        star0 = await con.fetchrow(
            "SELECT COUNT(rating) FROM reviews WHERE reviewee_id = $1 AND rating < 1.0",
            reviewee_id)
        star1 = await con.fetchrow(
            "SELECT COUNT(rating) FROM reviews WHERE reviewee_id = $1 AND rating >= 1.0 AND rating < 2.0",
            reviewee_id)
        star2 = await con.fetchrow(
            "SELECT COUNT(rating) FROM reviews WHERE reviewee_id = $1 AND rating >= 2.0 AND rating < 3.0",
            reviewee_id)
        star3 = await con.fetchrow(
            "SELECT COUNT(rating) FROM reviews WHERE reviewee_id = $1 AND rating >= 3.0 AND rating < 4.0",
            reviewee_id)
        star4 = await con.fetchrow(
            "SELECT COUNT(rating) FROM reviews WHERE reviewee_id = $1 AND rating >= 4.0 AND rating < 5.0",
            reviewee_id)
        star5 = await con.fetchrow(
            "SELECT COUNT(rating) FROM reviews WHERE reviewee_id = $1 AND rating >= 5.0",
            reviewee_id)

        stars = {
            "0": star0['count'],
            "1": star1['count'],
            "2": star2['count'],
            "3": star3['count'],
            "4": star4['count'],
            "5": star5['count']
        }

    return count, avg, stars

async def _update_user_reputation(database_config, push_urls, signing_key, reviewee_id):
    con = await asyncpg.connect(**database_config)
    count, avg, _ = await calculate_user_reputation(con, reviewee_id)
    await con.close()

    body = json.dumps({
        "address": reviewee_id,
        "count": count,
        "score": avg
    })

    address = private_key_to_address(signing_key)

    futs = []
    for push_url in push_urls:

        futs.append(do_push(push_url, body, address, signing_key, reviewee_id))

    await asyncio.gather(*futs)

async def do_push(push_url, body, address, signing_key, reviewee_id):

    path = '/' + push_url.split('/', 3)[-1]

    method = 'POST'
    backoff = 5
    retries = 10

    terminate = False
    async with aiohttp.ClientSession() as session:
        while not terminate:
            timestamp = int(time.time())
            signature = sign_request(signing_key, method, path, timestamp, body)

            with aiohttp.Timeout(10):
                async with session.post(push_url,
                                        headers={
                                            'content-type': 'application/json',
                                            TOKEN_SIGNATURE_HEADER: signature,
                                            TOKEN_ID_ADDRESS_HEADER: address,
                                            TOKEN_TIMESTAMP_HEADER: str(timestamp)},
                                        data=body) as response:
                    if response.status == 204 or response.status == 200:
                        terminate = True
                    else:
                        log.error("Error updating user details")
                        log.error("URL: {}".format(push_url))
                        log.error("User Address: {}".format(reviewee_id))
                    retries -= 1
                    if retries <= 0:
                        terminate = True
            await asyncio.sleep(backoff)
            backoff = min(backoff + 5, 30)

def update_user_reputation(push_url, signing_key, reviewee_id):
    loop = asyncio.get_event_loop()
    database_config = {'dsn': os.environ['DATABASE_URL']}
    loop.run_until_complete(_update_user_reputation(database_config, push_url, signing_key, reviewee_id))
