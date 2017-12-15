CREATE TABLE IF NOT EXISTS reviews (
    reviewer_id VARCHAR NOT NULL,
    reviewee_id VARCHAR NOT NULL,

    rating DECIMAL,
    review VARCHAR,

    created TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc'),
    updated TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc'),

    PRIMARY KEY (reviewer_id, reviewee_id)
);

-- stores the location based on the revewer's ip address
-- when submitting a review. This is stored every time a reviewer
-- makes/updates a review.
-- location is stored by geoname_id, retrieved from matching the
-- ip address of the submit request to the GeoLite2 database
CREATE TABLE IF NOT EXISTS review_locations (
    review_location_id SERIAL PRIMARY KEY,
    reviewer_id VARCHAR NOT NULL,
    location VARCHAR,
    submitted TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON reviews (reviewer_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewee ON reviews (reviewee_id);

CREATE INDEX IF NOT EXISTS idx_reviews_sort_by_updated ON reviews (updated DESC);
CREATE INDEX IF NOT EXISTS idx_review_reviewer_sorted ON reviews (reviewer_id, updated DESC);
CREATE INDEX IF NOT EXISTS idx_review_reviewee_sorted ON reviews (reviewee_id, updated DESC);
CREATE INDEX IF NOT EXISTS idx_review_reviewer_and_reviewee_sorted ON reviews (reviewer_id, reviewee_id, updated DESC);

CREATE INDEX IF NOT EXISTS idx_review_locations_reviewer_id ON review_locations (reviewer_id);

UPDATE database_version SET version_number = 1;
