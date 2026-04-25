# start-lab.ps1 — Start the SPECTER-AI lab environment
# Run from repo root: .\scripts\start-lab.ps1

$ErrorActionPreference = 'Stop'
$LabDir = Join-Path $PSScriptRoot '..\lab'

Write-Host "`n[SPECTER-AI] Starting lab..." -ForegroundColor Cyan

# ── Pre-flight checks ──────────────────────────────────────────────────────
Write-Host "[1/4] Checking Docker..." -ForegroundColor Yellow
docker info | Out-Null
if (-not $?) { Write-Error "Docker Desktop is not running. Start it and retry."; exit 1 }

# ── Cert generation (skip if certs already exist) ─────────────────────────
$CertsDir = Join-Path $LabDir 'config\wazuh_indexer_ssl_certs'
$RootCa   = Join-Path $CertsDir 'root-ca.pem'

if (-not (Test-Path $RootCa)) {
    Write-Host "[2/4] Generating Wazuh SSL certificates (one-time)..." -ForegroundColor Yellow
    Push-Location $LabDir
    docker compose -f generate-certs.yml run --rm generator
    Pop-Location
    Write-Host "      Certs written to $CertsDir" -ForegroundColor Green
} else {
    Write-Host "[2/4] Certs already exist — skipping generation." -ForegroundColor Green
}

# ── Copy .env to lab dir if needed ────────────────────────────────────────
$EnvFile    = Join-Path $PSScriptRoot '..\. env'
$LabEnvFile = Join-Path $LabDir '.env'
$EnvSource  = Join-Path $PSScriptRoot '..\.env'
if ((Test-Path $EnvSource) -and (-not (Test-Path $LabEnvFile))) {
    Copy-Item $EnvSource $LabEnvFile
    Write-Host "      Copied .env to lab/" -ForegroundColor Green
}

# ── Start stack ───────────────────────────────────────────────────────────
Write-Host "[3/4] Starting containers (this takes 2-3 min on first run)..." -ForegroundColor Yellow
Push-Location $LabDir
docker compose up -d --build
Pop-Location

# ── Health poll ───────────────────────────────────────────────────────────
Write-Host "[4/4] Waiting for Wazuh indexer to become healthy..." -ForegroundColor Yellow
$Timeout  = 180   # seconds
$Interval = 10
$Elapsed  = 0

while ($Elapsed -lt $Timeout) {
    $Status = docker inspect --format '{{.State.Health.Status}}' lab-wazuh.indexer-1 2>$null
    if ($Status -eq 'healthy') {
        Write-Host "`n[OK] Wazuh indexer is healthy." -ForegroundColor Green
        break
    }
    Write-Host "     ...still starting ($Elapsed s elapsed, status: $Status)" -ForegroundColor DarkGray
    Start-Sleep $Interval
    $Elapsed += $Interval
}

if ($Elapsed -ge $Timeout) {
    Write-Warning "Indexer did not become healthy within ${Timeout}s. Check logs:"
    Write-Host "  docker compose -f lab/docker-compose.yml logs wazuh.indexer" -ForegroundColor Yellow
}

# ── Summary ───────────────────────────────────────────────────────────────
Write-Host @"

[SPECTER-AI] Lab is up.

  Bank app:         http://localhost:8080
  Wazuh dashboard:  https://localhost:5601  (admin / SecretPassword)
  Wazuh API:        https://localhost:55000  (wazuh-wui / MyS3cr37P450r.*)
  MySQL:            localhost:3306  (root / rootpass)

  Tail bank logs:   docker exec lab-bank-1 tail -f /var/log/bank/access.log
  Tail Wazuh alerts: .\scripts\tail-alerts.ps1
"@ -ForegroundColor Cyan
