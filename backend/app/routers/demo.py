"""
Demo management endpoints.

POST /demo/reset  — wipe in-memory state + blocked_ips.json. Call before each demo run.
POST /demo/seed   — (re-)populate bankdb with fresh users + transactions.
                    Also callable after /demo/reset to ensure clean DB state.
"""

import logging
import os
import random
from datetime import datetime, timedelta

import pymysql
from fastapi import APIRouter

from app.services import state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/demo")

# ── Demo user roster — matches attacker/sqli.py _FAKE_ROWS so dump looks real ──
_USERS = [
    ("admin",    "admin123",    "System Administrator",   "admin@meridianbank.com",    250_000.00,  "MNB-0000-0001"),
    ("jsmith",   "J$m!th2024",  "John Smith",             "jsmith@meridianbank.com",   48_320.50,   "MNB-1001-4421"),
    ("mwilson",  "W!ls0n99",    "Margaret Wilson",        "mwilson@meridianbank.com",  127_840.00,  "MNB-1002-8834"),
    ("dcarter",  "Cart3r2024",  "David Carter",           "dcarter@meridianbank.com",  9_215.75,    "MNB-1003-2291"),
    ("elee",     "3m!lyL33",    "Emily Lee",              "elee@meridianbank.com",     302_100.00,  "MNB-1004-6670"),
    ("bthomas",  "Bth0m@s1",    "Brian Thomas",           "bthomas@meridianbank.com",  55_890.25,   "MNB-1005-1198"),
    ("agarcia",  "G@rc!a2024",  "Ana Garcia",             "agarcia@meridianbank.com",  18_650.00,   "MNB-1006-3345"),
    ("rjohnson", "R0b3rtJ!",    "Robert Johnson",         "rjohnson@meridianbank.com", 880_000.00,  "MNB-1007-9912"),
    ("lnguyen",  "Ngu3n!2024",  "Lan Nguyen",             "lnguyen@meridianbank.com",  73_400.00,   "MNB-1008-5567"),
    ("kpatel",   "P@t3l2024!",  "Kiran Patel",            "kpatel@meridianbank.com",   441_250.00,  "MNB-1009-0023"),
]

_TXN_POOL = [
    ("Direct Deposit — Payroll",           2_500.00,  "credit"),
    ("ATM Withdrawal",                       200.00,  "debit"),
    ("Online Transfer — Utilities",          145.50,  "debit"),
    ("POS Purchase — Whole Foods",            87.32,  "debit"),
    ("Incoming Wire Transfer",             5_000.00,  "credit"),
    ("POS Purchase — Amazon",               234.99,  "debit"),
    ("Monthly Interest Payment",              12.45,  "credit"),
    ("Mortgage / Rent Payment",           1_850.00,  "debit"),
    ("ATM Deposit",                          500.00,  "credit"),
    ("POS Purchase — Shell Gas",              55.00,  "debit"),
    ("Zelle Transfer — Received",            300.00,  "credit"),
    ("POS Purchase — Starbucks",              12.75,  "debit"),
    ("Subscription — Netflix",                15.99,  "debit"),
    ("Tax Refund — IRS",                   1_200.00,  "credit"),
    ("Insurance Premium — Auto",             220.00,  "debit"),
]


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "bankuser"),
        password=os.getenv("MYSQL_PASSWORD", "bankpass"),
        database=os.getenv("MYSQL_DATABASE", "bankdb"),
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )


@router.post("/seed")
async def demo_seed():
    """Re-populate bankdb with the standard demo roster. Safe to call multiple times."""
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM users")
            cur.execute("ALTER TABLE users AUTO_INCREMENT = 1")

            for username, password, full_name, email, balance, acct_no in _USERS:
                cur.execute(
                    "INSERT INTO users (username, password, full_name, email, balance, account_number) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (username, password, full_name, email, balance, acct_no),
                )
                uid = cur.lastrowid

                # 5–7 plausible transactions per user, spread over the last 30 days
                txns = random.sample(_TXN_POOL, k=random.randint(5, 7))
                for desc, amount, txn_type in txns:
                    ts = datetime.utcnow() - timedelta(
                        days=random.randint(1, 30),
                        hours=random.randint(0, 23),
                        minutes=random.randint(0, 59),
                    )
                    cur.execute(
                        "INSERT INTO transactions (user_id, description, amount, type, created_at) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (uid, desc, amount, txn_type, ts),
                    )
        conn.close()
        logger.info("demo/seed: %d users inserted", len(_USERS))
        return {"seeded": True, "users": len(_USERS)}

    except pymysql.Error as exc:
        logger.error("demo/seed DB error: %s", exc)
        return {"seeded": False, "error": str(exc), "hint": "Is the lab (docker compose) running?"}


@router.post("/reset")
async def demo_reset():
    """
    Full demo reset — call this between judging runs.
    Clears all in-memory + on-disk state so the next run starts clean.
    Does NOT touch MySQL — call /demo/seed after if you also want a clean DB.
    """
    from defenses.block_ip import unblock_all
    from defenses.lock_user import unlock_all

    unblock_all()
    unlock_all()

    state.alerts.clear()
    state.defenses.clear()
    state.attack_log.clear()
    state.PAGERDUTY_INCIDENTS.clear()
    state.PENDING_BRIEFINGS.clear()
    state.SPOKEN_ALERT_IDS.clear()
    state.LAST_BRIEFING_KEY.clear()
    state.last_alert_time     = None
    state.HARDWARE_MODE       = "UNKNOWN"
    state.last_heartbeat_time = None
    state.WAKE_REQUESTED      = False
    state.wake_requested_at   = None
    state._alert_counter      = 0

    logger.info("demo/reset: full state cleared")
    return {
        "reset":   True,
        "cleared": [
            "blocks", "locked_users",
            "alerts", "defenses", "attack_log",
            "pagerduty_incidents",
            "pending_briefings", "spoken_alert_ids", "briefing_dedup_keys",
            "hardware_mode", "alert_counter",
        ],
    }
