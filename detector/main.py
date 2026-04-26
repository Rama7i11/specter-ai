"""
SPECTER-AI Detector — SQL injection + brute-force detection via Apache log tail.

Replaces Wazuh integrator for actual alerting. Wazuh containers stay up for
visual SOC dashboard eye candy. This service does the real detection work.

Flow:
  bank container writes /var/log/bank/access.log
    → (shared Docker volume)
  detector tails that file
    → two detectors run on every new line
  on hit: POST alert JSON to backend /webhook/wazuh
    → backend stores it + forwards to Argon hardware endpoint
"""

import datetime
import json
import os
import re
import time
from urllib.parse import unquote_plus

import requests

# ── Config from environment ────────────────────────────────────────────────
LOG_PATH       = os.getenv("LOG_PATH",      "/var/log/bank/access.log")
BACKEND_URL    = os.getenv("BACKEND_URL",   "http://host.docker.internal:8000")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET","specter-ai-webhook-secret")
POLL_INTERVAL  = float(os.getenv("POLL_INTERVAL", "0.3"))

# ── SQLi signatures ────────────────────────────────────────────────────────
_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)union[\s%+]+(all[\s%+]+)?select",            "UNION SELECT"),
    (r"(?i)\bor\b[\s'\"01%+]+=[\s'\"01%+]+",            "OR 1=1"),
    (r"(?i)'\s*(or|and)\s+'?\d",                         "OR/AND bypass"),
    (r"--[\s$]|#[\s$]|/\*",                              "SQL comment"),
    (r"(?i)\bsleep\s*\(",                                "SLEEP()"),
    (r"(?i)\bbenchmark\s*\(",                            "BENCHMARK()"),
    (r"(?i)waitfor\s+delay",                             "WAITFOR DELAY"),
    (r"(?i);\s*(drop|insert|update|delete|create)\b",   "stacked query"),
    (r"(?i)\binformation_schema\b",                      "information_schema probe"),
    (r"(?i)\b(schema|database)\s*\(\s*\)",              "schema enumeration"),
    (r"(?i)\bload_file\s*\(",                            "LOAD_FILE()"),
    (r"(?i)\binto\s+outfile\b",                          "INTO OUTFILE"),
]
PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(pat), name) for pat, name in _PATTERNS
]

# ── Alert dedup state ──────────────────────────────────────────────────────
# Suppresses duplicate alerts for the same (ip, raw_request) within 2s.
# Keeps the dashboard clean when one HTTP request matches multiple SQLi
# patterns or is logged repeatedly by the bank container.
RECENT_ALERTS: dict[tuple[str, int], float] = {}   # (ip, hash(raw_request)) -> timestamp
_DEDUP_WINDOW = 2.0    # seconds
_DEDUP_PRUNE  = 60.0   # seconds — prune entries older than this

# ── Brute-force state ──────────────────────────────────────────────────────
# Tracks timestamps of login POSTs per IP over the last 60 seconds.
FAILED_LOGINS_BY_IP: dict[str, list[float]] = {}

_BF_WINDOW   = 60   # seconds
_BF_THRESH   = 5    # attempts in window → alert

# Matches synthetic log lines that check_blocked.php writes for POST params.
# Shape: POST /index.php?username=foo&password=bar HTTP/1.1
_LOGIN_POST_RE  = re.compile(r"POST\s+/index\.php\?username=", re.IGNORECASE)

# Detect SQLi characters inside a username field — skip these for BF counting
# (they're handled by the SQLi detector, not the brute-force detector)
_SQLI_CHARS_RE  = re.compile(r"['\";]|--|\bOR\b|\bUNION\b|\bSELECT\b|\bAND\b", re.IGNORECASE)

# Apache Combined Log: IP - - [date] "METHOD path proto" status size ...
_APACHE_RE = re.compile(r'^(\S+)\s+\S+\s+\S+\s+\[[^\]]+\]\s+"([^"]*)"')


def _parse_line(line: str) -> tuple[str | None, str | None, str | None]:
    """Return (source_ip, raw_request, decoded_request) or (None, None, None)."""
    m = _APACHE_RE.match(line)
    if not m:
        return None, None, None
    ip  = m.group(1)
    raw = m.group(2)
    # Double-decode: catches both single- and double-encoded payloads
    decoded = unquote_plus(unquote_plus(raw))
    return ip, raw, decoded


def _first_sqli_match(request_decoded: str) -> str | None:
    """Return the name of the first matching SQLi pattern, or None."""
    for pattern, name in PATTERNS:
        if pattern.search(request_decoded):
            return name
    return None


def _detect_brute_force(ip: str, raw_request: str) -> dict | None:
    """
    Track login POST attempts per IP. Ignores requests containing SQLi payloads
    (those are handled by the SQLi detector).

    Returns a BRUTE_FORCE alert dict once _BF_THRESH attempts accumulate within
    _BF_WINDOW seconds; resets the counter so the next _BF_THRESH attempts can
    trigger a second alert.
    """
    if not _LOGIN_POST_RE.search(raw_request):
        return None

    # Extract and decode the username value
    username_m = re.search(r"username=([^&\s\"]+)", raw_request, re.IGNORECASE)
    if not username_m:
        return None
    username = unquote_plus(username_m.group(1))

    # Skip SQLi payloads — the SQLi detector handles those
    if _SQLI_CHARS_RE.search(username):
        return None

    now    = time.time()
    bucket = FAILED_LOGINS_BY_IP.setdefault(ip, [])
    bucket.append(now)
    # Prune stale timestamps
    FAILED_LOGINS_BY_IP[ip] = [t for t in bucket if now - t <= _BF_WINDOW]

    if len(FAILED_LOGINS_BY_IP[ip]) >= _BF_THRESH:
        FAILED_LOGINS_BY_IP[ip] = []   # reset so the next burst can trigger
        return {
            "type":            "BRUTE_FORCE",
            "ip":              ip,
            "severity":        7,
            "timestamp":       datetime.datetime.utcnow().isoformat() + "Z",
            "raw_request":     raw_request,
            "matched_pattern": "5_failures_in_60s",
        }
    return None


def _send_alert(alert: dict) -> None:
    """POST a completed alert dict to the backend webhook, with dedup."""
    ip          = alert["ip"]
    raw_request = alert.get("raw_request", "")
    now         = time.time()
    key         = (ip, hash(raw_request))

    last = RECENT_ALERTS.get(key)
    if last is not None and now - last < _DEDUP_WINDOW:
        print(f"[DEDUP] skipping duplicate alert for {ip}", flush=True)
        return
    RECENT_ALERTS[key] = now

    # Prune stale entries so the dict doesn't grow unbounded.
    stale = [k for k, t in RECENT_ALERTS.items() if now - t > _DEDUP_PRUNE]
    for k in stale:
        RECENT_ALERTS.pop(k, None)

    try:
        r = requests.post(
            f"{BACKEND_URL}/webhook/wazuh",
            json=alert,
            headers={"X-Auth-Token": WEBHOOK_SECRET, "Content-Type": "application/json"},
            timeout=5,
        )
        print(
            f"[ALERT] type={alert.get('type','?')}  ip={alert['ip']}"
            f"  match={alert['matched_pattern']}  backend={r.status_code}",
            flush=True,
        )
    except requests.RequestException as exc:
        print(f"[ERROR] backend unreachable: {exc}", flush=True)


def _wait_for_log() -> None:
    while not os.path.exists(LOG_PATH):
        print(f"[WAIT] {LOG_PATH} not found — waiting for bank container to start...", flush=True)
        time.sleep(5)


def _tail() -> None:
    """Tail LOG_PATH indefinitely, running both detectors on every new line."""
    _wait_for_log()
    print(f"[DETECTOR] Tailing {LOG_PATH}", flush=True)

    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
        fh.seek(0, 2)  # start at end — ignore historical lines
        while True:
            line = fh.readline()
            if line:
                line = line.rstrip("\n")
                ip, raw_request, decoded_request = _parse_line(line)
                if ip and raw_request:
                    # ── SQLi detector ──────────────────────────────────────
                    if decoded_request:
                        matched = _first_sqli_match(decoded_request)
                        if matched:
                            _send_alert({
                                "type":            "SQL_INJECTION",
                                "ip":              ip,
                                "severity":        10,
                                "timestamp":       datetime.datetime.utcnow().isoformat() + "Z",
                                "raw_request":     line,
                                "matched_pattern": matched,
                            })

                    # ── Brute-force detector ───────────────────────────────
                    bf = _detect_brute_force(ip, raw_request)
                    if bf:
                        _send_alert(bf)
            else:
                # Detect log rotation (file truncated or replaced)
                try:
                    current_pos = fh.tell()
                    file_size   = os.path.getsize(LOG_PATH)
                    if current_pos > file_size:
                        print("[DETECTOR] Log rotated — seeking to start of new file", flush=True)
                        fh.seek(0)
                except FileNotFoundError:
                    print("[DETECTOR] Log file disappeared — reopening", flush=True)
                    return  # outer loop will reopen

                time.sleep(POLL_INTERVAL)


def main() -> None:
    print("[DETECTOR] SPECTER-AI detector starting...", flush=True)
    print(f"[DETECTOR] Watching : {LOG_PATH}", flush=True)
    print(f"[DETECTOR] Backend  : {BACKEND_URL}", flush=True)
    while True:
        try:
            _tail()
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] {exc} — restarting in 5s", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
