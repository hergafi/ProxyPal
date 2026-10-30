@echo off
title ProxyPal - System Check

echo ========================================
echo   ProxyPal - System Check
echo ========================================
echo.

echo Checking system requirements...
echo.

REM Check Python
echo [1/4] Python...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    python --version
    echo      [OK] Python is installed
) else (
    echo      [ERROR] Python is NOT installed
    echo      Please install Python 3.11+ from https://python.org
)
echo.

REM Check pip
echo [2/4] pip...
pip --version >nul 2>&1
if %errorlevel% equ 0 (
    pip --version
    echo      [OK] pip is installed
) else (
    echo      [ERROR] pip is NOT installed
)
echo.

REM Check Node.js
echo [3/4] Node.js...
node --version >nul 2>&1
if %errorlevel% equ 0 (
    node --version
    echo      [OK] Node.js is installed
) else (
    echo      [ERROR] Node.js is NOT installed
    echo      Please install Node.js from https://nodejs.org
)
echo.

REM Check npm
echo [4/4] npm...
npm --version >nul 2>&1
if %errorlevel% equ 0 (
    npm --version
    echo      [OK] npm is installed
) else (
    echo      [ERROR] npm is NOT installed
)
echo.

REM Check files
echo ========================================
echo   Checking project files...
echo ========================================
echo.

if exist gateway.py (
    echo [OK] gateway.py found
) else (
    echo [ERROR] gateway.py NOT found
)

if exist .env (
    echo [OK] .env found
) else (
    echo [WARNING] .env NOT found - will be created from .env.example
)

if exist modern-workspace\package.json (
    echo [OK] modern-workspace/package.json found
) else (
    echo [ERROR] modern-workspace/package.json NOT found
)

if exist modern-workspace\node_modules (
    echo [OK] node_modules installed
) else (
    echo [WARNING] node_modules NOT installed - will be installed on first run
)

echo.
echo ========================================
echo   Check complete!
echo ========================================
echo.
pause
