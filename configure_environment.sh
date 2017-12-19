#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

if [ ! -z ${ENV_DIR+x} ]; then
    if [ -e $ENV_DIR/STAGE ]; then
        STAGE=$(cat "$ENV_DIR/STAGE")
    else
        STAGE="development"
    fi
    DATABASE_URL=$(cat "$ENV_DIR/DATABASE_URL")
    if [ -e $ENV_DIR/USE_GEOLITE2 ]; then
        USE_GEOLITE2=$(cat "$ENV_DIR/USE_GEOLITE2")
    fi
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

if command -v md5sum &>/dev/null; then
    MD5=md5sum
elif command -v md5 &>/dev/null; then
    MD5="md5 -r"
else
    echo "Unable to find suitable md5 calculator"
    exit 1
fi

### geocode
if [ ! -z ${USE_GEOLITE2+x} ] && [ ! -z ${DATABASE_URL+x} ]; then
    URL=http://geolite.maxmind.com/download/geoip/database/GeoLite2-Country-CSV_20170404.zip
    MD5SUM="5b7d4cd3955a8e773cc71deff71a4155"
    FILENAME=GeoLite2-Country-CSV_20170404.zip
    if [ -e $FILENAME ]; then
        CHKSUM=$(eval $MD5 $FILENAME | grep --only-matching -m 1 '^[0-9a-f]*')
    fi
    if [ ! -e $FILENAME ] || [ $CHKSUM != $MD5SUM ]; then
        curl -s -S -o $FILENAME $URL
        CHKSUM=$(eval $MD5 $FILENAME | grep --only-matching -m 1 '^[0-9a-f]*')
    fi
    if [ $CHKSUM == $MD5SUM ]; then
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
