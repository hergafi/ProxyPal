@echo off
title ProxyPal - Setup

echo ========================================
echo   ProxyPal - Initial Setup
echo ========================================
echo.

echo [1/5] Creating directory structure...
if not exist logs mkdir logs
echo      [OK] Directories created
echo.

echo [2/5] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed
    echo Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)
echo      [OK] Python is installed
echo.

echo [3/5] Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies
    pause
    exit /b 1
)
echo      [OK] Python dependencies installed
echo.

echo [4/5] Checking Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed
    echo Please install Node.js from https://nodejs.org
    pause
    exit /b 1
)
echo      [OK] Node.js is installed
echo.

echo [5/5] Installing Node.js dependencies...
cd modern-workspace
call npm install
cd ..
echo      [OK] Node.js dependencies installed
echo.

echo ========================================
echo   [OK] Setup completed successfully!
echo ========================================
echo.
echo Next steps:
echo   1. Edit .env file and add your API keys
echo   2. Run 'run.bat' to start the servers
echo   3. Open http://localhost:5173 in your browser
echo.
pause
