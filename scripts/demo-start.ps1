# demo-start.ps1 - One-command SPECTER-AI demo setup
# Run from repo root: .\scripts\demo-start.ps1
#
# Opens four windows (Lab, Backend, ngrok, Voice). Resilient: never aborts on
# slow services - prints a final dashboard with green/yellow/red status per
# component so the operator can see at a glance what is healthy.

param(
    [string]$BackendUrl  = "http://localhost:8000",
    [string]$BankUrl     = "http://localhost:8080",
    [int]   $BankWait    = 240,   # seconds to poll bank app
    [int]   $BackendWait = 60,    # seconds to poll backend /health
    [int]   $NgrokWait   = 30,    # seconds to poll ngrok local API
    [switch]$SkipLab,             # pass if Docker lab is already running
    [switch]$SkipVoice            # pass to skip the voice listener window
)

$ErrorActionPreference = 'Continue'
$RepoRoot   = Split-Path $PSScriptRoot -Parent
$ScriptsDir = $PSScriptRoot

function _ok($t)   { Write-Host "  [OK] $t"   -ForegroundColor Green }
function _warn($t) { Write-Host "  [!]  $t"   -ForegroundColor Yellow }
function _fail($t) { Write-Host "  [X]  $t"   -ForegroundColor Red }
function _info($t) { Write-Host "       $t"   -ForegroundColor DarkGray }

function Launch-Window($title, $scriptPath) {
    $cmd = "[Console]::Title='$title'; & '$scriptPath'"
    Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", $cmd
}

function Test-BankUp {
    param([string]$Url)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        return ($r.StatusCode -lt 500)
    } catch { return $false }
}

function Test-BackendUp {
    param([string]$Url)
    try {
        $r = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 3 -ErrorAction Stop
        return ($r.status -eq "ok")
    } catch { return $false }
}

function Test-NgrokUp {
    param([string]$Url)
    if (-not $Url) { return $false }
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop
        return ($r.StatusCode -lt 500)
    } catch { return $false }
}

function Test-LabRunning {
    try {
        $names = docker ps --format "{{.Names}}" 2>$null
        if (-not $names) { return $false }
        return ($names -match "wazuh|bank|mysql")
    } catch { return $false }
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
$NgrokFile   = Join-Path $DataDir  'ngrok-url.txt'

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

$labAlreadyRunning = Test-LabRunning

if ($SkipLab) {
    _ok "Skipped (-SkipLab flag)"
} elseif ($labAlreadyRunning) {
    _ok "Lab already running, skipping Docker step"
} else {
    $labScript = Join-Path $ScriptsDir 'start-lab.ps1'
    Launch-Window "SPECTER - Lab" $labScript
    _ok "Lab window opened - waiting for bank app at $BankUrl (up to ${BankWait}s)"
}

$bankReady = $false
$elapsed   = 0
Write-Host -NoNewline "       "
while ($elapsed -lt $BankWait) {
    if (Test-BankUp $BankUrl) { $bankReady = $true; break }
    Start-Sleep 5
    $elapsed += 5
    Write-Host -NoNewline "." -ForegroundColor DarkGray
    if ($elapsed % 30 -eq 0) {
        Write-Host -NoNewline " (${elapsed}s)" -ForegroundColor DarkGray
    }
}
Write-Host ""

if ($bankReady) {
    _ok "Bank app is up at $BankUrl"
} else {
    _warn "Bank not responding yet - continuing with backend startup. Bank will likely come up in background."
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
    if (Test-BackendUp $BackendUrl) { $backendReady = $true; break }
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

    if ($ngrokUrl) {
        _ok "Tunnel: $ngrokUrl"
        $ngrokUrl | Out-File $NgrokFile -Encoding ASCII
        _info "URL saved to data/ngrok-url.txt"
    } else {
        _warn "Could not fetch ngrok URL within ${NgrokWait}s - check ngrok window"
    }
} else {
    _warn "Skipped (ngrok not in PATH)"
}

# --- STEP 6: voice listener ---
Write-Host ""
Write-Host "  [6/8] Voice listener" -ForegroundColor Cyan

$voiceLaunched = $false
if ($SkipVoice) {
    _ok "Skipped (-SkipVoice flag)"
} else {
    $voiceScript = Join-Path $ScriptsDir 'start-voice.ps1'
    if (Test-Path $voiceScript) {
        Launch-Window "SPECTER - Voice" $voiceScript
        _ok "Voice listener window opened"
        $voiceLaunched = $true
        Start-Sleep 2
    } else {
        _warn "start-voice.ps1 not found - skipping"
    }
}

# --- STEP 7: reset + seed demo state ---
Write-Host ""
Write-Host "  [7/8] Reset + seed demo state" -ForegroundColor Cyan

if ($backendReady) {
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
} else {
    _warn "Backend not ready - skipping reset/seed (run reset-demo.ps1 once it is up)"
}

# --- STEP 8: dashboard (re-probe at print time) ---
Write-Host ""
Write-Host "  [8/8] Final status probe" -ForegroundColor Cyan

$bankFinal     = Test-BankUp    $BankUrl
$backendFinal  = Test-BackendUp $BackendUrl
$ngrokFinal    = Test-NgrokUp   $ngrokUrl
$socUrl        = "$BackendUrl/dashboards/soc/"
$socFinal      = $false
try {
    $rsoc = Invoke-WebRequest -Uri $socUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $socFinal = ($rsoc.StatusCode -lt 500)
} catch {}

$voicePid = $null
$voiceProcs = Get-Process | Where-Object {
    ($_.MainWindowTitle -eq "SPECTER - Voice") -or
    ($_.ProcessName -match "python" -and $_.MainWindowTitle -match "Specter|Voice")
}
if ($voiceProcs) { $voicePid = ($voiceProcs | Select-Object -First 1).Id }
$voiceFinal = ($voiceLaunched -and $voicePid)

$hwMode = "UNKNOWN"
if ($backendFinal) {
    try {
        $status = Invoke-RestMethod -Uri "$BackendUrl/api/status" -TimeoutSec 3 -ErrorAction Stop
        $hwMode = $status.hardware_mode
    } catch {}
}

function _statusTag {
    param([bool]$ok, [bool]$wait)
    if ($ok)        { return @{ Text = "[ OK ]"; Color = "Green"  } }
    elseif ($wait)  { return @{ Text = "[WAIT]"; Color = "Yellow" } }
    else            { return @{ Text = "[FAIL]"; Color = "Red"    } }
}

function _writeLine {
    param($tag, $label, $value)
    Write-Host -NoNewline "  "
    Write-Host -NoNewline $tag.Text -ForegroundColor $tag.Color
    Write-Host ("  {0,-12} {1}" -f $label, $value) -ForegroundColor White
}

$div  = "  ==========================================="
$sep  = "  -------------------------------------------"

$ngrokDisplay = if ($ngrokUrl) { $ngrokUrl } else { "(not available)" }
$voiceDisplay = if ($voiceFinal) { "running (PID $voicePid)" }
                elseif ($SkipVoice) { "skipped (-SkipVoice)" }
                elseif ($voiceLaunched) { "window opened (PID not detected)" }
                else { "not started" }

$bankTag    = _statusTag $bankFinal    (-not $bankFinal)
$backTag    = _statusTag $backendFinal (-not $backendFinal)
$ngrokTag   = if ($ngrokUrl) {
                  _statusTag $ngrokFinal (-not $ngrokFinal)
              } else { @{ Text = "[FAIL]"; Color = "Red" } }
$voiceTag   = if ($SkipVoice) { @{ Text = "[ -- ]"; Color = "DarkGray" } }
              elseif ($voiceFinal) { @{ Text = "[ OK ]"; Color = "Green" } }
              elseif ($voiceLaunched) { @{ Text = "[WAIT]"; Color = "Yellow" } }
              else { @{ Text = "[FAIL]"; Color = "Red" } }
$socTag     = _statusTag $socFinal (-not $socFinal)

Write-Host ""
Write-Host $div -ForegroundColor Cyan
Write-Host "        SPECTER-AI  |  DEMO READY" -ForegroundColor Cyan
Write-Host $div -ForegroundColor Cyan
_writeLine $bankTag  "Bank"        $BankUrl
_writeLine $backTag  "Backend"     "$BackendUrl/api/status"
_writeLine $ngrokTag "ngrok"       $ngrokDisplay
_writeLine $voiceTag "Voice"       $voiceDisplay
_writeLine $socTag   "SOC POV"     $socUrl
Write-Host $sep -ForegroundColor Cyan
Write-Host ("  Wearable mode:      {0}" -f $hwMode) -ForegroundColor White
Write-Host  "  PagerDuty:          https://moeabushamma.pagerduty.com/incidents" -ForegroundColor White
Write-Host $div -ForegroundColor Cyan
Write-Host ""

if ($ngrokUrl) {
    Write-Host ""
    Write-Host "  ===== NGROK PUBLIC URL (share with hardware teammate) =====" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "      $ngrokUrl" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "      (also saved to data/ngrok-url.txt)" -ForegroundColor DarkGray
    Write-Host "  ===========================================================" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "  RUN ATTACK:  .\scripts\run-attack.ps1 sqli|brute" -ForegroundColor DarkYellow
Write-Host "  RESET DEMO:  .\scripts\reset-demo.ps1"            -ForegroundColor DarkYellow
Write-Host "  STOP ALL:    .\scripts\demo-stop.ps1"             -ForegroundColor DarkYellow
Write-Host ""
