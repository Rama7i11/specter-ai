import logging

from fastapi import APIRouter

from app.models.alert import AlertIn

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/hardware-alert")
async def hardware_alert(alert: AlertIn):
    """No-op stub — kept for backward compatibility with hardware team's test scripts."""
    return {"status": "ok"}
