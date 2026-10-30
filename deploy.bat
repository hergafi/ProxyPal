@echo off
title ProxyPal - Docker Deploy

echo ========================================
echo   ProxyPal - Docker Deployment
echo ========================================
echo.

docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not installed
    echo Please install Docker Desktop from https://docker.com
    pause
    exit /b 1
)

echo [1/3] Building Docker images...
docker-compose build

if %errorlevel% neq 0 (
    echo [ERROR] Build failed
    pause
    exit /b 1
)

echo.
echo [2/3] Starting containers...
docker-compose up -d

if %errorlevel% neq 0 (
    echo [ERROR] Failed to start containers
    pause
    exit /b 1
)

echo.
echo [3/3] Waiting for services...
timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo   [OK] Deployment successful!
echo ========================================
echo.
echo   Application: http://localhost:8790
echo.
echo   Commands:
echo     Logs:    docker-compose logs -f
echo     Stop:    docker-compose down
echo     Restart: docker-compose restart
echo.
pause
