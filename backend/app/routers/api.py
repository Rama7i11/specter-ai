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
    return {"alerts": list(state.alerts)}


@router.get("/defenses")
async def get_defenses():
    return {"defenses": list(state.defenses)}


@router.get("/attack-log")
async def get_attack_log():
    return {"lines": list(state.attack_log)}


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

    return {
        "detector":              detector_status,
        "backend":               "up",
        "alerts_today":          alerts_today,
        "blocked_ips":           len(get_blocked()),
        "uptime":                int(now - state.START_TIME),
        "hardware_mode":         effective_mode,
        "seconds_since_heartbeat": seconds_since_hb,
    }


@router.get("/health")
async def health():
    return {"status": "ok", "uptime": int(time.time() - state.START_TIME)}
