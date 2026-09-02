import pytest
from unittest.mock import patch
from app.service.windows_task import WindowsServiceManager

def test_windows_service_status_installed_and_running():
    mgr = WindowsServiceManager()
    with patch("subprocess.run") as mock_run, \
         patch("os.path.exists", return_value=True):
        # 1st call: reg check -> returns cmd
        # 2nd call: proc check -> returns RUNNING
        # 3rd call: port check -> returns True
        mock_proc_running = type("ProcessResult", (), {"stdout": "RUNNING", "returncode": 0})
        mock_reg_installed = type("ProcessResult", (), {"stdout": "wscript.exe", "returncode": 0})
        mock_port_open = type("ProcessResult", (), {"stdout": "True", "returncode": 0})
        mock_run.side_effect = [mock_reg_installed, mock_proc_running, mock_port_open]

        status = mgr.get_status("AutonomousAgencyService")
        assert status["installed"] is True
        assert status["running"] is True
        assert status["state"] == "RUNNING"
        assert status["port_active"] is True
        assert status["service_name"] == "AutonomousAgencyService"

def test_windows_service_status_not_installed():
    mgr = WindowsServiceManager()
    with patch("subprocess.run") as mock_run, \
         patch("os.path.exists", return_value=False):
        mock_empty = type("ProcessResult", (), {"stdout": "", "returncode": 0})
        mock_stopped = type("ProcessResult", (), {"stdout": "STOPPED", "returncode": 0})
        mock_port_closed = type("ProcessResult", (), {"stdout": "False", "returncode": 0})
        mock_run.side_effect = [mock_empty, mock_stopped, mock_port_closed]

        status = mgr.get_status("NonexistentService")
        assert status["installed"] is False
        assert status["running"] is False
        assert status["state"] == "NOT_INSTALLED"

def test_windows_service_install_mocked():
    mgr = WindowsServiceManager()
    with patch("subprocess.run") as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("shutil.copy2"):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        res = mgr.install("TestAgencyService")
        assert res["success"] is True
        assert res["service_name"] == "TestAgencyService"
        assert "Windows boot / logon" in res["auto_start"]

def test_windows_service_uninstall_mocked():
    mgr = WindowsServiceManager()
    with patch("subprocess.run") as mock_run, \
         patch("os.path.exists", return_value=False):
        mock_run.return_value.returncode = 0

        res = mgr.uninstall("TestAgencyService")
        assert res["success"] is True
        assert res["service_name"] == "TestAgencyService"
