# Setup Windows Task Scheduler for morning/night scripts
# Run this script ONCE as Administrator to create the scheduled tasks

$ErrorActionPreference = "Stop"

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "Setting up scheduled tasks..." -ForegroundColor Cyan

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$morningScript = Join-Path $scriptPath "morning-startup.ps1"
$nightScript = Join-Path $scriptPath "night-shutdown.ps1"
$logFile = Join-Path $scriptPath "scheduler.log"

# Create log file if it doesn't exist
if (-not (Test-Path $logFile)) {
    New-Item -Path $logFile -ItemType File -Force | Out-Null
    Write-Host "Created log file: $logFile" -ForegroundColor Green
}

# Morning Task - 8 AM, Sun-Thu
Write-Host "Creating morning startup task (8 AM, Sun-Thu)..." -ForegroundColor Yellow
$morningAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$morningScript`" && echo `"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Morning startup completed`" >> `"$logFile`""
$morningTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday,Monday,Tuesday,Wednesday,Thursday -At 8:00AM
$morningSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "LEIDOS_Morning_Startup" -Action $morningAction -Trigger $morningTrigger -Settings $morningSettings -Description "Starts LEIDOS infrastructure at 8 AM (Sun-Thu)" -Force | Out-Null
Write-Host "  Created: LEIDOS_Morning_Startup" -ForegroundColor Green

# Night Task - 6 PM, Sun-Thu
Write-Host "Creating night shutdown task (6 PM, Sun-Thu)..." -ForegroundColor Yellow
$nightAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$nightScript`" && echo `"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Night shutdown completed`" >> `"$logFile`""
$nightTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday,Monday,Tuesday,Wednesday,Thursday -At 6:00PM
$nightSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "LEIDOS_Night_Shutdown" -Action $nightAction -Trigger $nightTrigger -Settings $nightSettings -Description "Shuts down LEIDOS infrastructure at 6 PM (Sun-Thu)" -Force | Out-Null
Write-Host "  Created: LEIDOS_Night_Shutdown" -ForegroundColor Green

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Scheduled tasks created:" -ForegroundColor Cyan
Write-Host "  - Morning Startup: 8:00 AM (Sun, Mon, Tue, Wed, Thu)" -ForegroundColor Gray
Write-Host "  - Night Shutdown:  6:00 PM (Sun, Mon, Tue, Wed, Thu)" -ForegroundColor Gray
Write-Host ""
Write-Host "Log file: $logFile" -ForegroundColor Cyan
Write-Host ""
Write-Host "To view tasks: Open Task Scheduler and look for 'LEIDOS_*'" -ForegroundColor Yellow
Write-Host "To disable: Right-click task in Task Scheduler and select 'Disable'" -ForegroundColor Yellow
Write-Host "To remove: Run: Remove-ScheduledTask -TaskName 'LEIDOS_Morning_Startup' -Confirm:`$false" -ForegroundColor Yellow
