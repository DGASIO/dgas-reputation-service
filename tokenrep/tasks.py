import asyncio
import asyncpg
import aiohttp
import json
import time
import os
import logging

from ethutils import private_key_to_address
from dgasio.request import sign_request
from tokenservices.handlers import (
    TOKEN_TIMESTAMP_HEADER,
    TOKEN_SIGNATURE_HEADER,
    TOKEN_ID_ADDRESS_HEADER)

log = logging.getLogger('worker.log')

async def _update_user_reputation(database_config, push_url, signing_key, reviewee_address):
    con = await asyncpg.connect(**database_config)
    row = await con.fetchrow(
        "SELECT AVG(score), COUNT(score) FROM reviews WHERE reviewee_address = $1",
        reviewee_address)

    if row['count'] == 0:
        count = 0
        avg = None
    else:
        count = row['count']
        avg = row['avg']
        avg = round(avg * 10) / 10

    path = '/' + push_url.split('/', 3)[-1]
    method = 'POST'
    body = json.dumps({
        "address": reviewee_address,
        "count": count,
        "score": avg
    })

    address = private_key_to_address(signing_key)

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
                        log.error("User Address: {}".format(reviewee_address))
                    retries -= 1
                    if retries <= 0:
                        terminate = True
            await asyncio.sleep(backoff)
            backoff = min(backoff + 5, 30)

    return

def update_user_reputation(push_url, signing_key, reviewee_address):
    loop = asyncio.get_event_loop()
    database_config = {'dsn': os.environ['DATABASE_URL']}
    loop.run_until_complete(_update_user_reputation(database_config, push_url, signing_key, reviewee_address))
