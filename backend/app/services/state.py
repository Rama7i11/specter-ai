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

_alert_counter: int = 0


def next_alert_id() -> int:
    global _alert_counter
    _alert_counter += 1
    return _alert_counter
