# demo-stop.ps1 - Gracefully stop all SPECTER-AI demo processes
# Run from repo root: .\scripts\demo-stop.ps1
#
# Stops: ngrok, uvicorn (backend), voice listener (listener.py)
# Pass -StopLab to also docker compose down the lab containers.

param(
    [switch]$StopLab    # pass to also stop Docker Compose lab
)

$ErrorActionPreference = 'Continue'

Write-Host ""
Write-Host "  SPECTER-AI  |  Demo Stop" -ForegroundColor Cyan
Write-Host ""

# --- ngrok ---
$ngrok = Get-Process ngrok -ErrorAction SilentlyContinue
if ($ngrok) {
    $ngrok | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] ngrok stopped" -ForegroundColor Green
} else {
    Write-Host "  [-]  ngrok was not running" -ForegroundColor DarkGray
}

# --- backend (uvicorn) ---
$uvicorn = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*uvicorn*" }
if ($uvicorn) {
    $uvicorn | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  [OK] Backend (uvicorn) stopped" -ForegroundColor Green
} else {
    Write-Host "  [-]  Backend was not running" -ForegroundColor DarkGray
}

# --- voice listener ---
$listener = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*listener.py*" }
if ($listener) {
    $listener | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  [OK] Voice listener stopped" -ForegroundColor Green
} else {
    Write-Host "  [-]  Voice listener was not running" -ForegroundColor DarkGray
}

# --- lab (optional) ---
if ($StopLab) {
    Write-Host ""
    Write-Host "  Stopping Docker lab containers..." -ForegroundColor Yellow
    $LabDir = Join-Path $PSScriptRoot '..\lab'
    Push-Location $LabDir
    docker compose down
    Pop-Location
    Write-Host "  [OK] Lab containers stopped" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "  Lab containers still running." -ForegroundColor DarkGray
    Write-Host "  Pass -StopLab to also run docker compose down." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  Done. Run .\scripts\demo-start.ps1 to restart." -ForegroundColor Cyan
Write-Host ""
