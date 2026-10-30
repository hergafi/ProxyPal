# API FX Prod - Quick Start Script
# PowerShell version (more reliable than batch)

$Host.UI.RawUI.WindowTitle = "API FX Prod - Starting..."

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  API FX Prod - Smart AI Gateway v2.0" -ForegroundColor Cyan
Write-Host "  Starting development servers..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python is not installed" -ForegroundColor Red
    Write-Host "Please install Python 3.11+ from https://python.org"
    Read-Host "Press Enter to exit"
    exit 1
}

# Check Node.js
try {
    $nodeVersion = node --version 2>&1
    Write-Host "✓ Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Node.js is not installed" -ForegroundColor Red
    Write-Host "Please install Node.js from https://nodejs.org"
    Read-Host "Press Enter to exit"
    exit 1
}

# Check .env
if (-not (Test-Path .env)) {
    Write-Host ""
    Write-Host "⚠ WARNING: .env file not found" -ForegroundColor Yellow
    Write-Host "Copying from .env.example..."
    Copy-Item .env.example .env
    Write-Host "Please edit .env and add your API keys" -ForegroundColor Yellow
    Read-Host "Press Enter to continue"
}

# Install Python dependencies
Write-Host ""
Write-Host "[1/4] Installing Python dependencies..." -ForegroundColor Cyan
pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Failed to install Python dependencies" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "     ✓ Python dependencies installed" -ForegroundColor Green

# Install Node dependencies
Write-Host ""
Write-Host "[2/4] Checking Node.js dependencies..." -ForegroundColor Cyan
if (-not (Test-Path "modern-workspace\node_modules")) {
    Write-Host "     Installing Node.js dependencies..."
    Set-Location modern-workspace
    npm install
    Set-Location ..
}
Write-Host "     ✓ Node.js dependencies ready" -ForegroundColor Green

# Create logs directory
if (-not (Test-Path logs)) {
    New-Item -ItemType Directory -Path logs | Out-Null
}

# Start Backend
Write-Host ""
Write-Host "[3/4] Starting Backend server..." -ForegroundColor Cyan
Write-Host "     URL: http://127.0.0.1:8790" -ForegroundColor Gray
$backendProcess = Start-Process -FilePath "python" -ArgumentList "gateway.py" -PassThru -WindowStyle Normal
Start-Sleep -Seconds 3
Write-Host "     ✓ Backend started (PID: $($backendProcess.Id))" -ForegroundColor Green

# Start Frontend
Write-Host ""
Write-Host "[4/4] Starting Frontend server..." -ForegroundColor Cyan
Write-Host "     URL: http://localhost:5173" -ForegroundColor Gray
$frontendProcess = Start-Process -FilePath "cmd" -ArgumentList "/c cd modern-workspace && npm run dev" -PassThru -WindowStyle Normal
Start-Sleep -Seconds 2
Write-Host "     ✓ Frontend started (PID: $($frontendProcess.Id))" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ✓ Servers started successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backend:  http://127.0.0.1:8790" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""

# Open browser
$openBrowser = Read-Host "Open browser now? (Y/n)"
if ($openBrowser -ne 'n' -and $openBrowser -ne 'N') {
    Start-Process "http://localhost:5173"
}

Write-Host ""
Write-Host "Servers are running in separate windows." -ForegroundColor Gray
Write-Host "Run .\stop.ps1 to stop all servers." -ForegroundColor Gray
Write-Host ""
Read-Host "Press Enter to continue"
