@echo off
setlocal enabledelayedexpansion

title Agency OS -- CEO Dashboard Launcher
cd /d "%~dp0"

echo ======================================================================
echo   Agency OS -- Autonomous B2B Operations ^& CEO Control Center
echo ======================================================================
echo.

:: Optional restart flag check
if /i "%~1"=="--restart" goto :restart_process
if /i "%~1"=="-r" goto :restart_process
goto :check_running

:restart_process
echo [*] Restart requested. Stopping existing Agency OS server...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue; if ($conn) { foreach ($p in $conn.OwningProcess | Select-Object -Unique) { if ($p -gt 0) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } } }" >nul 2>&1
timeout /t 1 /nobreak >nul 2>&1

:check_running
echo [*] Checking backend server status...

:: Check if server is already responding on port 8000
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'SilentlyContinue'; try { $res = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 1; if ($res.StatusCode -eq 200 -and $res.Content -match 'Autonomous B2B') { exit 0 } } catch {}; exit 1" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [*] Agency OS server is verified and running!
    echo [*] Opening CEO Dashboard in your default browser...
    start http://localhost:8000/dashboard
    goto :done
)

:: Locate Python executable (.venv preferred)
set "PY_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    for %%P in (python.exe) do set "PY_EXE=%%~$PATH:P"
)

if "%PY_EXE%"=="" (
    echo [!] ERROR: Python runtime not found.
    echo Please ensure Python or .venv is installed.
    pause
    exit /b 1
)

echo [*] Starting Agency OS server in background...
start "" /b "%PY_EXE%" -m app.cli serve --host 127.0.0.1 --port 8000

echo [*] Initializing services and verifying health...
powershell -NoProfile -ExecutionPolicy Bypass -Command "for ($i=0; $i -lt 25; $i++) { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Milliseconds 750 }; exit 1" >nul 2>&1

if %ERRORLEVEL% neq 0 (
    echo [!] Server took longer than expected to report healthy. Opening dashboard anyway...
) else (
    echo [*] Server is healthy and operational!
)

echo [*] Launching CEO Control Center...
start http://localhost:8000/dashboard

:done
echo [*] Done. You can close this window at any time.
exit /b 0
