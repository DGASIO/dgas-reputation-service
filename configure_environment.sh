#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

if [ ! -z ${ENV_DIR+x} ]; then
    STAGE=$(cat "$ENV_DIR/STAGE")
    DATABASE_URL=$(cat "$ENV_DIR/DATABASE_URL")
else
    STAGE="unknown"
fi
echo "BUILDING requirements.txt WITH STAGE=$STAGE"
cat requirements-base.txt > requirements.txt
if [[ $STAGE == "production" ]]; then
    cat requirements-production.txt >> requirements.txt
else
    cat requirements-development.txt >> requirements.txt
fi
cat requirements.txt

### geocode
if [ ! -z ${DATABASE_URL+x} ]; then
    URL=http://geolite.maxmind.com/download/geoip/database/GeoLite2-Country-CSV_20170404.zip
    MD5SUM="5b7d4cd3955a8e773cc71deff71a4155"
    FILENAME=GeoLite2-Country-CSV_20170404.zip
    if [ ! -e $FILENAME ] || [ $(md5 < $FILENAME) == $MD5SUM ]; then
        curl -s -S -o $FILENAME $URL
    fi
    if [ $(md5 < $FILENAME) == $MD5SUM ]; then
        echo "IMPORTING GeoLite2 DB"
        unzip -o -j $FILENAME -d geolite2
        sed \
             -e "s@:ipv4_csv@${PWD}/geolite2/GeoLite2-Country-Blocks-IPv4.csv@g" \
             -e "s@:ipv6_csv@${PWD}/geolite2/GeoLite2-Country-Blocks-IPv6.csv@g" \
             -e "s@:country_csv@${PWD}/geolite2/GeoLite2-Country-Locations-en.csv@g" \
             sql/import_geolite2.sql \
            | psql $DATABASE_URL
        rm -r geolite2/
    else
        echo "ERROR: md5sum of GeoLite2 download did not match!"
    fi
else
    echo "SKIPPING GeoLite2 database import"
fi
