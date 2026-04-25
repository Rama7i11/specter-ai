"""
SPECTER-AI Detector — lightweight SQL injection detection via Apache log tail.

Replaces Wazuh integrator for actual alerting. Wazuh containers stay up for
visual SOC dashboard eye candy. This service does the real detection work.

Flow:
  bank container writes /var/log/bank/access.log
    → (shared Docker volume)
  detector tails that file
    → regex match on each new line
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
LOG_PATH      = os.getenv("LOG_PATH",      "/var/log/bank/access.log")
BACKEND_URL   = os.getenv("BACKEND_URL",   "http://host.docker.internal:8000")
WEBHOOK_SECRET= os.getenv("WEBHOOK_SECRET","specter-ai-webhook-secret")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "0.3"))

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

# Apache Combined Log: IP - - [date] "METHOD path proto" status size ...
_APACHE_RE = re.compile(r'^(\S+)\s+\S+\s+\S+\s+\[[^\]]+\]\s+"([^"]*)"')


def _parse_line(line: str) -> tuple[str | None, str | None, str | None]:
    """Return (source_ip, raw_request, decoded_request) or (None, None, None)."""
    m = _APACHE_RE.match(line)
    if not m:
        return None, None, None
    ip  = m.group(1)
    raw = m.group(2)
    # Double-decode: catches both single-encoded and double-encoded payloads
    # e.g. %2527 → %27 → '   or   admin%27+OR+%271%27%3D%271 → admin' OR '1'='1
    decoded = unquote_plus(unquote_plus(raw))
    return ip, raw, decoded


def _first_match(request_decoded: str) -> str | None:
    """Return the name of the first matching SQLi pattern, or None.
    Always called with the decoded request string."""
    for pattern, name in PATTERNS:
        if pattern.search(request_decoded):
            return name
    return None


def _send_alert(ip: str, raw_line: str, matched: str) -> None:
    alert = {
        "type": "SQL_INJECTION",
        "ip": ip,
        "severity": 10,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "raw_request": raw_line,
        "matched_pattern": matched,
    }
    try:
        r = requests.post(
            f"{BACKEND_URL}/webhook/wazuh",
            json=alert,
            headers={"X-Auth-Token": WEBHOOK_SECRET, "Content-Type": "application/json"},
            timeout=5,
        )
        print(f"[ALERT] ip={ip}  match={matched}  backend={r.status_code}", flush=True)
    except requests.RequestException as exc:
        print(f"[ERROR] backend unreachable: {exc}", flush=True)


def _wait_for_log() -> None:
    while not os.path.exists(LOG_PATH):
        print(f"[WAIT] {LOG_PATH} not found — waiting for bank container to start...", flush=True)
        time.sleep(5)


def _tail() -> None:
    """Tail LOG_PATH indefinitely, sending alerts on SQLi matches."""
    _wait_for_log()
    print(f"[DETECTOR] Tailing {LOG_PATH}", flush=True)

    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
        fh.seek(0, 2)  # start at end — ignore historical lines
        while True:
            line = fh.readline()
            if line:
                line = line.rstrip("\n")
                ip, raw_request, decoded_request = _parse_line(line)
                if ip and decoded_request:
                    matched = _first_match(decoded_request)
                    if matched:
                        _send_alert(ip, line, matched)
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
