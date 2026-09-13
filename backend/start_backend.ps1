# Start the IdentiCare backend reachable from your phone. No Docker needed
# once MONGO_URI points at Atlas.
#
#   backend\start_backend.ps1
#
# It prints the exact `flutter run` line for your current LAN IP, because that
# IP changes every time you switch between Wi-Fi and a phone hotspot - and a
# stale IP baked into the app is the single most common reason the phone
# reports "Tidak dapat terhubung ke server".

$ErrorActionPreference = "Stop"
$backend = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $backend
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "[!] No virtualenv at $python" -ForegroundColor Red
    Write-Host "    py -3.12 -m venv backend\.venv; backend\.venv\Scripts\pip install -r backend\requirements.txt"
    exit 1
}

# --- Which database are we on? ------------------------------------------- #
$envFile = Join-Path $backend ".env"
$uri = (Select-String -Path $envFile -Pattern '^MONGO_URI=(.*)$').Matches[0].Groups[1].Value
if ($uri -like "*REPLACE_WITH_CLUSTER_HOST*") {
    Write-Host "[!] MONGO_URI still has the placeholder host." -ForegroundColor Red
    Write-Host "    Run:  $python backend\scripts\use_atlas.py <your-cluster-host>"
    exit 1
}
if ($uri -like "mongodb+srv://*") {
    Write-Host "[+] Database: MongoDB Atlas" -ForegroundColor Green
} else {
    Write-Host "[~] Database: local ($($uri -replace ':[^:@]*@', ':***@'))" -ForegroundColor Yellow
    Write-Host "    This needs Docker running. If it is not, use Atlas: backend\scripts\use_atlas.py"
}

# --- LAN IP the phone should use ---------------------------------------- #
$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -notlike '172.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
    Select-Object -First 1 -ExpandProperty IPAddress
if (-not $ip) { $ip = "<your-lan-ip>" }

# --- Firewall: silent timeouts on the phone are almost always this -------- #
$rule = Get-NetFirewallRule -DisplayName "IdentiCare API" -ErrorAction SilentlyContinue
if (-not $rule) {
    Write-Host "[~] No firewall rule for port 8000. If the phone times out, run ONCE as admin:" -ForegroundColor Yellow
    Write-Host '    New-NetFirewallRule -DisplayName "IdentiCare API" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow'
}

Write-Host ""
Write-Host "==================================================================="
Write-Host " Backend:  http://${ip}:8000        Swagger: http://${ip}:8000/docs"
Write-Host ""
Write-Host " Run the app against it (from the repo root, phone plugged in):"
Write-Host "   flutter run --dart-define=API_BASE_URL=http://${ip}:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host " Or, without rebuilding: open the app > Pengaturan > Alamat server"
Write-Host " and enter http://${ip}:8000"
Write-Host "==================================================================="
Write-Host ""

Set-Location $root
& $python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
