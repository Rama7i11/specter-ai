"""
PagerDuty Events API V2 integration.
On severity-10 alerts the webhook handler enqueues a fire-and-forget call to
create_incident(); a missing PAGERDUTY_ROUTING_KEY is non-fatal so demos still
run without an account configured.
"""

import datetime
import logging
import os

import httpx

from app.services import state

logger = logging.getLogger(__name__)

_PD_ENQUEUE_URL = "https://events.pagerduty.com/v2/enqueue"


async def create_incident(alert: dict) -> dict | None:
    routing_key = os.getenv("PAGERDUTY_ROUTING_KEY", "")
    if not routing_key:
        logger.info("[PD] no routing key - skipping")
        return None

    ip       = alert.get("ip", "unknown")
    severity = alert.get("severity", 0)
    pattern  = alert.get("matched_pattern", "unknown")
    summary  = f"SQL injection from {ip} (severity {severity})"

    payload = {
        "routing_key":  routing_key,
        "event_action": "trigger",
        "payload": {
            "summary":   summary,
            "source":    "specter-ai-soc",
            "severity":  "critical",
            "component": "bank-app",
            "group":     "specter-ai",
            "class":     "sql-injection",
            "custom_details": {
                "ip":              ip,
                "matched_pattern": pattern,
                "geo_city":        alert.get("geo_city"),
                "geo_country":     alert.get("geo_country"),
            },
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(_PD_ENQUEUE_URL, json=payload, timeout=5)
            data = r.json() if r.content else {}
            if r.status_code == 202 and data.get("status") == "success":
                dedup_key = data.get("dedup_key")
                logger.info("[PD] incident created dedup_key=%s ip=%s", dedup_key, ip)
                state.PAGERDUTY_INCIDENTS.append({
                    "incident_id": dedup_key or "",
                    "alert_id":    alert.get("alert_id", 0),
                    "summary":     summary,
                    "status":      "triggered",
                    "created_at":  datetime.datetime.utcnow().isoformat() + "Z",
                })
                return data
            logger.warning("[PD] create failed status=%s body=%s", r.status_code, r.text[:200])
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PD] unreachable (%s) - continuing", exc)
        return None
