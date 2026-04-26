"""
Shared in-process state. Imported by all routers.
load_dotenv() is called in main.py before any router import, so os.getenv
values are already populated by the time this module is first used.
"""

import os
import time
from collections import deque

WEBHOOK_SECRET    = os.getenv("WEBHOOK_SECRET",    "specter-ai-webhook-secret")
HARDWARE_ENDPOINT = os.getenv("HARDWARE_ENDPOINT", "")

# ── In-memory stores ──────────────────────────────────────────────────────
alerts:     deque[dict] = deque(maxlen=100)
attack_log: deque[str]  = deque(maxlen=50)
defenses:   deque[dict] = deque(maxlen=100)

START_TIME:      float       = time.time()
last_alert_time: float | None = None

# ── Hardware mode (updated by POST /api/heartbeat) ────────────────────────
HARDWARE_MODE:        str         = "UNKNOWN"   # MONITOR | ALERT_ONLY | DEFENSE_READY | UNKNOWN
last_heartbeat_time:  float | None = None
HEARTBEAT_TIMEOUT:    int          = 60         # seconds — treat as UNKNOWN if exceeded

# ── Specter voice state (updated by POST /voice/state from listener) ──────
SPECTER_STATE:         str   = "ASLEEP"   # ASLEEP | LISTENING | THINKING | HACKING
SPECTER_VOICE_LEVEL:   float = 0.0        # 0.0 .. 1.0
SPECTER_STATE_UPDATED: float = 0.0

# ── Wake button (updated by POST /voice/wake) ─────────────────────────────
WAKE_REQUESTED:    bool        = False
wake_requested_at: float | None = None
WAKE_EXPIRY:       int          = 10   # seconds — button press expires after this


def consume_wake() -> bool:
    """Atomically read-and-clear the wake flag. Returns True if a valid wake was pending."""
    global WAKE_REQUESTED, wake_requested_at
    if not WAKE_REQUESTED:
        return False
    if wake_requested_at is None or (time.time() - wake_requested_at) > WAKE_EXPIRY:
        WAKE_REQUESTED = False
        wake_requested_at = None
        return False
    WAKE_REQUESTED = False
    wake_requested_at = None
    return True

# ── PagerDuty incidents (created on severity >= 9 alerts) ────────────────
# Each: {"incident_id": str, "alert_id": int, "summary": str,
#        "status": "triggered", "created_at": str}
PAGERDUTY_INCIDENTS: deque[dict] = deque(maxlen=20)

# ── Archive of past demo runs (populated by cmd 2 soft-reset) ─────────────
ALERT_HISTORY:      deque[dict] = deque(maxlen=200)
DEFENSE_HISTORY:    deque[dict] = deque(maxlen=200)
PAGERDUTY_HISTORY:  deque[dict] = deque(maxlen=200)

# Monotonic counters that survive cmd 2 (only /demo/reset zeros them).
# Drives /api/history "X attacks across Y demo runs" framing.
TOTAL_ALERTS_EVER:   int = 0
TOTAL_DEFENSES_EVER: int = 0

# ── Proactive voice briefings ─────────────────────────────────────────────
PENDING_BRIEFINGS: deque[dict]                  = deque(maxlen=20)  # {"alert_id": int, "text": str}
SPOKEN_ALERT_IDS:  set[int]                     = set()             # IDs already dispatched to listener
LAST_BRIEFING_KEY: dict[tuple[str, str], float] = {}                # (type, ip) -> timestamp of last queued briefing
BRIEFING_DEDUP_WINDOW: int                      = 30                # seconds

_alert_counter: int = 0


def next_alert_id() -> int:
    global _alert_counter
    _alert_counter += 1
    return _alert_counter
