import pytest
from unittest.mock import patch, AsyncMock
from app.orchestrator.worker import PersistentAgencyWorker
from app.database.models import SystemRun
from sqlalchemy import select

@pytest.mark.asyncio
async def test_persistent_worker_tick_execution():
    worker = PersistentAgencyWorker(interval_seconds=1)
    
    with patch("app.crm.inbox_poller.inbox_poller.poll_inbox", new_callable=AsyncMock) as mock_inbox, \
         patch("app.followups.engine.followup_engine.process_due_followups", new_callable=AsyncMock) as mock_fu:
        mock_inbox.return_value = []
        mock_fu.return_value = []

        summary = await worker.execute_tick()
        assert summary["status"] == "SUCCESS"
        assert summary["inbox_replies_processed"] == 0
        assert summary["followups_dispatched"] == 0
        assert worker.ticks_executed >= 1

@pytest.mark.asyncio
async def test_persistent_worker_error_recovery():
    worker = PersistentAgencyWorker(interval_seconds=1)

    with patch("app.crm.inbox_poller.inbox_poller.poll_inbox", side_effect=RuntimeError("Simulated transient network glitch")):
        summary = await worker.execute_tick()
        # Worker tick records error in summary and SystemRun, but does not throw unhandled exception
        assert summary["status"] == "ERROR"
        assert "Simulated transient network glitch" in summary["error"]

def test_persistent_worker_status():
    worker = PersistentAgencyWorker(interval_seconds=45)
    status = worker.get_status()
    assert status["is_running"] is False
    assert status["interval_seconds"] == 45
    assert status["email_provider"] in ("dry_run", "resend", "sendgrid", "smtp")
