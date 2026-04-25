# demo-start.ps1 - One-command SPECTER-AI demo setup
# Run from repo root: .\scripts\demo-start.ps1
#
# Opens four windows (Lab, Backend, ngrok, Voice), waits for each to be ready,
# resets + seeds demo state, then prints the live dashboard.

param(
    [string]$BackendUrl  = "http://localhost:8000",
    [string]$BankUrl     = "http://localhost:8080",
    [int]   $BackendWait = 45,    # seconds to poll backend /health
    [int]   $NgrokWait   = 20,    # seconds to poll ngrok local API
    [switch]$SkipLab,             # pass if Docker lab is already running
    [switch]$SkipVoice            # pass to skip the voice listener window
)

$ErrorActionPreference = 'Continue'
$RepoRoot   = Split-Path $PSScriptRoot -Parent
$ScriptsDir = $PSScriptRoot

function _ok($t)   { Write-Host "  [OK] $t" -ForegroundColor Green }
function _warn($t) { Write-Host "  [!]  $t" -ForegroundColor Yellow }
function _fail($t) { Write-Host "  [X]  $t" -ForegroundColor Red }
function _info($t) { Write-Host "       $t" -ForegroundColor DarkGray }

function Launch-Window($title, $scriptPath) {
    $cmd = "[Console]::Title='$title'; & '$scriptPath'"
    Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", $cmd
}

# --- STEP 1: pre-flight checks ---
Write-Host ""
Write-Host "  SPECTER-AI - DEMO STARTUP" -ForegroundColor Magenta
Write-Host ""
Write-Host "  [1/8] Pre-flight checks" -ForegroundColor Cyan

$prereqOk = $true

try { docker info 2>$null | Out-Null; _ok "Docker is running" }
catch { _fail "Docker Desktop not running - start it first"; $prereqOk = $false }

if (Get-Command ngrok -ErrorAction SilentlyContinue) { _ok "ngrok in PATH" }
else { _warn "ngrok not found - tunnel step will be skipped" }

if (Get-Command python -ErrorAction SilentlyContinue) { _ok "Python in PATH" }
else { _fail "Python not found in PATH"; $prereqOk = $false }

if (-not $prereqOk) {
    _fail "Fix the issues above and re-run."
    exit 1
}

# --- STEP 2: data files ---
Write-Host ""
Write-Host "  [2/8] Initializing data files" -ForegroundColor Cyan

$DataDir     = Join-Path $RepoRoot 'data'
$BlockedFile = Join-Path $DataDir  'blocked_ips.json'
$LockedFile  = Join-Path $DataDir  'locked_users.json'

if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Path $DataDir | Out-Null }

if (-not (Test-Path $BlockedFile)) {
    '[]' | Out-File $BlockedFile -Encoding ASCII
    _ok "Created data/blocked_ips.json"
} else { _ok "data/blocked_ips.json exists" }

if (-not (Test-Path $LockedFile)) {
    '[]' | Out-File $LockedFile -Encoding ASCII
    _ok "Created data/locked_users.json"
} else { _ok "data/locked_users.json exists" }

# --- STEP 3: lab (Docker Compose) ---
Write-Host ""
Write-Host "  [3/8] Lab (Docker Compose)" -ForegroundColor Cyan

if ($SkipLab) {
    _ok "Skipped (-SkipLab flag)"
} else {
    $labScript = Join-Path $ScriptsDir 'start-lab.ps1'
    Launch-Window "SPECTER - Lab" $labScript
    _ok "Lab window opened - waiting for bank app at $BankUrl ..."

    $labReady = $false
    for ($i = 0; $i -lt 24; $i++) {
        Start-Sleep 10
        try {
            $r = Invoke-WebRequest -Uri $BankUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($r.StatusCode -lt 500) { $labReady = $true; break }
        } catch {}
        _info "...still waiting ($($($i+1)*10)s)"
    }

    if ($labReady) { _ok "Bank app is up at $BankUrl" }
    else            { _warn "Bank app did not respond within 240s - continuing anyway" }
}

# --- STEP 4: backend (FastAPI) ---
Write-Host ""
Write-Host "  [4/8] Backend (FastAPI)" -ForegroundColor Cyan

$backendScript = Join-Path $ScriptsDir 'start-backend.ps1'
Launch-Window "SPECTER - Backend" $backendScript
_ok "Backend window opened - polling $BackendUrl/health ..."

$backendReady = $false
for ($i = 0; $i -lt $BackendWait; $i++) {
    Start-Sleep 1
    try {
        $r = Invoke-RestMethod -Uri "$BackendUrl/health" -ErrorAction Stop
        if ($r.status -eq "ok") { $backendReady = $true; break }
    } catch {}
    if (($i % 5) -eq 4) { _info "...waiting ($($i+1)s)" }
}

if ($backendReady) { _ok "Backend is up" }
else               { _warn "Backend did not respond within ${BackendWait}s - continuing anyway" }

# --- STEP 5: ngrok ---
Write-Host ""
Write-Host "  [5/8] ngrok tunnel" -ForegroundColor Cyan

$ngrokUrl = $null
if (Get-Command ngrok -ErrorAction SilentlyContinue) {
    Start-Process ngrok -ArgumentList "http 8000"
    _ok "ngrok process started - polling localhost:4040 ..."

    for ($i = 0; $i -lt $NgrokWait; $i++) {
        Start-Sleep 1
        try {
            $tunnels = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -ErrorAction Stop
            $https   = $tunnels.tunnels | Where-Object { $_.proto -eq "https" }
            if ($https) { $ngrokUrl = $https[0].public_url; break }
        } catch {}
    }

    if ($ngrokUrl) { _ok "Tunnel: $ngrokUrl" }
    else            { _warn "Could not fetch ngrok URL - check ngrok window" }
} else {
    _warn "Skipped (ngrok not in PATH)"
}

# --- STEP 6: voice listener ---
Write-Host ""
Write-Host "  [6/8] Voice listener" -ForegroundColor Cyan

if ($SkipVoice) {
    _ok "Skipped (-SkipVoice flag)"
} else {
    $voiceScript = Join-Path $ScriptsDir 'start-voice.ps1'
    Launch-Window "SPECTER - Voice" $voiceScript
    _ok "Voice listener window opened"
    Start-Sleep 2
}

# --- STEP 7: reset + seed demo state ---
Write-Host ""
Write-Host "  [7/8] Reset + seed demo state" -ForegroundColor Cyan

try {
    Invoke-RestMethod -Uri "$BackendUrl/demo/reset" -Method Post -ErrorAction Stop | Out-Null
    _ok "In-memory state reset"
} catch {
    _warn "Could not call /demo/reset - backend may still be starting"
}

try {
    $seed = Invoke-RestMethod -Uri "$BackendUrl/demo/seed" -Method Post -ErrorAction Stop
    if ($seed.seeded) { _ok "Bank DB seeded ($($seed.users) users)" }
    else               { _warn "DB seed error: $($seed.error)" }
} catch {
    _warn "Could not call /demo/seed - lab (MySQL) may still be starting"
}

# --- STEP 8: dashboard ---
Write-Host ""
Write-Host "  [8/8] Demo dashboard" -ForegroundColor Cyan

$ngrokDisplay = if ($ngrokUrl) { $ngrokUrl } else { "(see ngrok window)" }
$hwMode = "UNKNOWN"
try {
    $status = Invoke-RestMethod -Uri "$BackendUrl/api/status" -ErrorAction Stop
    $hwMode = $status.hardware_mode
} catch {}

$div  = "  ====================================================="
$sep  = "  -----------------------------------------------------"

Write-Host ""
Write-Host $div  -ForegroundColor Cyan
Write-Host "        SPECTER-AI  DEMO READY" -ForegroundColor Cyan
Write-Host $div  -ForegroundColor Cyan
Write-Host "  Bank:          $BankUrl" -ForegroundColor Cyan
Write-Host "  Backend:       $BackendUrl/api/status" -ForegroundColor Cyan
Write-Host "  ngrok:         $ngrokDisplay" -ForegroundColor Cyan
Write-Host "  Wearable mode: $hwMode" -ForegroundColor Cyan
Write-Host $sep  -ForegroundColor Cyan
Write-Host "  RUN ATTACK:  .\scripts\run-attack.ps1 sqli|brute" -ForegroundColor Yellow
Write-Host "  RESET DEMO:  .\scripts\reset-demo.ps1" -ForegroundColor Yellow
Write-Host "  STOP ALL:    .\scripts\demo-stop.ps1" -ForegroundColor Yellow
Write-Host $div  -ForegroundColor Cyan
Write-Host ""
