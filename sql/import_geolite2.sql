\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS geolite2_ip_addresses (
    network CIDR,
    geoname_id INT,
    registered_country_geoname_id INT,
    represented_country_geoname_id INT,
    is_anonymous_proxy BOOLEAN,
    is_satellite_provider BOOLEAN
);

CREATE INDEX IF NOT EXISTS geolite2_ip_addresses_network_idx ON geolite2_ip_addresses (network);

CREATE TABLE IF NOT EXISTS geolite2_countries (
    geoname_id INT,
    locale_code VARCHAR,
    continent_code VARCHAR,
    continent_name VARCHAR,
    country_iso_code VARCHAR,
    country_name VARCHAR
);

CREATE INDEX IF NOT EXISTS geolite2_ip_countries_geoname_id_idx ON geolite2_countries (geoname_id);

-- clear the existing data
DELETE FROM geolite2_ip_addresses;
DELETE FROM geolite2_countries;

-- import csv
\COPY geolite2_ip_addresses FROM :ipv4_csv DELIMITER ',' CSV HEADER;
\COPY geolite2_ip_addresses FROM :ipv6_csv DELIMITER ',' CSV HEADER;

\COPY geolite2_countries FROM :country_csv DELIMITER ',' CSV HEADER;
