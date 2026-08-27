# Permanent backend startup script.
#
# Fixes, every single time, the three recurring causes of "URL is down" /
# "Could not reach the server" seen throughout this project:
#   1. A stale/duplicate uvicorn process still holding port 8000 (bound to
#      127.0.0.1 only), silently serving OLD code to the phone while a NEW
#      process on the same port answers curl from this PC just fine.
#   2. mobile/.env pointing at a LAN IP that changed (DHCP reassigns it,
#      especially after switching networks).
#   3. Forgetting --host 0.0.0.0 (binds to localhost-only, unreachable from
#      the phone). --reload is intentionally NOT used here: this project's
#      node_modules/backend code lives inside a OneDrive-synced folder, and
#      OneDrive's file-sync interferes with file-watchers (the same class of
#      problem documented for Metro elsewhere in this repo) -- --reload was
#      observed to silently stop picking up changes. Rerun this script after
#      editing backend code instead of trusting auto-reload.
#
# Usage (from anywhere):
#   powershell -ExecutionPolicy Bypass -File "C:\Users\user\OneDrive\Desktop\AITrailReporter\backend\start.ps1"

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$envFile = Join-Path $repoRoot "mobile\.env"
$port = 8000

Write-Host "=== 1. Killing anything already on port $port ===" -ForegroundColor Cyan
$existing = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $existing) {
    try {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "  Stopping PID $procId ($($proc.ProcessName))"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}
if ($existing) { Start-Sleep -Seconds 1 }

Write-Host "=== 2. Detecting this machine's LAN IPv4 ===" -ForegroundColor Cyan
$ip = (Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp -ErrorAction SilentlyContinue |
    Where-Object { $_.InterfaceAlias -notmatch "Loopback|vEthernet|WSL" } |
    Select-Object -First 1 -ExpandProperty IPAddress)
if (-not $ip) {
    # Fallback for a statically-configured adapter (no Dhcp origin).
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -notmatch "Loopback|vEthernet|WSL" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -First 1 -ExpandProperty IPAddress)
}
if (-not $ip) {
    Write-Host "  Could not detect a LAN IP automatically. Leaving mobile/.env untouched." -ForegroundColor Yellow
} else {
    Write-Host "  LAN IP: $ip"
    $desiredLine = "EXPO_PUBLIC_API_BASE_URL=http://${ip}:${port}"
    if (Test-Path $envFile) {
        $current = Get-Content $envFile -Raw
        if ($current.Trim() -ne $desiredLine) {
            Set-Content -Path $envFile -Value $desiredLine -Encoding utf8 -NoNewline
            Add-Content -Path $envFile -Value "" -Encoding utf8
            Write-Host "  Updated mobile\.env -> $desiredLine" -ForegroundColor Green
        } else {
            Write-Host "  mobile\.env already correct."
        }
    } else {
        Set-Content -Path $envFile -Value $desiredLine -Encoding utf8
        Write-Host "  Created mobile\.env -> $desiredLine" -ForegroundColor Green
    }
}

Write-Host "=== 3. Ensuring the firewall rule exists (Private + Public) ===" -ForegroundColor Cyan
$ruleName = "AITrailreporter backend (dev, port $port)"
$rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $rule) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP `
        -LocalPort $port -Action Allow -Profile Private, Public | Out-Null
    Write-Host "  Created firewall rule." -ForegroundColor Green
} else {
    Write-Host "  Firewall rule already present."
}

Write-Host "=== 4. Starting uvicorn on 0.0.0.0:$port (no --reload -- see header comment) ===" -ForegroundColor Cyan
Set-Location $backendDir
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port $port
