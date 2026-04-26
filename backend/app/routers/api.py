import datetime
import time
import logging

from fastapi import APIRouter
from fastapi.middleware.cors import CORSMiddleware  # noqa: F401 (added at app level)
from pydantic import BaseModel

from app.services import state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class HeartbeatIn(BaseModel):
    device:  str
    project: str = ""
    status:  str = "online"
    mode:    str
    ip:      str = ""


@router.post("/heartbeat")
async def heartbeat(body: HeartbeatIn):
    state.HARDWARE_MODE       = body.mode
    state.last_heartbeat_time = time.time()
    logger.info("heartbeat  device=%s  mode=%s  ip=%s", body.device, body.mode, body.ip)
    return {
        "ok":          True,
        "server_time": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get("/alerts")
async def get_alerts():
    out = []
    for a in state.alerts:
        item = dict(a)
        item.setdefault("city",    a.get("geo_city")    or "")
        item.setdefault("country", a.get("geo_country") or "")
        item.setdefault("lat",     a.get("lat"))
        item.setdefault("lon",     a.get("lon"))
        out.append(item)
    return {"alerts": out}


@router.get("/defenses")
async def get_defenses():
    from defenses.block_ip import get_blocked
    from defenses.lock_user import get_locked
    return {
        "defenses":     list(state.defenses),
        "blocked_ips":  list(get_blocked()),
        "locked_users": list(get_locked()),
    }


@router.get("/attack-log")
async def get_attack_log():
    return {"lines": list(state.attack_log)}


@router.get("/pagerduty-incidents")
async def get_pagerduty_incidents():
    return {"incidents": list(state.PAGERDUTY_INCIDENTS)}


@router.get("/history")
async def get_history():
    return {
        "alerts":              list(state.ALERT_HISTORY),
        "defenses":            list(state.DEFENSE_HISTORY),
        "pagerduty":           list(state.PAGERDUTY_HISTORY),
        "total_alerts_ever":   state.TOTAL_ALERTS_EVER,
        "total_defenses_ever": state.TOTAL_DEFENSES_EVER,
    }


@router.get("/status")
async def get_status():
    from defenses.block_ip import get_blocked

    now = time.time()

    # Detector "up" heuristic: received an alert within the last 5 minutes
    if state.last_alert_time and (now - state.last_alert_time) < 300:
        detector_status = "up"
    elif state.alerts:
        detector_status = "degraded"
    else:
        detector_status = "unknown"

    today = datetime.date.today().isoformat()
    alerts_today = sum(
        1 for a in state.alerts if a.get("timestamp", "").startswith(today)
    )

    # Effective hardware mode — UNKNOWN if heartbeat has timed out
    if state.last_heartbeat_time is None:
        effective_mode        = "UNKNOWN"
        seconds_since_hb      = None
    else:
        elapsed               = now - state.last_heartbeat_time
        seconds_since_hb      = int(elapsed)
        effective_mode        = state.HARDWARE_MODE if elapsed <= state.HEARTBEAT_TIMEOUT else "UNKNOWN"

    from defenses.lock_user import get_locked

    return {
        "detector":                detector_status,
        "backend":                 "up",
        "alerts_today":            alerts_today,
        "blocked_ips":             len(get_blocked()),
        "locked_users":            len(get_locked()),
        "uptime":                  int(now - state.START_TIME),
        "hardware_mode":           effective_mode,
        "seconds_since_heartbeat": seconds_since_hb,
        "pagerduty_incidents":     len(state.PAGERDUTY_INCIDENTS),
        "specter_mode":            state.SPECTER_STATE,
        "voice_state":             state.SPECTER_STATE,
        "voice_level":             state.SPECTER_VOICE_LEVEL,
        "dial_position":           effective_mode,
        "heartbeat_seconds_ago":   seconds_since_hb,
    }


@router.get("/health")
async def health():
    return {"status": "ok", "uptime": int(time.time() - state.START_TIME)}
