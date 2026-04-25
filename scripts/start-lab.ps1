$ErrorActionPreference = 'Stop'

Write-Host "[1/2] Starting lab containers (Wazuh + Bank + MySQL)..." -ForegroundColor Yellow

$LabDir = Join-Path $PSScriptRoot '..\lab'
Push-Location $LabDir

docker compose up -d

Write-Host "[2/2] Waiting for bank app to be healthy..." -ForegroundColor Yellow

$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            $ok = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if ($ok) {
    Write-Host "Lab is up. Bank: http://localhost:8080" -ForegroundColor Green
} else {
    Write-Host "Bank did not become healthy in 120s. Check: docker compose logs bank" -ForegroundColor Red
}

Pop-Location
