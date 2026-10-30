@echo off
title ProxyPal - Backend

echo ========================================
echo   ProxyPal - Backend Server
echo ========================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed
    pause
    exit /b 1
)

if not exist .env (
    echo [WARNING] .env file not found
    copy .env.example .env
    echo Please edit .env and add your API keys
    pause
)

echo Installing dependencies...
pip install -r requirements.txt

if not exist logs mkdir logs

echo.
echo Starting Backend server...
echo URL: http://127.0.0.1:8790
echo.
echo Press Ctrl+C to stop
echo.

python gateway.py

pause
