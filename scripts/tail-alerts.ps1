# tail-alerts.ps1 — Live-tail SPECTER-AI alerts from the backend API
# Polls /api/alerts every 2 seconds, prints only new entries.
# Run from repo root: .\scripts\tail-alerts.ps1

param(
    [string]$BaseUrl = "http://localhost:8000",
    [int]   $PollSec = 2
)

$seen = @{}

Write-Host ""
Write-Host " SPECTER-AI  |  Alert Feed" -ForegroundColor Cyan
Write-Host " Backend     :  $BaseUrl" -ForegroundColor DarkCyan
Write-Host " Polling     :  every ${PollSec}s  |  Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host (" " + "─" * 72) -ForegroundColor DarkGray
Write-Host ""

while ($true) {
    try {
        $resp   = Invoke-RestMethod -Uri "$BaseUrl/api/alerts" -Method Get -ErrorAction Stop
        $alerts = $resp.alerts | Sort-Object { [int]$_.alert_id }

        foreach ($a in $alerts) {
            $id = [string]$a.alert_id
            if (-not $seen.ContainsKey($id)) {
                $seen[$id] = $true

                $ts      = if ($a.timestamp) { $a.timestamp.Substring(0,19).Replace("T"," ") } else { "?" }
                $ip      = $a.ip
                $pattern = $a.matched_pattern
                $city    = $a.city
                $country = $a.country
                $geo     = if ($city -and $country -and $city -ne "private/local") {
                               "$city, $country"
                           } elseif ($country) {
                               $country
                           } else {
                               "private/local"
                           }

                Write-Host "[$ts] " -ForegroundColor DarkGray -NoNewline
                Write-Host "#$id " -ForegroundColor DarkRed -NoNewline
                Write-Host "SQL_INJECTION " -ForegroundColor Red -NoNewline
                Write-Host "ip=$ip " -ForegroundColor Yellow -NoNewline
                Write-Host "geo=[$geo] " -ForegroundColor Cyan -NoNewline
                Write-Host "pattern=$pattern" -ForegroundColor White
            }
        }

        # Status line: update every poll cycle (overwrite same line)
        $status = Invoke-RestMethod -Uri "$BaseUrl/api/status" -Method Get -ErrorAction SilentlyContinue
        if ($status) {
            $line = "  detector=$($status.detector)  alerts_today=$($status.alerts_today)  blocked=$($status.blocked_ips)  uptime=$($status.uptime)s"
            Write-Host "`r$line" -ForegroundColor DarkGray -NoNewline
        }
    }
    catch {
        Write-Host "`r[WARN] Backend unreachable — retrying in ${PollSec}s..." -ForegroundColor DarkYellow -NoNewline
    }

    Start-Sleep -Seconds $PollSec
}
