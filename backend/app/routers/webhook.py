import logging
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.models.alert import AlertIn
from app.services import state
from app.services.geo import lookup as geo_lookup
from app.services.hardware_client import particle_alert

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Briefing helpers ──────────────────────────────────────────────────────────

_DIGIT_WORDS = {
    "0": "zero", "1": "one",  "2": "two",   "3": "three", "4": "four",
    "5": "five",  "6": "six",  "7": "seven", "8": "eight", "9": "nine",
}
_NUM_WORDS = {
    0:"zero",1:"one",2:"two",3:"three",4:"four",5:"five",
    6:"six",7:"seven",8:"eight",9:"nine",10:"ten",
}


def _ip_to_spoken(ip: str) -> str:
    """'172.19.0.1' → 'one seven two dot one nine dot zero dot one'"""
    return " dot ".join(
        " ".join(_DIGIT_WORDS.get(d, d) for d in octet)
        for octet in ip.split(".")
    )


def _build_briefing(
    ip: str,
    matched_pattern: str,
    severity: int,
    geo: dict | None = None,
) -> str:
    pattern  = matched_pattern.upper()
    ip_words = _ip_to_spoken(ip)
    sev_word = _NUM_WORDS.get(severity, str(severity))

    loc = ""
    if geo:
        city    = geo.get("city") or ""
        country = geo.get("country") or ""
        if city and city != "private/local" and country:
            loc = f" Origin: {city}, {country}."
        elif country:
            loc = f" Origin: {country}."

    if "BRUTE" in pattern or "FORCE" in pattern or "FAIL" in pattern:
        return (
            f"Aegis team, this is Specter. Brute force attack from {ip_words}.{loc} "
            f"Five failed logins in sixty seconds. Severity {sev_word}. "
            f"Awaiting your command."
        )
    return (
        f"Aegis team, this is Specter. SQL injection detected. "
        f"Source IP {ip_words}.{loc} Severity {sev_word}. "
        f"Awaiting your command."
    )


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/webhook/wazuh")
async def receive_alert(
    alert: AlertIn,
    request: Request,
    background_tasks: BackgroundTasks,
):
    token = request.headers.get("X-Auth-Token", "")
    if token != state.WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid X-Auth-Token")

    alert_id = state.next_alert_id()

    geo = await geo_lookup(alert.ip)
    entry = {
        **alert.model_dump(),
        "alert_id":    alert_id,
        "geo_city":    geo.get("city")    if geo else None,
        "geo_country": geo.get("country") if geo else None,
    }

    state.alerts.append(entry)
    state.attack_log.append(alert.raw_request)
    state.last_alert_time = time.time()

    # Queue a proactive voice briefing — deduplicated per (type, ip) per 30s
    key  = (alert.type, alert.ip)
    last = state.LAST_BRIEFING_KEY.get(key, 0)
    if time.time() - last < state.BRIEFING_DEDUP_WINDOW:
        logger.info(
            "briefing suppressed for alert #%d (last briefing %ds ago)",
            alert_id, int(time.time() - last),
        )
    else:
        state.LAST_BRIEFING_KEY[key] = time.time()
        briefing_text = _build_briefing(alert.ip, alert.matched_pattern, alert.severity, geo)
        state.PENDING_BRIEFINGS.append({"alert_id": alert_id, "text": briefing_text})

    background_tasks.add_task(particle_alert, alert.ip, alert.severity)

    logger.info("alert #%d  ip=%-16s  pattern=%s", alert_id, alert.ip, alert.matched_pattern)
    return {"status": "received", "alert_id": alert_id}
