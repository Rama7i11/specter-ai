$ErrorActionPreference = 'Stop'
$VoiceDir = Join-Path $PSScriptRoot '..\voice'
Push-Location $VoiceDir

if (-not (Test-Path '.venv')) {
    Write-Host "[1/3] Creating Python venv..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "[1/3] venv exists - skipping creation." -ForegroundColor Green
}

Write-Host "[2/3] Installing dependencies..." -ForegroundColor Yellow
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt --quiet

Write-Host "[3/3] Starting voice listener..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Say 'Hey Jarvis' to wake Specter-AI" -ForegroundColor DarkCyan
Write-Host "  Then issue a command like 'Run command three'" -ForegroundColor DarkCyan
Write-Host ""

python listener.py

Pop-Location
