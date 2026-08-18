# =============================================================================
# AnonyMus - Zero-Configuration 1-Click Windows Setup & Launcher
# =============================================================================

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "         AnonyMus Windows Quickstart Setup Wizard          " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Check Python installation
Write-Host "[*] Checking Python runtime..." -ForegroundColor Yellow
$PythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = "py"
} else {
    Write-Host "[!] Error: Python 3.10+ is required but not found in PATH." -ForegroundColor Red
    Write-Host "    Please download Python from https://www.python.org/downloads/ and ensure 'Add Python to PATH' is checked." -ForegroundColor Red
    Pause
    Exit 1
}

# Verify Python version
$VersionStr = & $PythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "[+] Found Python version: $VersionStr" -ForegroundColor Green

# 2. Virtual Environment Setup
$VenvDir = Join-Path $PSScriptRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[*] Initializing virtual environment in .venv..." -ForegroundColor Yellow
    & $PythonCmd -m venv $VenvDir
}

# 3. Dependency Installation
Write-Host "[*] Installing / verifying dependencies..." -ForegroundColor Yellow
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r (Join-Path $PSScriptRoot "requirements.txt")

# 4. Apply Database Migrations
Write-Host "[*] Upgrading database schema via Alembic..." -ForegroundColor Yellow
& $VenvPython -m alembic upgrade head

# 5. Launch AnonyMus Client
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Setup complete! Starting AnonyMus Secure Communications...  " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

& $VenvPython (Join-Path $PSScriptRoot "anonymus-launcher.py")
