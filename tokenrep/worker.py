import os

import redis
from rq import Worker, Queue, Connection

listen = ['high', 'default', 'low']

REDIS_URL = os.getenv('REDIS_URL', None)
REDIS_UNIX_SOCKET = os.getenv('REDIS_UNIX_SOCKET', None)
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

if __name__ == '__main__':
    print("RUNNING")
    if REDIS_UNIX_SOCKET:
        if REDIS_PASSWORD:
            url = 'unix://:{}@{}?db={}'.format(REDIS_PASSWORD, REDIS_UNIX_SOCKET, REDIS_DB)
        else:
            url = 'unix://{}?db={}'.format(REDIS_UNIX_SOCKET, REDIS_DB)
    else:
        url = REDIS_URL or 'redis://localhost:6379'
    conn = redis.from_url(url)
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()
