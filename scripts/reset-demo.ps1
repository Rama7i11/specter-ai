# reset-demo.ps1 - Full demo reset between judging runs
#
# Does in order:
#   1. POST /demo/reset  -> clears blocked IPs + all in-memory alert/defense state
#   2. POST /demo/seed   -> re-populates bankdb with fresh users & transactions
#
# Run from repo root: .\scripts\reset-demo.ps1

param(
    [string]$BaseUrl  = "http://localhost:8000",
    [switch]$SkipSeed           # pass -SkipSeed if MySQL/lab isn't running
)

$ErrorActionPreference = 'Continue'   # don't abort on partial failure

Write-Host ""
Write-Host " SPECTER-AI  |  Demo Reset" -ForegroundColor Cyan
Write-Host " Backend     :  $BaseUrl" -ForegroundColor DarkCyan
Write-Host ""

# --- Step 1: clear state ---
Write-Host "[1/2] Resetting all demo state..." -ForegroundColor Yellow
try {
    $reset = Invoke-RestMethod -Uri "$BaseUrl/demo/reset" -Method Post -ErrorAction Stop
    $cleared = $reset.cleared -join ", "
    Write-Host "      OK - cleared: $cleared" -ForegroundColor Green
}
catch {
    Write-Host "      FAILED: $_" -ForegroundColor Red
    Write-Host "      Is the backend running?  .\scripts\start-backend.ps1" -ForegroundColor DarkYellow
    exit 1
}

# --- Step 2: re-seed bank DB ---
if ($SkipSeed) {
    Write-Host "[2/2] Skipping DB seed (-SkipSeed flag set)." -ForegroundColor DarkGray
}
else {
    Write-Host "[2/2] Re-seeding bank database..." -ForegroundColor Yellow
    try {
        $seed = Invoke-RestMethod -Uri "$BaseUrl/demo/seed" -Method Post -ErrorAction Stop
        if ($seed.seeded) {
            Write-Host "      OK - $($seed.users) users inserted into bankdb" -ForegroundColor Green
        }
        else {
            Write-Host "      WARN - seed returned error: $($seed.error)" -ForegroundColor Yellow
            Write-Host "      HINT: $($seed.hint)" -ForegroundColor DarkYellow
            Write-Host "      Is the lab running?  .\scripts\start-lab.ps1" -ForegroundColor DarkYellow
        }
    }
    catch {
        Write-Host "      WARN - seed endpoint unreachable ($_)" -ForegroundColor Yellow
        Write-Host "      The state reset succeeded; DB may still have previous data." -ForegroundColor DarkYellow
    }
}

# --- Summary ---
Write-Host ""
Write-Host " Demo reset complete. Next steps:" -ForegroundColor Cyan
Write-Host "   1.  .\scripts\run-attack.ps1 -type sqli|brute   (Attacker terminal)"
Write-Host "   2.  Say 'Hey Jarvis' - Specter will brief you   (Voice terminal)"
Write-Host "   3.  Say 'Run command one'                        (blocks attacker IP)"
Write-Host "   4.  Visit http://localhost:8080                  (confirm 403)"
Write-Host "   5.  .\scripts\reset-demo.ps1                    (repeat for next judge)"
Write-Host ""
