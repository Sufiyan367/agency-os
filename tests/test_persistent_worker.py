import pytest
from unittest.mock import patch, AsyncMock
from app.orchestrator.worker import PersistentAgencyWorker
from app.database.models import SystemRun
from sqlalchemy import select

@pytest.mark.asyncio
async def test_persistent_worker_tick_execution():
    worker = PersistentAgencyWorker(interval_seconds=1)
    
    with patch("app.crm.inbox_poller.inbox_poller.poll_inbox", new_callable=AsyncMock) as mock_inbox, \
         patch("app.followups.engine.followup_engine.process_due_followups", new_callable=AsyncMock) as mock_fu, \
         patch("app.payments.provider.stripe_payment_provider.fetch_completed_sessions", new_callable=AsyncMock) as mock_pmt:
        mock_inbox.return_value = []
        mock_fu.return_value = []
        mock_pmt.return_value = []

        summary = await worker.execute_tick()
        assert summary["status"] == "SUCCESS"
        assert summary["inbox_replies_processed"] == 0
        assert summary["followups_dispatched"] == 0
        assert summary["payments_detected"] == 0
        assert worker.ticks_executed >= 1

@pytest.mark.asyncio
async def test_persistent_worker_automatic_payment_detection():
    worker = PersistentAgencyWorker(interval_seconds=1)
    
    fake_pmt = [{
        "business_id": 999,
        "reference_id": "cs_worker_auto_999",
        "amount_usd": 750.0,
        "customer_email": "auto@client.com"
    }]
    mock_provider = AsyncMock()
    mock_provider.fetch_completed_payments.return_value = fake_pmt
    with patch("app.crm.inbox_poller.inbox_poller.poll_inbox", new_callable=AsyncMock) as mock_inbox, \
         patch("app.followups.engine.followup_engine.process_due_followups", new_callable=AsyncMock) as mock_fu, \
         patch("app.orchestrator.worker.get_active_payment_provider", return_value=mock_provider), \
         patch("app.payments.service.payment_service.confirm_payment_and_onboard", new_callable=AsyncMock) as mock_onboard:
        mock_inbox.return_value = []
        mock_fu.return_value = []
        mock_onboard.return_value = {"status": "SUCCESS"}

        summary = await worker.execute_tick()
        assert summary["status"] == "SUCCESS"
        assert summary["payments_detected"] == 1
        mock_onboard.assert_called_once()

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
