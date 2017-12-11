ALTER TABLE reviews RENAME COLUMN reviewer_address TO reviewer_id;
ALTER TABLE reviews RENAME COLUMN reviewee_address TO reviewee_id;

CREATE TABLE IF NOT EXISTS review_locations (
    review_location_id SERIAL PRIMARY KEY,
    reviewer_id VARCHAR NOT NULL,
    geoname_id INT,
    submitted TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS idx_review_locations_reviewer_id ON review_locations (reviewer_id);
