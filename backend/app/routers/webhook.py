import logging
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.models.alert import AlertIn
from app.services import state
from app.services.hardware_client import particle_alert

logger = logging.getLogger(__name__)
router = APIRouter()


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
    entry = {**alert.model_dump(), "alert_id": alert_id}

    state.alerts.append(entry)
    state.attack_log.append(alert.raw_request)
    state.last_alert_time = time.time()

    background_tasks.add_task(particle_alert, alert.ip, alert.severity)

    logger.info("alert #%d  ip=%-16s  pattern=%s", alert_id, alert.ip, alert.matched_pattern)
    return {"status": "received", "alert_id": alert_id}
