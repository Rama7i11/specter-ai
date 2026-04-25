import asyncio
import datetime
import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models.alert import CommandIn
from app.services import state
from app.services.hardware_client import (
    particle_defense_ok,
    particle_denied,
    particle_executing,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice")


def _record(cmd: int, action: str, result: str, ip: str | None = None) -> None:
    state.defenses.append({
        "command":   cmd,
        "action":    action,
        "result":    result,
        "ip":        ip,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    })


def _effective_mode() -> str:
    """Return current hardware mode, or UNKNOWN if heartbeat has timed out / never arrived."""
    if state.last_heartbeat_time is None:
        return "UNKNOWN"
    if (time.time() - state.last_heartbeat_time) > state.HEARTBEAT_TIMEOUT:
        return "UNKNOWN"
    return state.HARDWARE_MODE


def _mode_display(mode: str) -> str:
    return mode.replace("_", " ").title()


def _defense_refused(cmd: int, mode: str):
    """Build a 403 JSONResponse with a Gemini-speakable result string."""
    asyncio.create_task(particle_denied(f"MODE_{mode}_REQUIRED_DEFENSE_READY"))
    speak = (
        f"Defense blocked. The wearable is in {_mode_display(mode)} mode. "
        f"Please turn the dial to Defense Ready and try again."
    )
    logger.warning("cmd%d refused — hardware_mode=%s", cmd, mode)
    return JSONResponse(
        status_code=403,
        content={
            "executed":      False,
            "command":       cmd,
            "result":        speak,
            "denied_reason": mode,
        },
    )


@router.post("/command")
async def voice_command(body: CommandIn):
    cmd  = body.command
    args = body.args

    # ── cmd 1: block attacker IP ─────────────────────────────────────────
    if cmd == 1:
        from defenses.block_ip import block_ip

        mode = _effective_mode()
        if mode != "DEFENSE_READY":
            return _defense_refused(cmd, mode)

        ip = args.get("ip")
        if not ip and state.alerts:
            ip = state.alerts[-1]["ip"]
        if not ip:
            asyncio.create_task(particle_denied("NO_IP"))
            return {"executed": False, "command": 1, "result": "No IP available to block"}

        asyncio.create_task(particle_executing(1, "BLOCK_IP"))
        newly_blocked = block_ip(ip)
        result = f"IP {ip} {'blocked' if newly_blocked else 'was already blocked'}"
        asyncio.create_task(particle_defense_ok("BLOCK_IP_SUCCESS"))
        _record(cmd, "block_ip", result, ip=ip)
        logger.info("cmd1 block_ip: %s", result)

    # ── cmd 2: clear all IP blocks ────────────────────────────────────────
    elif cmd == 2:
        from defenses.block_ip import unblock_all

        mode = _effective_mode()
        if mode != "DEFENSE_READY":
            return _defense_refused(cmd, mode)

        asyncio.create_task(particle_executing(2, "RESET"))
        n = unblock_all()
        result = f"Cleared {n} blocked IP{'s' if n != 1 else ''} — attacker access restored for re-demo"
        asyncio.create_task(particle_defense_ok("RESET_SUCCESS"))
        _record(cmd, "reset_session", result)
        logger.info("cmd2 reset_session: %s", result)

    # ── cmd 3: status report — works in any mode ──────────────────────────
    elif cmd == 3:
        from defenses.block_ip import get_blocked

        asyncio.create_task(particle_executing(3, "STATUS"))
        recent  = list(state.alerts)[-3:]
        blocked = get_blocked()

        if not recent:
            result = "No alerts recorded in this session. Detector is standing by."
        else:
            lines = []
            for i, a in enumerate(recent):
                lines.append(
                    f"Alert {i+1}: SQL injection, "
                    f"pattern {a['matched_pattern']}, "
                    f"at {a['timestamp'][:19].replace('T', ' ')}"
                )
            block_str = (
                f"{len(blocked)} IP{'s' if len(blocked) != 1 else ''} currently blocked"
                if blocked else "no IPs currently blocked"
            )
            result = (
                f"Last {len(recent)} alert{'s' if len(recent) != 1 else ''}: "
                + "; ".join(lines)
                + f". Status: {block_str}."
            )

        asyncio.create_task(particle_defense_ok("STATUS_SUCCESS"))
        _record(cmd, "status_report", result)
        logger.info("cmd3 status_report generated")

    else:
        asyncio.create_task(particle_denied(f"UNKNOWN_CMD_{cmd}"))
        return {"executed": False, "command": cmd, "result": f"Unknown command {cmd}"}

    return {"executed": True, "command": cmd, "result": result}
