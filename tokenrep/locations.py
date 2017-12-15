import asyncio
import ipaddress
import asyncpg.exceptions

from tokenservices.log import log
from tornado.httpclient import AsyncHTTPClient

async def get_location_from_geolite2(pool, ip_addr):

    try:
        ip_addr = ipaddress.ip_address(ip_addr)
        # fix issues with asyncpg not handling ip address netmask defaults
        # correctly
        ip_addr = "{}/{}".format(ip_addr, 32 if ip_addr.version == 4 else 128)
        async with pool.acquire() as con:
            row = await con.fetchrow(
                "SELECT cs.country_iso_code FROM geolite2_ip_addresses ips "
                "JOIN geolite2_countries cs ON ips.geoname_id = cs.geoname_id "
                "WHERE ips.network >> $1", ip_addr)
        return row['country_iso_code'] if row else None
    except ValueError:
        return None
    except asyncpg.exceptions.UndefinedTableError:
        log.warning("Missing GeoLite2 database tables")
        return None

async def get_location_from_ip2c(pool, ip_addr):

    try:
        ip_addr = ipaddress.ip_address(ip_addr)
        ip_addr = str(ip_addr)
    except ValueError:
        return None

    url = "http://ip2c.org/{}".format(ip_addr)

    retries = 5
    backoff = 1

    while True:
        resp = await AsyncHTTPClient().fetch(
            url, method="GET", request_timeout=10)
        if resp.code == 200:
            txt = resp.body.decode('utf-8')
            state, cd, cod, _ = txt.split(";")
            if state == 0 or state == 2:
                log.warning("IP2C Error: {} -> {}".format(ip_addr, txt))
            return cd or None
        else:
            log.error("Error getting ip details")
            retries -= 1
            if retries <= 0:
                return None
            else:
                await asyncio.sleep(backoff)
                backoff = min(backoff + 5, 30)

    return None

async def store_review_location(fn, pool, reviewer_id, ip_addr):

    location = await fn(pool, ip_addr)

    async with pool.acquire() as con:
        await con.execute(
            "INSERT INTO review_locations (reviewer_id, location) "
            "VALUES ($1, $2) ",
            reviewer_id, location)
