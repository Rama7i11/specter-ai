"""
lock_user.py — Manage the account lockout list shared with the bank container.

Writes to data/locked_users.json at repo root.
The bank container checks it via check_blocked.php on every POST login request.
"""

import datetime
import json
import os
from pathlib import Path

_REPO_ROOT  = Path(__file__).parent.parent.parent.resolve()
LOCKED_FILE = Path(os.getenv("LOCKED_USERS_FILE", str(_REPO_ROOT / "data" / "locked_users.json")))


def _load() -> list[dict]:
    if LOCKED_FILE.exists():
        try:
            data = json.loads(LOCKED_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save(entries: list[dict]) -> None:
    LOCKED_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCKED_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def lock_user(username: str, by_ip: str) -> bool:
    """Lock *username*. Returns True if newly locked, False if already locked."""
    entries = _load()
    if any(e["username"] == username for e in entries):
        return False
    entries.append({
        "username":  username,
        "locked_at": datetime.datetime.utcnow().isoformat() + "Z",
        "by_ip":     by_ip,
    })
    _save(entries)
    return True


def unlock_all() -> int:
    """Unlock all accounts. Returns the count unlocked."""
    entries = _load()
    _save([])
    return len(entries)


def get_locked() -> list[dict]:
    return _load()
