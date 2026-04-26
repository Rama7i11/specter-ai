"""
Geo-IP enrichment via ip-api.com (free, no key, HTTP).
Results are cached in-process so repeated alerts from the same IP cost nothing.
Private/loopback addresses are short-circuited — no network call made.
"""

import ipaddress
import logging

import httpx

logger = logging.getLogger(__name__)

_cache: dict[str, dict] = {}

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_NULL_GEO = {"country": None, "city": None, "country_code": None, "lat": None, "lon": None}


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        return True


async def lookup(ip: str) -> dict:
    """
    Return {"country", "city", "country_code"} for *ip*.
    Always returns a dict with those three keys, never raises.
    Private IPs return nulls without a network call.
    """
    if ip in _cache:
        return _cache[ip]

    if _is_private(ip):
        result = {
            "country": None, "city": "private/local",
            "country_code": None, "lat": None, "lon": None,
        }
        _cache[ip] = result
        return result

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,city,countryCode,lat,lon"},
                timeout=2.0,
            )
            data = r.json()
            if data.get("status") == "success":
                result = {
                    "country":      data.get("country"),
                    "city":         data.get("city"),
                    "country_code": data.get("countryCode"),
                    "lat":          data.get("lat"),
                    "lon":          data.get("lon"),
                }
            else:
                result = dict(_NULL_GEO)
    except Exception as exc:  # noqa: BLE001
        logger.debug("geo lookup failed for %s: %s", ip, exc)
        result = dict(_NULL_GEO)

    _cache[ip] = result
    logger.info("geo  ip=%-16s  %s, %s", ip, result["city"], result["country"])
    return result
