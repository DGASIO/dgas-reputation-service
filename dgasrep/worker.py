import os
import sys
import logging

import redis
from rq import Worker, Queue, Connection

#logging.basicConfig() # NOTE: this stops the rq logs from being displayed
log = logging.getLogger("worker.log")

listen = ['high', 'default', 'low']

REDIS_URL = os.getenv('REDIS_URL', None)
REDIS_UNIX_SOCKET = os.getenv('REDIS_UNIX_SOCKET', None)
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

if __name__ == '__main__':
    if 'DATABASE_URL' not in os.environ:
        log.error("ENVIRONMENT MISSING `DATABASE_URL`")
        sys.exit(1)
    if REDIS_UNIX_SOCKET:
        if REDIS_PASSWORD:
            url = 'unix://:{}@{}?db={}'.format(REDIS_PASSWORD, REDIS_UNIX_SOCKET, REDIS_DB)
        else:
            url = 'unix://{}?db={}'.format(REDIS_UNIX_SOCKET, REDIS_DB)
    elif REDIS_URL:
        url = REDIS_URL
    else:
        log.error("ENVIROMENT MISSING `REDIS_URL`")
        sys.exit(1)
    conn = redis.from_url(url)
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()
