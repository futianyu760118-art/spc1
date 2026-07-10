param(
    [string]$CondaPath = "D:\software\miniconda3",
    [string]$EnvName = "spc-backend",
    [switch]$SkipInitDb,
    [switch]$SkipSetup
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path

try {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  SPC v2 - Backend Local Run Script" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    # ── 1. Initialize Conda ──
    $CondaScript = Join-Path $CondaPath "Scripts\conda.exe"
    if (-not (Test-Path $CondaScript)) {
        $CondaScript = Join-Path $CondaPath "condabin\conda.bat"
    }
    if (-not (Test-Path $CondaScript)) {
        throw "Conda not found at $CondaPath. Please check the miniconda3 installation path."
    }
    Write-Host "[1/5] Conda found at: $CondaPath" -ForegroundColor Green

    # ── 2. Setup Conda environment ──
    if (-not $SkipSetup) {
        Write-Host "[2/5] Setting up conda environment '$EnvName'..." -ForegroundColor Yellow
        & $CondaScript init powershell | Out-Null

        $envExists = & $CondaScript env list | Select-String -Pattern "^\s*$EnvName\s" -Quiet
        if (-not $envExists) {
            Write-Host "  Creating conda environment '$EnvName' with Python 3.11..." -ForegroundColor Yellow
            & $CondaScript create -n $EnvName python=3.11 -y
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to create conda environment."
            }
        } else {
            Write-Host "  Conda environment '$EnvName' already exists." -ForegroundColor Green
        }

        Write-Host "  Installing Python dependencies..." -ForegroundColor Yellow
        & $CondaScript run -n $EnvName pip install -r "$ProjectRoot\backend\requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  Retrying with default PyPI..." -ForegroundColor Yellow
            & $CondaScript run -n $EnvName pip install -r "$ProjectRoot\backend\requirements.txt"
        }
        Write-Host "[2/5] Dependencies installed." -ForegroundColor Green
    } else {
        Write-Host "[2/5] Skipped (--SkipSetup)." -ForegroundColor DarkGray
    }

    # ── 3. Environment file ──
    Write-Host "[3/5] Checking .env file..." -ForegroundColor Yellow
    $EnvFile = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $EnvFile)) {
        Copy-Item "$ProjectRoot\.env.example" $EnvFile
        Write-Host "  Created .env from .env.example. Please review and adjust settings if needed." -ForegroundColor Yellow
        Write-Host "  Default database: postgresql+asyncpg://root:123456@192.168.0.127:5432/spc_db" -ForegroundColor DarkGray
    } else {
        Write-Host "  .env already exists." -ForegroundColor Green
    }

    # ── 4. Initialize database (with timeout) ──
    $initDbTimeout = 120  # seconds
    if (-not $SkipInitDb) {
        Write-Host "[4/5] Initializing database (timeout: ${initDbTimeout}s)..." -ForegroundColor Yellow
        Set-Location "$ProjectRoot\backend"

        $job = Start-Job -ScriptBlock {
            param($CondaScript, $EnvName, $ProjectRoot)
            Set-Location "$ProjectRoot\backend"
            & $CondaScript run -n $EnvName python init_database.py 2>&1
        } -ArgumentList $CondaScript, $EnvName, $ProjectRoot

        $completed = Wait-Job $job -Timeout $initDbTimeout
        if ($completed) {
            $output = Receive-Job $job
            $output | ForEach-Object { Write-Host "  $_" }
            Remove-Job $job
            Write-Host "[4/5] Database initialized." -ForegroundColor Green
        } else {
            Write-Host "  WARNING: init_database.py timed out after ${initDbTimeout}s!" -ForegroundColor Yellow
            Write-Host "  The database may already be initialized. Continuing anyway..." -ForegroundColor Yellow
            Write-Host "  Tip: Run 'python init_database.py' manually in backend/ if needed." -ForegroundColor DarkGray
            Stop-Job $job
            Remove-Job $job
        }
    } else {
        Write-Host "[4/5] Skipped (--SkipInitDb)." -ForegroundColor DarkGray
    }

    # ── 5. Get LAN IP (优先真实网卡，排除虚拟网卡) ──
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

    # ── 6. Check Windows Firewall ──
    Write-Host "[5/6] Checking Windows Firewall..." -ForegroundColor Yellow
    $fwBackend = netsh advfirewall firewall show rule name="SPC Backend" 2>&1
    if ($LASTEXITCODE -ne 0 -or $fwBackend -notmatch "SPC Backend") {
        Write-Host "  WARNING: Firewall rule for port 8000 not found!" -ForegroundColor Red
        Write-Host "  LAN access will be blocked by Windows Firewall." -ForegroundColor Red
        Write-Host "  Run the following command as Administrator to fix:" -ForegroundColor Yellow
        Write-Host "    netsh advfirewall firewall add rule name='SPC Backend' dir=in action=allow protocol=TCP localport=8000" -ForegroundColor White
        Write-Host ""
    } else {
        Write-Host "  Firewall rule OK." -ForegroundColor Green
    }

    # ── 7. Start backend ──
    Write-Host "[6/6] Starting backend server (LAN enabled)..." -ForegroundColor Yellow
    Write-Host "  Local:    http://localhost:8000" -ForegroundColor Cyan
    if ($localIP -ne "localhost") {
        Write-Host "  LAN:      http://${localIP}:8000" -ForegroundColor Cyan
    }
    Write-Host "  API Docs: http://localhost:8000/api/v1/docs" -ForegroundColor Cyan
    Write-Host "  Health:   http://localhost:8000/health" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    Set-Location "$ProjectRoot\backend"
    & $CondaScript run -n $EnvName uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
} catch {
    Write-Host ""
    Write-Host "ERROR: $_" -ForegroundColor Red
    Write-Host ""
    Pause
} finally {
    Write-Host ""
    Write-Host "Backend server stopped." -ForegroundColor Yellow
    Pause
}