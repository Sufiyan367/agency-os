# Autonomous B2B Lead-Gen & Sales Agency — Windows Background Service Installer
# Registers a persistent Windows Scheduled Task that auto-starts on boot/logon and restarts on crash.

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$PythonExe = (Get-Command python).Source
$PythonwExe = Join-Path (Split-Path -Parent $PythonExe) "pythonw.exe"
if (-not (Test-Path $PythonwExe)) {
    $PythonwExe = $PythonExe
}

$TaskName = "AutonomousAgencyService"
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " Installing Autonomous Agency as a Persistent Windows Service... " -ForegroundColor Cyan
Write-Host " Project Directory: $ProjectDir" -ForegroundColor White
Write-Host " Python Executable: $PythonwExe" -ForegroundColor White
Write-Host " Task Name:         $TaskName" -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor Cyan

# Remove old task if exists
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Create Action, Trigger, Settings
$Action = New-ScheduledTaskAction `
    -Execute $PythonwExe `
    -Argument "-m app.service.runner" `
    -WorkingDirectory $ProjectDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -MultipleInstances IgnoreNew

# Register Task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Autonomous B2B Lead-Gen & Sales Agency Background Service (Continuous Lead Discovery, Audits, Follow-ups, Reply Monitoring, and Stripe Payments)" `
    -Force | Out-Null

Write-Host " Starting Service Task immediately..." -ForegroundColor Yellow
Start-ScheduledTask -TaskName $TaskName

Start-Sleep -Seconds 2

$TaskInfo = Get-ScheduledTask -TaskName $TaskName
Write-Host ""
Write-Host "[SUCCESS] Autonomous Agency Service is registered and running!" -ForegroundColor Green
Write-Host "  State:             $($TaskInfo.State)" -ForegroundColor Green
Write-Host "  Auto-Start:        On Windows boot / user logon" -ForegroundColor White
Write-Host "  Crash Recovery:    Auto-restarts 5 times every 1 minute" -ForegroundColor White
Write-Host "  Control Center UI: http://localhost:8000" -ForegroundColor Cyan
Write-Host "  Logs:              $ProjectDir\logs\agency_service.log" -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor Cyan
