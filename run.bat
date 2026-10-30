@echo off
cd /d "%~dp0"
title ProxyPal - Starting...

echo ========================================
echo   API FX Prod - Smart AI Gateway
echo   Starting development servers...
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed
    echo Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

REM Check Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed
    echo Please install Node.js from https://nodejs.org
    pause
    exit /b 1
)

REM Check .env
if not exist .env (
    echo [WARNING] .env file not found
    echo Copying from .env.example...
    copy .env.example .env
    echo.
    echo [IMPORTANT] Please edit .env and add your API keys
    echo.
    pause
)

REM Install Python dependencies
echo [1/4] Installing Python dependencies...
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies
    pause
    exit /b 1
)
echo      [OK] Python dependencies installed
echo.

REM Install Node dependencies
echo [2/4] Checking Node.js dependencies...
if not exist modern-workspace\node_modules (
    echo      Installing Node.js dependencies...
    cd modern-workspace
    call npm install
    cd ..
)
echo      [OK] Node.js dependencies ready
echo.

REM Create logs directory
if not exist logs mkdir logs

echo [3/4] Checking Backend server...
REM exit 0 = current gateway, 1 = not running, 2 = port belongs to another app, 3 = old gateway version
powershell -NoProfile -Command "$v=0; try { $r = Invoke-RestMethod 'http://127.0.0.1:8790/health' -TimeoutSec 2; if ($r.status -eq 'ok') { $v=[int]$r.version; if ($v -ge 6) { exit 0 }; exit 3 } else { exit 2 } } catch { if ($_.Exception.Response) { exit 2 }; exit 1 }"
if errorlevel 3 goto restart_backend
if errorlevel 2 (
    echo [ERROR] Port 8790 belongs to another service. No process was stopped.
    pause
    exit /b 1
)
if errorlevel 1 (
    start "API-FX-Backend" cmd /k "python gateway.py"
)
goto wait_backend

:restart_backend
echo      Old gateway version detected - restarting it...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart.ps1"
if errorlevel 1 (
    echo [ERROR] Could not restart the backend. See logs\backend.err.log
    pause
    exit /b 1
)

:wait_backend
powershell -NoProfile -Command "$ready = $false; for ($i=0; $i -lt 30; $i++) { try { $r = Invoke-RestMethod 'http://127.0.0.1:8790/health' -TimeoutSec 1; if ($r.status -eq 'ok' -and [int]$r.version -ge 6) { $ready = $true; break } } catch {}; Start-Sleep -Milliseconds 400 }; if (-not $ready) { exit 1 }"
if errorlevel 1 (
    echo [ERROR] Backend did not become ready. Check its window or logs\backend.err.log
    pause
    exit /b 1
)

echo [4/4] Checking Frontend server...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest 'http://localhost:5173/' -TimeoutSec 2 -UseBasicParsing; if ($r.Content -match 'ProxyPal') { exit 0 }; exit 2 } catch { if ($_.Exception.Response) { exit 2 }; exit 1 }"
if errorlevel 2 (
    echo [ERROR] Port 5173 belongs to another app. No process was stopped.
    pause
    exit /b 1
)
if errorlevel 1 (
    start "API-FX-Frontend" cmd /k "cd modern-workspace && npm run dev -- --strictPort"
)
powershell -NoProfile -Command "$ready = $false; for ($i=0; $i -lt 30; $i++) { try { $r = Invoke-WebRequest 'http://localhost:5173/' -TimeoutSec 1 -UseBasicParsing; if ($r.Content -match 'ProxyPal') { $ready = $true; break } } catch {}; Start-Sleep -Milliseconds 200 }; if (-not $ready) { exit 1 }"
if errorlevel 1 (
    echo [ERROR] Frontend did not become ready. Check its window.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   [OK] Servers started successfully!
echo ========================================
echo.
echo   Backend:  http://127.0.0.1:8790
echo   Frontend: http://localhost:5173
echo.
echo   Press any key to open browser...
pause >nul

REM Open browser
start http://localhost:5173

echo.
echo Servers are running in separate windows.
echo Close those windows to stop the servers.
echo.
pause
