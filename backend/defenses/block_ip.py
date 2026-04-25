"""
block_ip.py — Manage the IP blocklist shared with the bank container.

Writes to data/blocked_ips.json at the repo root.
The bank container bind-mounts that file as /data/blocked_ips.json and checks
it on every request via check_blocked.php.
"""

import json
import os
from pathlib import Path

# Resolve repo root regardless of where the backend process is started from
_REPO_ROOT     = Path(__file__).parent.parent.parent.resolve()
BLOCKED_FILE   = Path(os.getenv("BLOCKED_IPS_FILE", str(_REPO_ROOT / "data" / "blocked_ips.json")))


def _load() -> list[str]:
    if BLOCKED_FILE.exists():
        try:
            data = json.loads(BLOCKED_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save(ips: list[str]) -> None:
    BLOCKED_FILE.parent.mkdir(parents=True, exist_ok=True)
    BLOCKED_FILE.write_text(json.dumps(ips, indent=2), encoding="utf-8")


def block_ip(ip: str) -> bool:
    """Add *ip* to the blocklist. Returns True if it was newly added."""
    ips = _load()
    if ip in ips:
        return False
    ips.append(ip)
    _save(ips)
    return True


def unblock_ip(ip: str) -> bool:
    """Remove *ip* from the blocklist. Returns True if it was present."""
    ips = _load()
    if ip not in ips:
        return False
    ips.remove(ip)
    _save(ips)
    return True


def unblock_all() -> int:
    """Clear all blocks. Returns the number of IPs removed."""
    ips = _load()
    _save([])
    return len(ips)


def get_blocked() -> list[str]:
    return _load()
