import os
from . import locations
from . import handlers
import tokenservices.web
from tokenservices.handlers import GenerateTimestamp
from rq import Queue
import redis
from functools import partial

urls = [
    (r"^/v1/timestamp/?$", GenerateTimestamp),

    (r"^/v1/search/review/?$", handlers.SearchReviewsHandler),
    (r"^/v1/review/submit/?$", handlers.SubmitReviewHandler),
    (r"^/v1/review/delete/?$", handlers.DeleteReviewHandler),
    (r"^/v1/user/(?P<reviewee>[^/]+)/?$", handlers.GetUserRatingHandler),

    # admin
    (r"^/v1/admin/reprocess/?$", handlers.ReprocessReviews)
]

class Application(tokenservices.web.Application):

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'USE_GEOLITE2' in os.environ:
            self.store_location = partial(
                locations.store_review_location,
                locations.get_location_from_geolite2, self.connection_pool)
        else:
            self.store_location = partial(
                locations.store_review_location,
                locations.get_location_from_ip2c, self.connection_pool)


def main():
    app = Application(urls)
    conn = redis.from_url(app.config['redis']['url'])
    app.q = Queue(connection=conn)
    app.start()
