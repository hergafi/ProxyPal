# ProxyPal - restart the backend safely.
# Only stops the process that listens on the gateway port AND runs gateway.py.
param([int]$Port = 8790)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Get-ListenerPid {
    @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

Write-Host "ProxyPal restart" -ForegroundColor Cyan
Write-Host "Port: $Port" -ForegroundColor DarkGray

$listeners = Get-ListenerPid
foreach ($processId in $listeners) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    $commandLine = [string]$process.CommandLine
    if ($commandLine -notmatch 'gateway\.py') {
        Write-Host "[!] Port $Port belongs to another program (PID $processId). It was NOT stopped." -ForegroundColor Yellow
        Write-Host "    $commandLine" -ForegroundColor DarkGray
        exit 2
    }
    Write-Host "Stopping old gateway (PID $processId)..." -ForegroundColor Yellow
    Stop-Process -Id $processId -Force -ErrorAction Stop
}

$deadline = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $deadline -and (Get-ListenerPid).Count -gt 0) {
    Start-Sleep -Milliseconds 200
}
if ((Get-ListenerPid).Count -gt 0) {
    Write-Host "[ERROR] Port $Port is still busy. Close the old window and try again." -ForegroundColor Red
    exit 1
}

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

if (-not (Test-Path (Join-Path $root 'logs'))) {
    New-Item -ItemType Directory -Path (Join-Path $root 'logs') | Out-Null
}
$outLog = Join-Path $root 'logs\backend.log'
$errLog = Join-Path $root 'logs\backend.err.log'

Write-Host "Starting gateway..." -ForegroundColor Yellow
Start-Process -FilePath $python -ArgumentList 'gateway.py' -WorkingDirectory $root `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden

$version = 0
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 1
        if ($health.status -eq 'ok') { $version = [int]$health.version; break }
    } catch { }
    Start-Sleep -Milliseconds 400
}

if ($version -eq 0) {
    Write-Host "[ERROR] The gateway did not answer on port $Port." -ForegroundColor Red
    if (Test-Path $errLog) {
        Write-Host "----- last log lines -----" -ForegroundColor DarkGray
        Get-Content $errLog -Tail 15 -ErrorAction SilentlyContinue
        Write-Host "--------------------------" -ForegroundColor DarkGray
    }
    exit 1
}

Write-Host "[OK] Gateway is running (version $version)." -ForegroundColor Green
Write-Host "     http://127.0.0.1:$Port" -ForegroundColor DarkGray
Write-Host "     Logs: logs\backend.log / logs\backend.err.log" -ForegroundColor DarkGray
exit 0
