# start-voice.ps1 — Set up venv and launch SPECTER-AI voice listener
# Run from repo root: .\scripts\start-voice.ps1

$ErrorActionPreference = 'Stop'
$VoiceDir = Join-Path $PSScriptRoot '..\voice'

Push-Location $VoiceDir

# ── Create venv if missing ────────────────────────────────────────────────
if (-not (Test-Path '.venv')) {
    Write-Host "[1/3] Creating Python venv..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "[1/3] venv exists — skipping creation." -ForegroundColor Green
}

# ── Activate + install ────────────────────────────────────────────────────
Write-Host "[2/3] Installing dependencies..." -ForegroundColor Yellow
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt --quiet

# ── sounddevice / PortAudio check ─────────────────────────────────────────
$sdOk = python -c "import sounddevice; print(sounddevice.query_devices())" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "sounddevice import failed. Trying pipwin fallback for PortAudio..."
    pip install pipwin --quiet
    pipwin install pyaudio
    Write-Host "Retry: if sounddevice still fails, install PortAudio manually from:"
    Write-Host "  https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio"
}

# ── Show available mic devices ────────────────────────────────────────────
Write-Host ""
Write-Host "[INFO] Available audio devices:" -ForegroundColor DarkCyan
python -c "import sounddevice as sd; [print(f'  [{i}] {d[\"name\"]}') for i,d in enumerate(sd.query_devices())]" 2>$null
Write-Host ""
Write-Host "  To use a specific device, set SOUNDDEVICE_INDEX=<n> in .env" -ForegroundColor DarkGray

# ── Launch ────────────────────────────────────────────────────────────────
Write-Host "[3/3] Starting voice listener..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Wake word : 'Hey Jarvis' (or 'Hey Specter AI' if custom model present)" -ForegroundColor DarkCyan
Write-Host "  Commands  : 'run command one / two / three'" -ForegroundColor DarkCyan
Write-Host "  Backend   : http://localhost:8000" -ForegroundColor DarkCyan
Write-Host ""

python listener.py

Pop-Location
