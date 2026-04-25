import asyncio
import datetime
import logging
import re
import time
from urllib.parse import unquote_plus

from fastapi import APIRouter, Request
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
    if state.last_heartbeat_time is None:
        return "UNKNOWN"
    if (time.time() - state.last_heartbeat_time) > state.HEARTBEAT_TIMEOUT:
        return "UNKNOWN"
    return state.HARDWARE_MODE


def _mode_display(mode: str) -> str:
    return mode.replace("_", " ").title()


def _defense_refused(cmd: int, mode: str):
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


def _parse_username_from_raw(raw_request: str) -> str | None:
    """Extract username query param from a synthetic Apache log request string."""
    m = re.search(r"username=([^&\s\"]+)", raw_request, re.IGNORECASE)
    if m:
        return unquote_plus(m.group(1)) or None
    return None


# ── Wake button endpoints ─────────────────────────────────────────────────

@router.post("/wake")
async def trigger_wake(request: Request):
    state.WAKE_REQUESTED    = True
    state.wake_requested_at = time.time()
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    logger.info("wake button pressed")
    return {"acknowledged": True, "timestamp": ts}


@router.get("/wake-status")
async def wake_status():
    if not state.WAKE_REQUESTED or state.wake_requested_at is None:
        return {"wake_requested": False, "age_seconds": None}
    age    = int(time.time() - state.wake_requested_at)
    active = age <= state.WAKE_EXPIRY
    return {"wake_requested": active, "age_seconds": age}


@router.post("/wake-ack")
async def wake_ack():
    consumed = state.consume_wake()
    return {"consumed": consumed}


@router.get("/pending-briefing")
async def pending_briefing():
    hw_mode = state.HARDWARE_MODE
    if state.last_heartbeat_time is None or (
        (time.time() - state.last_heartbeat_time) > state.HEARTBEAT_TIMEOUT
    ):
        hw_mode = "UNKNOWN"

    while state.PENDING_BRIEFINGS:
        entry    = state.PENDING_BRIEFINGS.popleft()
        alert_id = entry["alert_id"]
        if alert_id not in state.SPOKEN_ALERT_IDS:
            state.SPOKEN_ALERT_IDS.add(alert_id)
            return {
                "briefing":      entry["text"],
                "alert_id":      alert_id,
                "hardware_mode": hw_mode,
            }
    return {"briefing": None, "hardware_mode": hw_mode}


# ── Command dispatcher ────────────────────────────────────────────────────

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

    # ── cmd 2: reset all defenses ─────────────────────────────────────────
    elif cmd == 2:
        from defenses.block_ip import unblock_all
        from defenses.lock_user import unlock_all

        mode = _effective_mode()
        if mode != "DEFENSE_READY":
            return _defense_refused(cmd, mode)

        asyncio.create_task(particle_executing(2, "RESET"))
        n_ips   = unblock_all()
        n_users = unlock_all()
        parts   = []
        if n_ips:
            parts.append(f"{n_ips} IP{'s' if n_ips != 1 else ''} unblocked")
        if n_users:
            parts.append(f"{n_users} account{'s' if n_users != 1 else ''} unlocked")
        result = (
            ("Cleared: " + ", ".join(parts) + " — demo ready for re-run.")
            if parts else "Nothing to clear — demo state was already clean."
        )
        asyncio.create_task(particle_defense_ok("RESET_SUCCESS"))
        _record(cmd, "reset_session", result)
        logger.info("cmd2 reset_session: %s", result)

    # ── cmd 3: status report — works in any mode ──────────────────────────
    elif cmd == 3:
        from defenses.block_ip import get_blocked
        from defenses.lock_user import get_locked

        asyncio.create_task(particle_executing(3, "STATUS"))
        recent  = list(state.alerts)[-3:]
        blocked = get_blocked()
        locked  = get_locked()

        if not recent:
            result = "No alerts recorded in this session. Detector is standing by."
        else:
            lines = []
            for i, a in enumerate(recent):
                alert_type = a.get("type", "SQL_INJECTION")
                if "BRUTE" in alert_type.upper():
                    lines.append(
                        f"Alert {i+1}: brute force, "
                        f"pattern {a['matched_pattern']}, "
                        f"at {a['timestamp'][:19].replace('T', ' ')}"
                    )
                else:
                    lines.append(
                        f"Alert {i+1}: SQL injection, "
                        f"pattern {a['matched_pattern']}, "
                        f"at {a['timestamp'][:19].replace('T', ' ')}"
                    )
            parts = []
            if blocked:
                parts.append(f"{len(blocked)} IP{'s' if len(blocked) != 1 else ''} blocked")
            if locked:
                parts.append(f"{len(locked)} account{'s' if len(locked) != 1 else ''} locked")
            state_str = (", ".join(parts) + ".") if parts else "no active defenses."
            result = (
                f"Last {len(recent)} alert{'s' if len(recent) != 1 else ''}: "
                + "; ".join(lines)
                + f". Status: {state_str}"
            )

        asyncio.create_task(particle_defense_ok("STATUS_SUCCESS"))
        _record(cmd, "status_report", result)
        logger.info("cmd3 status_report generated")

    # ── cmd 4: lock user account ──────────────────────────────────────────
    elif cmd == 4:
        from defenses.lock_user import lock_user as do_lock_user

        mode = _effective_mode()
        if mode != "DEFENSE_READY":
            return _defense_refused(cmd, mode)

        username = args.get("username")
        ip       = args.get("ip")

        # Try to resolve username from most recent BRUTE_FORCE alert if not given
        if not username:
            for alert in reversed(list(state.alerts)):
                if "BRUTE" in str(alert.get("type", "")).upper() or \
                   "fail" in str(alert.get("matched_pattern", "")).lower():
                    parsed = _parse_username_from_raw(alert.get("raw_request", ""))
                    if parsed:
                        username = parsed
                        ip = ip or alert.get("ip")
                        break

        if not username:
            username = "admin"   # last-resort demo fallback
        if not ip and state.alerts:
            ip = state.alerts[-1]["ip"]

        asyncio.create_task(particle_executing(4, "LOCK_USER"))
        newly_locked = do_lock_user(username, ip or "unknown")
        result = f"Account {username} {'locked by SOC' if newly_locked else 'was already locked'}."
        asyncio.create_task(particle_defense_ok(f"USER_{username}_LOCKED"))
        _record(cmd, "lock_user", result, ip=ip)
        logger.info("cmd4 lock_user: %s", result)

    else:
        asyncio.create_task(particle_denied(f"UNKNOWN_CMD_{cmd}"))
        return {"executed": False, "command": cmd, "result": f"Unknown command {cmd}"}

    return {"executed": True, "command": cmd, "result": result}
