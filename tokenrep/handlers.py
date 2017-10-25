import iso8601
from asyncpg.handlers import BaseHandler
from asyncpg.database import DatabaseMixin
from asyncpg.errors import JSONHTTPError
from tokenservices.handlers import RequestVerificationMixin
from dgasio.utils import validate_address
from decimal import Decimal, InvalidOperation
from .tasks import update_user_reputation

def render_review(review):
    return {
        "reviewer": review['reviewer_address'],
        "reviewee": review['reviewee_address'],
        "score": review['score'],
        "review": review['review']
    }

class UpdateUserMixin:

    def update_user(self, user_address):
        if (hasattr(self.application, 'q') and
                'reputation' in self.application.config and
                'push_url' in self.application.config['reputation']):
            self.application.q.enqueue(
                update_user_reputation,
                dict(self.application.config['database']),
                self.application.config['reputation']['push_url'],
                self.application.config['reputation']['signing_key'],
                user_address)

class SubmitReviewHandler(RequestVerificationMixin, DatabaseMixin, UpdateUserMixin, BaseHandler):

    async def post(self):

        submitter = self.verify_request()

        if not all(x in self.json for x in ['reviewee', 'score']):
            raise JSONHTTPError(400, body={'errors': [{'id': 'bad_arguments', 'message': 'Bad Arguments'}]})

        # validate user address
        user = self.json['reviewee']
        if not validate_address(user):
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_address', 'message': 'Invalid User Address'}]})

        # validate the score
        score = self.json['score']
        if isinstance(score, (dict, list, type(None))):
            score = Decimal(-1)
        else:
            try:
                score = Decimal(score)
            except (InvalidOperation, ValueError, TypeError):
                score = Decimal(-1)
        if score.is_nan() or score.is_infinite() or score < 0 or score > 5:
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_score', 'message': 'Invalid Score'}]})

        # validate the message
        message = self.json.get('review', None)
        if message and not isinstance(message, str):
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_review', 'message': 'Invalid Review'}]})

        # save the review, or replace an existing review
        async with self.db:
            await self.db.execute(
                "INSERT INTO reviews (reviewer_address, reviewee_address, score, review) "
                "VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (reviewer_address, reviewee_address) "
                "DO UPDATE "
                "SET score = EXCLUDED.score, review = EXCLUDED.review, updated = (now() at time zone 'utc')",
                submitter, user, score, message)
            await self.db.commit()

        self.set_status(204)
        self.update_user(user)

class DeleteReviewHandler(RequestVerificationMixin, DatabaseMixin, UpdateUserMixin, BaseHandler):

    async def post(self):

        submitter = self.verify_request()

        if not all(x in self.json for x in ['reviewee']):
            raise JSONHTTPError(400, body={'errors': [{'id': 'bad_arguments', 'message': 'Bad Arguments'}]})

        # validate user address
        user = self.json['reviewee']
        if not validate_address(user):
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_address', 'message': 'Invalid User Address'}]})

        # save the review, or replace an existing review
        async with self.db:
            await self.db.execute(
                "DELETE FROM reviews WHERE reviewer_address = $1 AND reviewee_address = $2",
                submitter, user)
            await self.db.commit()

        self.set_status(204)
        self.update_user(user)

class GetUserRatingHandler(DatabaseMixin, BaseHandler):

    async def get(self, reviewee):

        if not validate_address(reviewee):
            raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_address', 'message': 'Invalid Address'}]})

        async with self.db:
            row = await self.db.fetchrow(
                "SELECT AVG(score), COUNT(score) FROM reviews WHERE reviewee_address = $1",
                reviewee)

        average = row['avg']
        # round average down to 1 decimal point
        average = round(average * 10) / 10

        self.write({
            "average": average,
            "count": row['count']
        })

class SearchReviewsHandler(DatabaseMixin, BaseHandler):

    async def get(self):

        reviewee = self.get_query_argument('reviewee', None)
        reviewer = self.get_query_argument('reviewer', None)
        oldest = self.get_query_argument('oldest', None)
        offset = self.get_query_argument('offset', 0)
        limit = self.get_query_argument('limit', 10)

        if reviewee is None and reviewer is None:
            raise JSONHTTPError(400, body={'errors': [{'id': 'bad arguments', 'message': 'Bad Arguments'}]})

        wheres = []
        sql_args = []

        if reviewee is not None:
            if not validate_address(reviewee):
                raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_address', 'message': 'Invalid Address for `reviewee`'}]})
            wheres.append("reviewee_address = ${}".format(len(wheres) + 1))
            sql_args.append(reviewee)

        if reviewer is not None:
            if not validate_address(reviewer):
                raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_address', 'message': 'Invalid Address for `reviewer`'}]})
            wheres.append("reviewer_address = ${}".format(len(wheres) + 1))
            sql_args.append(reviewer)

        if oldest is not None:
            try:
                oldest = iso8601.parse_date(oldest)
            except iso8601.ParseError:
                raise JSONHTTPError(400, body={'errors': [{'id': 'invalid_date', 'message': 'Invalid date for `oldest`'}]})
            wheres.append("updated >= ${}".format(len(wheres) + 1))
            sql_args.append(oldest)

        sql = "SELECT * FROM reviews WHERE {}".format(" AND ".join(wheres))
        cnt_sql = "SELECT COUNT(*) FROM reviews WHERE {}".format(" AND ".join(wheres))

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
