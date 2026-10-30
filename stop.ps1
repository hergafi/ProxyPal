# ProxyPal - stop the backend and the dev server.
# Port-based, and only stops the expected processes.
param([int]$BackendPort = 8790, [int]$FrontendPort = 5173)

$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "Stopping ProxyPal servers..." -ForegroundColor Cyan

function Stop-ExpectedProcess([int]$Port, [string]$Pattern, [string]$Label) {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    $stopped = 0
    foreach ($processId in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        if (-not $process) { continue }
        $commandLine = [string]$process.CommandLine
        if ($commandLine -notmatch $Pattern) {
            Write-Host "     [!] $Label port $Port belongs to another program (PID $processId); left running." -ForegroundColor Yellow
            continue
        }
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        $stopped++
    }
    if ($stopped) {
        Write-Host "     [OK] $Label stopped." -ForegroundColor Green
    } else {
        Write-Host "     [--] $Label was not running." -ForegroundColor DarkGray
    }
}

Stop-ExpectedProcess $BackendPort 'gateway\.py' 'Backend'
Stop-ExpectedProcess $FrontendPort 'modern-workspace|vite' 'Frontend'

Write-Host ""
Write-Host "Done." -ForegroundColor Cyan
