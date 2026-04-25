# SPECTER-AI — Wearable SOAR (Team Aegis)

A voice-controlled Security Orchestration, Automation & Response system worn on the wrist.
Detects live attacks against a simulated bank, speaks proactive threat briefings, and executes
defensive countermeasures on voice command — all without touching a keyboard.

---

## Architecture

```
[Attacker scripts]
       │  HTTP POST (SQLi / brute force)
       ▼
[Lab: Apache/PHP Bank App]  ──── Apache access.log
                                        │
                               [Wazuh SIEM]  ──── custom decoder + rules
                                        │
                               webhook POST /webhook/wazuh
                                        │
                          ┌─────────────▼──────────────┐
                          │   Backend (FastAPI :8000)   │
                          │  • alert store (deque)      │
                          │  • geo-IP enrichment        │
                          │  • IP blocklist             │
                          │  • account lockout          │
                          └──────┬────────────┬─────────┘
                                 │            │
               POST /voice/command            │  POST particle.io
                                 │            ▼
                    ┌────────────▼───┐  [Particle Argon wearable]
                    │  Voice bridge  │   LED + buzzer alerts
                    │  (listener.py) │
                    └────────────────┘
                       ▲          │
              OpenWakeWord    OpenAI Realtime API
              "Hey Jarvis"    (GPT-4o Realtime)
```

**Defense flow:** attack → Wazuh alert → backend webhook → proactive voice briefing →
operator says "run command one" → IP blocked in `data/blocked_ips.json` →
PHP gate rejects further requests with 403.

---

## Quick Start (one command)

```powershell
.\scripts\demo-start.ps1
```

This opens four windows (Lab, Backend, ngrok, Voice), waits for each service, resets and seeds
demo state, then prints a live dashboard with all URLs and the current wearable mode.

**Flags:**
| Flag | Effect |
|------|--------|
| `-SkipLab` | Skip Docker Compose step (lab already running) |
| `-SkipVoice` | Skip voice listener window |
| `-BackendWait 60` | Extend backend polling timeout (seconds) |

---

## Manual Start Order

> Only needed if `demo-start.ps1` fails or you want finer control.

```powershell
# Terminal 1 — Lab (Wazuh + bank + MySQL, takes ~3 min first run)
.\scripts\start-lab.ps1

# Terminal 2 — Backend
.\scripts\start-backend.ps1

# Terminal 3 — ngrok tunnel (for wearable)
ngrok http 8000

# Terminal 4 — Voice listener
.\scripts\start-voice.ps1

# Seed bank DB + reset state
Invoke-RestMethod http://localhost:8000/demo/seed  -Method Post
Invoke-RestMethod http://localhost:8000/demo/reset -Method Post
```

---

## Attack Simulations

Run from repo root after the lab and backend are up:

```powershell
# SQL injection only
.\scripts\run-attack.ps1 -type sqli

# Brute force only  (5 failed logins → BRUTE_FORCE alert + cmd 4 locks account)
.\scripts\run-attack.ps1 -type brute

# Both in sequence
.\scripts\run-attack.ps1 -type both

# Against a custom target (e.g. ngrok URL)
.\scripts\run-attack.ps1 -type sqli -Target https://abc123.ngrok.io
```

### What each attack does

| Type | Script | Detects as | Alert pattern |
|------|--------|------------|---------------|
| `sqli` | `attacker/sqli.py` | SQL injection | `UNION SELECT`, `OR 1=1`, etc. |
| `brute` | `attacker/brute_force.py` | Brute force | 5 failed logins within 60 s |

---

## Voice Commands

Wake word: **"Hey Jarvis"**

After Specter speaks a threat briefing or you wake it manually, issue one of:

| Say | Command | What it does | Mode required |
|-----|---------|--------------|---------------|
| "Run command one" | cmd 1 | Block attacker IP — writes to `data/blocked_ips.json` | DEFENSE_READY |
| "Run command two" | cmd 2 | Reset all defenses (unblock IPs, unlock accounts) | DEFENSE_READY |
| "Run command three" | cmd 3 | Status report — recent alerts, active blocks/locks | Any |
| "Run command four" | cmd 4 | Lock attacker's account — writes to `data/locked_users.json` | DEFENSE_READY |

> **Hardware dial modes:** the Particle Argon wearable has a physical dial.
> Commands 1, 2, and 4 are blocked unless the dial is in **DEFENSE_READY** position.
> Command 3 works in any mode.

### Example demo flow

1. Start everything with `.\scripts\demo-start.ps1`
2. Run `.\scripts\run-attack.ps1 -type sqli`
3. Specter speaks: *"Aegis team, this is Specter. SQL injection detected. Source IP one seven two dot nineteen dot zero dot two. Severity ten. Awaiting your command."*
4. Say **"Hey Jarvis"** → *"Run command one"* → attacker IP is blocked
5. Refresh `http://localhost:8080` — bank returns 403
6. Run `.\scripts\run-attack.ps1 -type brute`
7. Specter speaks brute force briefing automatically
8. Say **"Hey Jarvis"** → *"Run command four"* → admin account locked
9. Try logging into the bank as admin — receives 403 Account Locked page

---

## Reset Between Judges

```powershell
.\scripts\reset-demo.ps1
```

Clears: IP blocklist, account lockout list, all in-memory alerts/defenses, pending briefings,
hardware mode, alert counter. Then re-seeds the bank DB with 10 fresh users.

To also stop all processes:
```powershell
.\scripts\demo-stop.ps1          # stops ngrok, uvicorn, voice listener
.\scripts\demo-stop.ps1 -StopLab # also runs docker compose down
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook/wazuh` | Receive Wazuh alert (requires `X-Auth-Token` header) |
| `POST` | `/api/heartbeat` | Wearable heartbeat — updates hardware mode |
| `GET`  | `/api/status` | System status: detector, blocked IPs, locked users, hardware mode |
| `GET`  | `/api/alerts` | All alerts this session |
| `GET`  | `/api/defenses` | All defense actions this session |
| `POST` | `/voice/wake` | Physical wake button pressed |
| `GET`  | `/voice/wake-status` | Check if wake is pending |
| `POST` | `/voice/command` | Execute a voice command `{"command": 1-4, "args": {}}` |
| `GET`  | `/voice/pending-briefing` | Pop next unspoken briefing |
| `POST` | `/demo/reset` | Full state reset (call between judging runs) |
| `POST` | `/demo/seed` | Re-populate bank DB with demo users |
| `GET`  | `/health` | Liveness check |
| `GET`  | `/docs` | Swagger UI |

---

## Directory Map

| Path | Contents |
|------|----------|
| `lab/` | Docker Compose: Wazuh single-node + PHP bank app + MySQL |
| `lab/bank/` | Intentionally vulnerable PHP bank (SQLi + login target) |
| `attacker/` | `sqli.py` and `brute_force.py` attack simulators |
| `backend/` | FastAPI SOAR backend (webhooks, voice bridge, defenses, demo API) |
| `backend/defenses/` | `block_ip.py`, `lock_user.py` — write to `data/*.json` |
| `detector/` | Log-tail process — detects SQLi and brute force, POSTs to backend |
| `voice/` | OpenWakeWord + OpenAI Realtime API voice bridge |
| `wazuh/` | Custom Wazuh decoder, rules, and active-response script |
| `data/` | Runtime JSON files: `blocked_ips.json`, `locked_users.json` |
| `scripts/` | PowerShell helpers: start, stop, attack, reset |

---

## Environment Variables

Copy `.env.example` → `.env` before starting any component.

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key (needs Realtime API access) |
| `OPENAI_REALTIME_MODEL` | No | Default: `gpt-4o-realtime-preview` |
| `PARTICLE_DEVICE_ID` | Yes | Particle Argon device ID |
| `PARTICLE_ACCESS_TOKEN` | Yes | Particle Cloud access token |
| `WEBHOOK_SECRET` | No | Shared secret for `/webhook/wazuh` (default: `specter-ai-webhook-secret`) |
| `MYSQL_HOST` | No | Default: `localhost` |
| `MYSQL_USER` | No | Default: `bankuser` |
| `MYSQL_PASSWORD` | No | Default: `bankpass` |
| `MYSQL_DATABASE` | No | Default: `bankdb` |

---

## Troubleshooting

**Wazuh containers restart-looping on first boot**
Give it 3 minutes — it generates TLS certs on first run. If still looping:
```powershell
docker compose -f lab/docker-compose.yml logs wazuh.manager | tail -50
```

**Port 1514/1515 already in use**
```powershell
docker ps -a | grep wazuh
docker rm -f <id>
```

**Backend can't reach MySQL**
Ensure `MYSQL_HOST=localhost` and the lab containers are healthy:
```powershell
docker compose -f lab/docker-compose.yml ps
```

**ngrok "session limit" error**
```powershell
Get-Process ngrok | Stop-Process -Force
```

**Voice listener exits immediately / no audio device**
Check that a microphone is present and not in use by another app.
Run `python listener.py` directly in the voice window to see the error.

**OpenWakeWord model not found**
Falls back to pretrained `hey_jarvis` automatically — no action needed.
See `voice/README.md` for custom model instructions.

**OpenAI Realtime API 401**
Confirm `OPENAI_API_KEY` in `.env` is valid and has Realtime API access enabled.
