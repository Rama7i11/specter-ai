"""
Particle Cloud hardware integration for the Specter-AI wearable.
All calls are fire-and-forget — hardware being offline never breaks the pipeline.

Particle function endpoint:
  POST https://api.particle.io/v1/devices/{DEVICE_ID}/{FUNCTION_NAME}
  Body (form-encoded): access_token=TOKEN&arg=ARG
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_PARTICLE_BASE = "https://api.particle.io/v1/devices"


async def particle_call(function_name: str, arg: str) -> bool:
    device_id = os.getenv("PARTICLE_DEVICE_ID", "")
    token     = os.getenv("PARTICLE_ACCESS_TOKEN", "")

    if not device_id or not token:
        logger.info("particle dev-mode — %s(%s)", function_name, arg)
        return False

    url = f"{_PARTICLE_BASE}/{device_id}/{function_name}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                data={"access_token": token, "arg": arg},
                timeout=5,
            )
            logger.info("particle %s(%s) → %s", function_name, arg, r.status_code)
            return r.status_code == 200
    except Exception as exc:  # noqa: BLE001
        logger.warning("particle unreachable (%s) — continuing", exc)
        return False


async def particle_alert(ip: str, severity: int = 10) -> None:
    await particle_call("alert", f"SQL_INJECTION,{ip},{severity}")


async def particle_executing(cmd_num: int, cmd_name: str) -> None:
    await particle_call("executing", f"COMMAND_{cmd_num}_{cmd_name}")


async def particle_defense_ok(label: str) -> None:
    await particle_call("defenseOK", label)


async def particle_denied(reason: str) -> None:
    await particle_call("denied", reason)
