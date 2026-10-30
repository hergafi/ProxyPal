@echo off
cd /d "%~dp0"
title ProxyPal - Restart Gateway
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart.ps1" %*
echo.
pause
