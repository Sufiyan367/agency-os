# Autonomous B2B Lead-Gen & Sales Agency — Windows Background Service Uninstaller

$TaskName = "AutonomousAgencyService"
Write-Host "Stopping and removing $TaskName..." -ForegroundColor Yellow

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Write-Host "[SUCCESS] $TaskName has been completely removed from Windows Task Scheduler." -ForegroundColor Green
