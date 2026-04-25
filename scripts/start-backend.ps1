$ErrorActionPreference = 'Stop'
$BackendDir = Join-Path $PSScriptRoot '..\backend'
Push-Location $BackendDir

if (-not (Test-Path '.venv')) {
    Write-Host "[1/3] Creating Python venv..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "[1/3] venv exists - skipping creation." -ForegroundColor Green
}

Write-Host "[2/3] Installing dependencies..." -ForegroundColor Yellow
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt --quiet

Write-Host "[3/3] Starting backend..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Endpoints:" -ForegroundColor DarkCyan
Write-Host "    POST  http://localhost:8000/webhook/wazuh"
Write-Host "    POST  http://localhost:8000/hardware-alert"
Write-Host "    POST  http://localhost:8000/voice/command"
Write-Host "    GET   http://localhost:8000/api/alerts"
Write-Host "    GET   http://localhost:8000/api/status"
Write-Host "    GET   http://localhost:8000/health"
Write-Host "    Docs  http://localhost:8000/docs"
Write-Host ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Pop-Location
