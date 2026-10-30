@echo off
cd /d "%~dp0"
title ProxyPal - Stop Servers
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
echo.
pause
