param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$FrontendDir = Join-Path $ProjectRoot "frontend"

try {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  SPC v2 - Frontend Local Run Script" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    # ── 1. Check Node.js ──
    Write-Host "[1/3] Checking Node.js..." -ForegroundColor Yellow
    try {
        $nodeVersion = & node --version 2>&1
        Write-Host "  Node.js version: $nodeVersion" -ForegroundColor Green
    } catch {
        throw "Node.js not found. Please install Node.js (https://nodejs.org/) and ensure it's in PATH."
    }

    # ── 2. Install dependencies ──
    if (-not $SkipInstall) {
        Write-Host "[2/3] Installing npm dependencies..." -ForegroundColor Yellow
        Set-Location $FrontendDir

        if (-not (Test-Path "node_modules")) {
            Write-Host "  First run: installing packages..." -ForegroundColor Yellow
            npm install
        } else {
            Write-Host "  node_modules exists, checking for updates..." -ForegroundColor Yellow
            npm install
        }

        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed."
        }
        Write-Host "[2/3] Dependencies installed." -ForegroundColor Green
    } else {
        Write-Host "[2/3] Skipped (--SkipInstall)." -ForegroundColor DarkGray
    }

    # ── 3. Get LAN IP (优先真实网卡，排除虚拟网卡) ──
    $allIPs = Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp,Manual `
        | Where-Object { $_.IPAddress -notmatch "^127\." -and $_.IPAddress -notmatch "^169\.254\." } `
        | Select-Object IPAddress, InterfaceAlias

    # 优先选择 192.168.x.x，其次 10.x.x.x，最后 172.16-31.x.x
    $localIP = ($allIPs | Where-Object { $_.IPAddress -match "^192\.168\." } | Select-Object -First 1).IPAddress
    if (-not $localIP) {
        $localIP = ($allIPs | Where-Object { $_.IPAddress -match "^10\." } | Select-Object -First 1).IPAddress
    }
    if (-not $localIP) {
        $localIP = ($allIPs | Where-Object { $_.IPAddress -match "^172\.(1[6-9]|2[0-9]|3[01])\." } | Select-Object -First 1).IPAddress
    }
    if (-not $localIP) {
        $localIP = ($allIPs | Select-Object -First 1).IPAddress
    }

    if (-not $localIP) {
        $localIP = "localhost"
    }

    # ── 4. Check Windows Firewall ──
    Write-Host "[3/4] Checking Windows Firewall..." -ForegroundColor Yellow
    $fwRule = netsh advfirewall firewall show rule name="SPC Frontend Dev" 2>&1
    if ($LASTEXITCODE -ne 0 -or $fwRule -notmatch "SPC Frontend Dev") {
        Write-Host "  WARNING: Firewall rule for port 3000 not found!" -ForegroundColor Red
        Write-Host "  LAN access will be blocked by Windows Firewall." -ForegroundColor Red
        Write-Host "  Run the following command as Administrator to fix:" -ForegroundColor Yellow
        Write-Host "    netsh advfirewall firewall add rule name='SPC Frontend Dev' dir=in action=allow protocol=TCP localport=3000" -ForegroundColor White
        Write-Host ""
    } else {
        Write-Host "  Firewall rule OK." -ForegroundColor Green
    }

    # ── 5. Start frontend dev server ──
    Write-Host "[4/4] Starting frontend dev server (LAN enabled)..." -ForegroundColor Yellow
    Write-Host "  Local:  http://localhost:3000" -ForegroundColor Cyan
    if ($localIP -ne "localhost") {
        Write-Host "  LAN:    http://${localIP}:3000" -ForegroundColor Cyan
    }
    Write-Host "  API proxy: /api -> http://localhost:8000" -ForegroundColor DarkGray
    Write-Host "========================================" -ForegroundColor Cyan

    Set-Location $FrontendDir
    npx vite --host 0.0.0.0 --port 3000
} catch {
    Write-Host ""
    Write-Host "ERROR: $_" -ForegroundColor Red
    Write-Host ""
    Pause
} finally {
    # Vite 异常退出时保持窗口不闪退
    Write-Host ""
    Write-Host "Frontend dev server stopped." -ForegroundColor Yellow
    Pause
}