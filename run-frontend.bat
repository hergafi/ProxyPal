@echo off
title ProxyPal - Frontend

echo ========================================
echo   ProxyPal - Frontend Server
echo ========================================
echo.

node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed
    pause
    exit /b 1
)

cd modern-workspace

if not exist node_modules (
    echo Installing dependencies...
    call npm install
    echo.
)

echo Starting Frontend server...
echo URL: http://localhost:5173
echo.
echo Press Ctrl+C to stop
echo.

call npm run dev

cd ..
pause
