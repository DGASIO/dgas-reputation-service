import os
from . import handlers
import asyncpg.web
from tokenservices.handlers import GenerateTimestamp
from rq import Queue
import redis

urls = [
    (r"^/v1/timestamp/?$", GenerateTimestamp),

    (r"^/v1/search/review/?$", handlers.SearchReviewsHandler),
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
            config['reputation']['push_url'] = os.environ['REPUTATION_PUSH_URL']

        if 'push_url' in config['reputation']:
            self.rep_push_urls = config['reputation']['push_url'].split(',')
        else:
            self.rep_push_url = []

        return config


def main():
    app = Application(urls)
    conn = redis.from_url(app.config['redis']['url'])
    app.q = Queue(connection=conn)
    app.start()
