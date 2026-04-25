# run-attack.ps1 — Launch the SQLi attacker simulation
# Run from repo root: .\scripts\run-attack.ps1 [--target http://host:port]

$ErrorActionPreference = 'Stop'
$AttackerDir = Join-Path $PSScriptRoot '..\attacker'

Push-Location $AttackerDir

if (-not (Test-Path '.venv')) {
    Write-Host "[setup] Creating attacker venv..." -ForegroundColor Yellow
    python -m venv .venv
    . .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt --quiet
} else {
    . .\.venv\Scripts\Activate.ps1
}

# Forward any extra args (e.g. --target http://192.168.1.x:8080)
python sqli.py @args

Pop-Location
