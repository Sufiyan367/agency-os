@echo off
REM Autonomous Agency Background Launcher
cd /d "%~dp0\.."
echo Starting Autonomous Agency Background Service...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows_service.ps1"
pause
