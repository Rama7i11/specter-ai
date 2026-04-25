# SPECTER-AI — Wearable SOAR Backend (Team Aegis)

## System Overview

```
[Attacker] ──SQLi──▶ [Lab: Apache/PHP Bank App]
                           │ Apache logs
                           ▼
                      [Wazuh SIEM] ──webhook──▶ [Backend: FastAPI]
                                                      │
                              ┌───────────────────────┼──────────────────────┐
                              ▼                        ▼                      ▼
                    [Hardware: Argon]       [Gemini Live API]        [MySQL: block/reset]
                              │                        ▲
                    (LED/buzzer alert)                 │
                                              [Voice: OpenWakeWord]
                                              "Hey Specter AI" ──WS──▶
```

## Run Order

> Run each step in a separate PowerShell terminal. Do NOT skip steps.

### Step 1 — Start the lab (Wazuh + Bank + MySQL)
```powershell
.\scripts\start-lab.ps1
```
Wait ~3 minutes for Wazuh to fully initialize. Check:
```powershell
docker compose -f lab/docker-compose.yml ps
```
All services should show `healthy`.

### Step 2 — Seed demo data
```powershell
# Once backend is running:
curl http://localhost:8000/demo/seed
```

### Step 3 — Start the backend
```powershell
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 4 — Expose via ngrok (for hardware team)
```powershell
ngrok http 8000
# Copy the https URL → paste into .env NGROK_URL
```

### Step 5 — Start voice listener
```powershell
cd voice
python listener.py
# Say "Hey Specter AI" to activate
```

### Step 6 — Run the attack
```powershell
.\scripts\run-attack.ps1
```

### Step 7 — Reset for next demo run
```powershell
.\scripts\reset-demo.ps1
# Or: curl -X POST http://localhost:8000/demo/reset
```

---

## Component Map

| Directory   | What it does |
|-------------|-------------|
| `/lab`      | Docker Compose: Wazuh single-node + MySQL + PHP bank app |
| `/lab/bank` | Intentionally vulnerable PHP bank (SQLi target) |
| `/attacker` | Python script that automates SQL injection against the bank |
| `/wazuh`    | Custom decoder/rules + active-response script |
| `/backend`  | FastAPI SOAR backend (webhooks, voice bridge, defensive commands) |
| `/voice`    | OpenWakeWord listener → Gemini Live API bridge |
| `/scripts`  | PowerShell helpers for start/attack/reset |

---

## Common Windows/Docker Issues

### Wazuh containers restart-loop on first boot
Wazuh generates certificates on first run. Give it 2–3 minutes. If still looping:
```powershell
docker compose -f lab/docker-compose.yml logs wazuh.manager | tail -50
```

### Port 1514/1515 already in use
Another Wazuh instance may be running. Kill it:
```powershell
docker ps -a | grep wazuh
docker rm -f <container_id>
```

### MySQL connection refused from backend
The bank app and backend both connect to MySQL. Ensure `MYSQL_HOST=localhost` (host-mode) or use the container service name if running backend inside Docker.

### ngrok "session limit" error
Free ngrok allows 1 simultaneous tunnel. Kill any existing ngrok process:
```powershell
Get-Process ngrok | Stop-Process -Force
```

### OpenWakeWord ONNX model not found
The voice listener falls back to `hey_jarvis` if a custom model is absent. See `/voice/README.md`.

### Active Response not executing
Ensure the Wazuh agent on the target container has the `firewall-drop` AR script deployed. Check:
```powershell
docker exec -it lab-wazuh.manager-1 /var/ossec/bin/agent_control -l
```

---

## Environment Variables

Copy `.env.example` → `.env` and fill in all values before starting any component.

Required before demo:
- `GEMINI_API_KEY`
- `WAZUH_API_PASS` (from Wazuh dashboard first-run setup)
- `HARDWARE_ENDPOINT` (from hardware team)
- `NGROK_URL` (after running ngrok)
