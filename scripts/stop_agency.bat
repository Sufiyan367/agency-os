@echo off
REM Autonomous Agency Background Stopper
cd /d "%~dp0\.."
echo Stopping Autonomous Agency Background Service...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_windows_service.ps1"
pause
