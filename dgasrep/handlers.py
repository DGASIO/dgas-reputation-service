import iso8601
import os
from dgas.config import config
from dgas.analytics import AnalyticsMixin
from dgas.handlers import BaseHandler
from dgas.database import DatabaseMixin
from dgas.errors import JSONHTTPError
from dgas.log import log
from dgas.handlers import RequestVerificationMixin
from dgas.utils import validate_address
from tornado.ioloop import IOLoop
from decimal import Decimal, InvalidOperation
from dgasrep.tasks import update_user_reputation, calculate_user_reputation

def render_review(review):
    return {
        "reviewer": review['reviewer_id'],
        "reviewee": review['reviewee_id'],
        "rating": float(review['rating']),
        "review": review['review'],
        "date": review['updated'].isoformat(),
        "edited": review['created'] != review['updated']
    }

class UpdateUserMixin:

    def update_user(self, user_address):
        if (hasattr(self.application, 'q') and
                'reputation' in config and
                'push_url' in config['reputation']):
            self.application.q.enqueue(
                update_user_reputation,
                self.application.rep_push_urls,
                config['reputation']['signing_key'],
                user_address)
        else:
            log.warn("Not updating users: {}, {}, {}".format(
                hasattr(self.application, 'q'),
                'reputation' in config,
                'push_url' in config['reputation'] if 'reputation' in config else None))

class SubmitReviewHandler(RequestVerificationMixin, AnalyticsMixin, DatabaseMixin, UpdateUserMixin, BaseHandler):

    async def put(self):
        submitter, user, rating, message, location = await self.validate()

        async with self.db:
            rval = await self.db.execute(
                "UPDATE reviews "
                "SET rating = $3, review = $4, updated = (now() at time zone 'utc') "
                "WHERE reviewer_id = $1 AND reviewee_id = $2",
                submitter, user, rating, message)
            if rval == "UPDATE 0":
                raise JSONHTTPError(400, body={'errors': [{'id': 'no_existing_review_found',
                                                           'message': 'A review for that reviewee was not found to update'}]})
            await self.db.commit()

        self.set_status(204)
        self.update_user(user)
        if hasattr(self.application, 'store_location'):
            IOLoop.current().add_callback(self.application.store_location, submitter, location)
        self.track(submitter, "Gave Review", {"score": float(rating)})
        self.track(user, "Was reviewed", {"score": float(rating)})

    async def post(self):
        submitter, user, rating, message, location = await self.validate()

        # save the review, or replace an existing review
        async with self.db:
            await self.db.execute(
                "INSERT INTO reviews (reviewer_id, reviewee_id, rating, review) "
                "VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (reviewer_id, reviewee_id) DO UPDATE "
                "SET rating = EXCLUDED.rating, review = EXCLUDED.review, "
                "updated = (now() at time zone 'utc')",
                submitter, user, rating, message)
            await self.db.commit()

        self.set_status(204)
        self.update_user(user)
        if hasattr(self.application, 'store_location'):
            IOLoop.current().add_callback(self.application.store_location, submitter, location)
        self.track(submitter, "Gave review", {"rating": float(rating)})
        self.track(user, "Was reviewed", {"rating": float(rating)})

    async def validate(self):

        submitter = self.verify_request()

        if not all(x in self.json for x in ['reviewee', 'rating']):
            raise JSONHTTPError(400, body={'errors': [{'id': 'bad_arguments', 'message': 'Bad Arguments'}]})

        # validate user address
        user = self.json['reviewee']
        # lowercase the address
        user = user.lower()
        if not validate_address(user):
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_address', 'message': 'Invalid User Address'}]})

        if submitter == user:
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_reviewee', 'message': "Cannot review yourself!"}]})

        # validate the rating
        rating = self.json['rating']
        if isinstance(rating, (dict, list, type(None))):
            rating = Decimal(-1)
        else:
            try:
                rating = Decimal(rating)
            except (InvalidOperation, ValueError, TypeError):
                rating = Decimal(-1)
        if rating.is_nan() or rating.is_infinite() or rating < 0 or rating > 5:
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_rating', 'message': 'Invalid Rating'}]})

        # validate the message
        message = self.json.get('review', None)
        if message and not isinstance(message, str):
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_review', 'message': 'Invalid Review'}]})

        for h in self.request.headers:
            print("HEADER -- {}: {}".format(h, self.request.headers[h]))

        ip_addr = self.request.remote_ip or "0.0.0.0"
        if 'X-Forwarded-For' in self.request.headers:
            ip_addr = self.request.headers['X-Forwarded-For']

        return submitter, user, rating, message, ip_addr

class DeleteReviewHandler(RequestVerificationMixin, DatabaseMixin, UpdateUserMixin, BaseHandler):

    async def post(self):

        submitter = self.verify_request()

        if not all(x in self.json for x in ['reviewee']):
            raise JSONHTTPError(400, body={'errors': [{'id': 'bad_arguments', 'message': 'Bad Arguments'}]})

        # validate user address
        user = self.json['reviewee']
        # lowercase the address
        user = user.lower()
        if not validate_address(user):
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_address', 'message': 'Invalid User Address'}]})

        # save the review, or replace an existing review
        async with self.db:
            await self.db.execute(
                "DELETE FROM reviews WHERE reviewer_id = $1 AND reviewee_id = $2",
                submitter, user)
            await self.db.commit()

        self.set_status(204)
        self.update_user(user)

class GetUserRatingHandler(DatabaseMixin, BaseHandler):

    async def get(self, reviewee):

        reviewee = reviewee.lower()
        if not validate_address(reviewee):
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_dgas_id', 'message': 'Invalid Dgas Id'}]})

        async with self.db:
            score, count, avg, stars = await calculate_user_reputation(self.db, reviewee)

        self.write({
            # NOTE: backwards compatibility
            "score": avg,
            "count": count,
            # ======
            "reputation_score": score,
            "review_count": count,
            "average_rating": avg,
            "stars": stars,
        })

class SearchReviewsHandler(DatabaseMixin, BaseHandler):

    async def get(self):

        reviewee = self.get_query_argument('reviewee', None)
        reviewer = self.get_query_argument('reviewer', None)
        oldest = self.get_query_argument('oldest', None)
        try:
            offset = int(self.get_query_argument('offset', 0))
            limit = int(self.get_query_argument('limit', 10))
        except ValueError:
            raise JSONHTTPError(400, body={'errors': [{'id': 'bad_arguments', 'message': 'Bad Arguments'}]})

        if reviewee is None and reviewer is None:
            raise JSONHTTPError(400, body={'errors': [{'id': 'bad arguments', 'message': 'Bad Arguments'}]})

        wheres = []
        sql_args = []

        if reviewee is not None:
            # lowercase the address
            reviewee = reviewee.lower()
            if not validate_address(reviewee):
                raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_address', 'message': 'Invalid Address for `reviewee`'}]})
            wheres.append("reviewee_id = ${}".format(len(wheres) + 1))
            sql_args.append(reviewee)

        if reviewer is not None:
            # lowercase the address
            reviewer = reviewer.lower()
            if not validate_address(reviewer):
                raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_address', 'message': 'Invalid Address for `reviewer`'}]})
            wheres.append("reviewer_id = ${}".format(len(wheres) + 1))
            sql_args.append(reviewer)

        if oldest is not None:
            try:
                oldest = iso8601.parse_date(oldest)
                # remove the tzinfo so asyncpg can handle them
                # fromutc adds the utc offset to the date, but doesn't remove the tzinfo
                # so the final replace is to wipe that out (which doesn't adjust anything else)
                oldest = oldest.tzinfo.fromutc(oldest).replace(tzinfo=None)
            except iso8601.ParseError:
                raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_date', 'message': 'Invalid date for `oldest`'}]})
            wheres.append("updated >= ${}".format(len(wheres) + 1))
            sql_args.append(oldest)

        cnt_sql = "SELECT COUNT(*) FROM reviews WHERE {}".format(" AND ".join(wheres))
        sql = "SELECT * FROM reviews WHERE {} ORDER BY updated DESC OFFSET ${} LIMIT ${}".format(
            " AND ".join(wheres), len(wheres) + 1, len(wheres) + 2)

        async with self.db:
            reviews = await self.db.fetch(sql, *sql_args + [offset, limit])
            stats = await self.db.fetchrow(cnt_sql, *sql_args)

        self.write({
            "query": self.request.query,
            "total": stats['count'],
            "reviews": [render_review(r) for r in reviews],
            "offset": offset,
            "limit": limit
        })

class ReprocessReviews(RequestVerificationMixin, UpdateUserMixin, DatabaseMixin, BaseHandler):
    async def post(self):

        submitter = self.verify_request()
        if submitter != os.environ["ADMIN_ADDRESS"]:
            raise JSONHTTPError(404, body={})

        # save the review, or replace an existing review
        async with self.db:
            reviewees = await self.db.fetch("SELECT DISTINCT(reviewee_id) FROM reviews")

        for reviewee in reviewees:
            reviewee = reviewee['reviewee_id']
            log.info("queuing review reporcessing for: {}".format(reviewee))
            self.update_user(reviewee)
