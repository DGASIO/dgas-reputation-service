import os
from . import handlers
import asyncpg.web
from tokenservices.handlers import GenerateTimestamp
from rq import Queue, Connection
from . import worker
import redis

urls = [
    (r"^/v1/timestamp/?$", GenerateTimestamp),

    (r"^/v1/review/submit/?$", handlers.SubmitReviewHandler),
    (r"^/v1/review/delete/?$", handlers.DeleteReviewHandler),
    (r"^/v1/user/(?P<reviewee>[^/]+)/?$", handlers.GetUserRatingHandler),
]

class Application(asyncpg.web.Application):

    def process_config(self):
        config = super(Application, self).process_config()

        if 'reputation' not in config:
            config['reputation'] = {}

        if 'REPUTATION_PUSH_SIGNING_KEY' in os.environ:
            config['reputation']['signing_key'] = os.environ['REPUTATION_PUSH_SIGNING_KEY']
        if 'REPUTATION_PUSH_URL' in os.environ:
            config['reputation']['url'] = os.environ['REPUTATION_PUSH_URL']

        return config


def main():
    app = asyncpg.web.Application(urls)
    conn = redis.from_url(app.config['redis'].REDIS_URL)
    app.q = Queue(connection=conn)
    app.start()
