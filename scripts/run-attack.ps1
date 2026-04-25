# run-attack.ps1 — Launch Specter-AI attacker simulations
# Run from repo root: .\scripts\run-attack.ps1 -type sqli|brute|both

param(
    [Parameter(Mandatory)]
    [ValidateSet('sqli','brute','both')]
    [string]$type,

    [string]$Target = "http://localhost:8080"
)

$ErrorActionPreference = 'Stop'
$AttackerDir = Join-Path $PSScriptRoot '..\attacker'

Push-Location $AttackerDir

# ── Ensure venv exists ────────────────────────────────────────────────────
if (-not (Test-Path '.venv')) {
    Write-Host "[setup] Creating attacker venv..." -ForegroundColor Yellow
    python -m venv .venv
    . .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt --quiet
} else {
    . .\.venv\Scripts\Activate.ps1
}

# ── Dispatch ──────────────────────────────────────────────────────────────
switch ($type) {
    'sqli' {
        Write-Host "`n[ATTACK] Launching SQL injection simulation..." -ForegroundColor Red
        python sqli.py --target $Target
    }
    'brute' {
        Write-Host "`n[ATTACK] Launching brute force simulation..." -ForegroundColor Yellow
        python brute_force.py --target $Target
    }
    'both' {
        Write-Host "`n[ATTACK] Launching SQL injection simulation..." -ForegroundColor Red
        python sqli.py --target $Target
        Write-Host "`n[ATTACK] Launching brute force simulation..." -ForegroundColor Yellow
        python brute_force.py --target $Target
    }
}

Pop-Location
