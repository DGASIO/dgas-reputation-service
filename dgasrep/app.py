import os
from . import locations
from . import handlers
import dgas.web
from dgas.handlers import GenerateTimestamp
from rq import Queue
import redis
from functools import partial
from dgas.config import config
from dgas.database import get_database_pool

def service_config():
    if 'reputation' not in config:
        config['reputation'] = {}

    if 'REPUTATION_PUSH_SIGNING_KEY' in os.environ:
        config['reputation']['signing_key'] = os.environ['REPUTATION_PUSH_SIGNING_KEY']
    if 'REPUTATION_PUSH_URL' in os.environ:
        config['reputation']['push_url'] = os.environ['REPUTATION_PUSH_URL']
service_config()

urls = [
    (r"^/v1/timestamp/?$", GenerateTimestamp),

    (r"^/v1/search/review/?$", handlers.SearchReviewsHandler),
    (r"^/v1/review/submit/?$", handlers.SubmitReviewHandler),
    (r"^/v1/review/delete/?$", handlers.DeleteReviewHandler),
    (r"^/v1/user/(?P<reviewee>[^/]+)/?$", handlers.GetUserRatingHandler),

    # admin
    (r"^/v1/admin/reprocess/?$", handlers.ReprocessReviews)
]

class Application(dgas.web.Application):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def _start(self):
        await super()._start()
        if 'USE_GEOLITE2' in os.environ:
            self.store_location = partial(
                locations.store_review_location,
                locations.get_location_from_geolite2, get_database_pool())
        else:
            self.store_location = partial(
                locations.store_review_location,
                locations.get_location_from_ip2c, get_database_pool())

        if 'push_url' in config['reputation']:
            self.rep_push_urls = config['reputation']['push_url'].split(',')
        else:
            self.rep_push_url = []

def main():
    app = Application(urls)
    conn = redis.from_url(config['redis']['url'])
    app.q = Queue(connection=conn)
    app.start()
