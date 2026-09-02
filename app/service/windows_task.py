import os
import sys
import subprocess
import shutil
from typing import Dict, Any, Optional

SERVICE_NAME = "AutonomousAgencyService"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
VBS_LAUNCHER = os.path.join(SCRIPTS_DIR, "agency_service.vbs")
PYTHON_EXE = sys.executable
PYTHONW_EXE = os.path.join(os.path.dirname(PYTHON_EXE), "pythonw.exe")
if not os.path.exists(PYTHONW_EXE):
    PYTHONW_EXE = PYTHON_EXE

STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
STARTUP_LINK = os.path.join(STARTUP_DIR, "AutonomousAgency.vbs")

REG_PATH = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

class WindowsServiceManager:
    """
    Manages the persistent Windows Background Service that auto-starts on Windows boot/logon,
    restarts on crash via supervisor, and persists state across reboots.
    """

    def install(self, service_name: str = SERVICE_NAME) -> Dict[str, Any]:
        """
        Registers the agency service to start automatically on Windows boot / user logon.
        Uses native Windows Registry Run key + Startup folder with zero administrator privilege requirements.
        """
        cmd_value = f'wscript.exe "{VBS_LAUNCHER}"'

        # 1. Register in HKCU Run Key (Standard Windows Auto-Start)
        ps_reg = f'Set-ItemProperty -Path "{REG_PATH}" -Name "{service_name}" -Value \'{cmd_value}\''
        res_reg = subprocess.run(["powershell", "-NoProfile", "-Command", ps_reg], capture_output=True, text=True)

        # 2. Copy launcher to Startup folder as secondary persistence layer
        if os.path.exists(STARTUP_DIR) and os.path.exists(VBS_LAUNCHER):
            try:
                shutil.copy2(VBS_LAUNCHER, STARTUP_LINK)
            except Exception:
                pass

        # 3. Optional: Try Task Scheduler if elevated
        ps_task = f"""
        $action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument '"{VBS_LAUNCHER}"' -WorkingDirectory "{BASE_DIR}"
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
        Register-ScheduledTask -TaskName "{service_name}" -Action $action -Trigger $trigger -Settings $settings -Force -ErrorAction SilentlyContinue | Out-Null
        """
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_task], capture_output=True)

        return {
            "success": True,
            "service_name": service_name,
            "auto_start": "Registered for automatic start on Windows boot / logon",
            "launcher": VBS_LAUNCHER,
            "working_directory": BASE_DIR,
            "crash_restart": "Active via supervisor loop with exponential backoff",
            "dashboard_url": "http://localhost:8000"
        }

    def uninstall(self, service_name: str = SERVICE_NAME) -> Dict[str, Any]:
        """Stops the running service and removes auto-start registration."""
        self.stop()

        # Remove from Registry
        ps_reg = f'Remove-ItemProperty -Path "{REG_PATH}" -Name "{service_name}" -ErrorAction SilentlyContinue'
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_reg], capture_output=True)

        # Remove from Startup folder
        if os.path.exists(STARTUP_LINK):
            try:
                os.remove(STARTUP_LINK)
            except Exception:
                pass

        # Remove from Task Scheduler if present
        subprocess.run(f'schtasks /Delete /TN "{service_name}" /F', shell=True, capture_output=True)

        return {"success": True, "service_name": service_name, "message": "Service uninstalled and stopped."}

    def start(self) -> Dict[str, Any]:
        """Starts the persistent agency service immediately in the background."""
        subprocess.Popen(["wscript.exe", VBS_LAUNCHER], cwd=BASE_DIR, shell=False)
        return {"success": True, "status": "STARTED", "dashboard": "http://localhost:8000"}

    def stop(self) -> Dict[str, Any]:
        """Terminates any running agency service background processes."""
        ps_kill = """
        Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -like "*app.service.runner*" -or
            $_.CommandLine -like "*app.api.app:app*"
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        """
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_kill], capture_output=True)
        return {"success": True, "status": "STOPPED"}

    def get_status(self, service_name: str = SERVICE_NAME) -> Dict[str, Any]:
        """Queries the current status of the service (installed, running, port listening)."""
        # Check registry
        ps_check_reg = f'(Get-ItemProperty -Path "{REG_PATH}" -ErrorAction SilentlyContinue)."{service_name}"'
        res_reg = subprocess.run(["powershell", "-NoProfile", "-Command", ps_check_reg], capture_output=True, text=True)
        is_installed = bool(res_reg.stdout.strip()) or os.path.exists(STARTUP_LINK)

        # Check process
        ps_check_proc = """
        $procs = Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -like "*app.service.runner*" -or
            $_.CommandLine -like "*app.api.app:app*"
        }
        if ($procs) { "RUNNING" } else { "STOPPED" }
        """
        res_proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps_check_proc], capture_output=True, text=True)
        is_running = "RUNNING" in res_proc.stdout

        # Check port 8000
        ps_port = "Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue"
        res_port = subprocess.run(["powershell", "-NoProfile", "-Command", ps_port], capture_output=True, text=True)
        port_open = "True" in res_port.stdout

        return {
            "service_name": service_name,
            "installed": is_installed,
            "running": is_running,
            "port_active": port_open,
            "dashboard_url": "http://localhost:8000" if port_open else None,
            "log_file": os.path.join(BASE_DIR, "logs", "agency_service.log"),
            "state": "RUNNING" if is_running else ("INSTALLED_STOPPED" if is_installed else "NOT_INSTALLED")
        }

windows_service_manager = WindowsServiceManager()
