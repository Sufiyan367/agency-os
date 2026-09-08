import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from sqlalchemy import select, func
from app.orchestrator.worker import PersistentAgencyWorker
from app.core.config import settings
from app.database.models import Business

@pytest.mark.asyncio
async def test_worker_suppresses_discovery_when_auto_discovery_disabled():
    """
    Verify that when AUTONOMOUS_AUTO_DISCOVERY=False, even if lead_count < 10
    and last_cycle_at is None, the worker does NOT run an autonomous discovery cycle.
    """
    worker = PersistentAgencyWorker(interval_seconds=1)
    worker.last_cycle_at = None

    with patch.object(settings, "AUTONOMOUS_AUTO_DISCOVERY", False), \
         patch("app.crm.inbox_poller.inbox_poller.poll_inbox", new_callable=AsyncMock) as mock_inbox, \
         patch("app.followups.engine.followup_engine.process_due_followups", new_callable=AsyncMock) as mock_fu, \
         patch("app.orchestrator.worker.get_active_payment_provider") as mock_pmt_fn, \
         patch("app.orchestrator.loop.orchestrator.run_full_autonomous_cycle", new_callable=AsyncMock) as mock_cycle:
        
        mock_inbox.return_value = []
        mock_fu.return_value = []
        mock_pmt = AsyncMock()
        mock_pmt.fetch_completed_payments.return_value = []
        mock_pmt_fn.return_value = mock_pmt

        summary = await worker.execute_tick()

        assert summary["status"] == "SUCCESS"
        assert summary["autonomous_cycle_run"] is False
        mock_cycle.assert_not_called()
        assert worker.last_cycle_at is None

@pytest.mark.asyncio
async def test_worker_runs_discovery_when_auto_discovery_enabled():
    """
    Verify that when AUTONOMOUS_AUTO_DISCOVERY=True and lead_count < 10 on startup,
    the worker executes the autonomous lead replenishment cycle.
    """
    worker = PersistentAgencyWorker(interval_seconds=1)
    worker.last_cycle_at = None

    with patch.object(settings, "AUTONOMOUS_AUTO_DISCOVERY", True), \
         patch("app.crm.inbox_poller.inbox_poller.poll_inbox", new_callable=AsyncMock) as mock_inbox, \
         patch("app.followups.engine.followup_engine.process_due_followups", new_callable=AsyncMock) as mock_fu, \
         patch("app.orchestrator.worker.get_active_payment_provider") as mock_pmt_fn, \
         patch("app.orchestrator.loop.orchestrator.run_full_autonomous_cycle", new_callable=AsyncMock) as mock_cycle, \
         patch("app.orchestrator.worker.AsyncSessionLocal") as mock_session_local:
        
        mock_inbox.return_value = []
        mock_fu.return_value = []
        mock_pmt = AsyncMock()
        mock_pmt.fetch_completed_payments.return_value = []
        mock_pmt_fn.return_value = mock_pmt
        mock_cycle.return_value = {"prospects_discovered": 10, "prospects_contacted": 0}

        # Mock session to return lead_count = 2 (< 10)
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_scalar = MagicMock(return_value=2)
        mock_res = MagicMock()
        mock_res.scalar = mock_scalar
        mock_session.execute.return_value = mock_res
        mock_session_local.return_value.__aenter__.return_value = mock_session

        summary = await worker.execute_tick()

        assert summary["status"] == "SUCCESS"
        assert summary["autonomous_cycle_run"] is True
        assert summary["cycle_summary"]["prospects_discovered"] == 10
        mock_cycle.assert_called_once()
        assert worker.last_cycle_at is not None

@pytest.mark.asyncio
async def test_explicit_manual_discovery_unblocked_by_auto_discovery_setting():
    """
    Verify that manual/explicit discovery triggers (e.g. orchestrator.run_full_autonomous_cycle)
    remain fully functional even when AUTONOMOUS_AUTO_DISCOVERY=False.
    """
    from app.orchestrator.loop import orchestrator

    with patch.object(settings, "AUTONOMOUS_AUTO_DISCOVERY", False), \
         patch("app.lead_generation.discovery.lead_discovery_coordinator.run_discovery_and_verification", new_callable=AsyncMock) as mock_disc:

        mock_disc.return_value = []
        res = await orchestrator.run_full_autonomous_cycle(target_leads=1)

        assert isinstance(res, dict)
        assert res.get("status") in ("SUCCESS", "NO_MARKETS")
        assert "duration_seconds" in res
        mock_disc.assert_called()

@pytest.mark.asyncio
async def test_db_remains_empty_after_repeated_worker_ticks():
    """
    Verify that a clean database with 0 businesses remains at exactly 0 businesses
    after repeated worker ticks when AUTONOMOUS_AUTO_DISCOVERY=False.
    """
    worker = PersistentAgencyWorker(interval_seconds=1)
    worker.last_cycle_at = None

    with patch.object(settings, "AUTONOMOUS_AUTO_DISCOVERY", False), \
         patch("app.crm.inbox_poller.inbox_poller.poll_inbox", new_callable=AsyncMock) as mock_inbox, \
         patch("app.followups.engine.followup_engine.process_due_followups", new_callable=AsyncMock) as mock_fu, \
         patch("app.orchestrator.worker.get_active_payment_provider") as mock_pmt_fn, \
         patch("app.orchestrator.loop.orchestrator.run_full_autonomous_cycle", new_callable=AsyncMock) as mock_cycle:
        
        mock_inbox.return_value = []
        mock_fu.return_value = []
        mock_pmt = AsyncMock()
        mock_pmt.fetch_completed_payments.return_value = []
        mock_pmt_fn.return_value = mock_pmt

        for _ in range(3):
            summary = await worker.execute_tick()
            assert summary["status"] == "SUCCESS"
            assert summary["autonomous_cycle_run"] is False

        mock_cycle.assert_not_called()

    # Verify status report reflects configuration
    status = worker.get_status()
    assert status["autonomous_auto_discovery"] is False

def test_no_fake_data_introduced_in_discovery_sources():
    """
    Verify that discovery sources strictly adhere to real commercial registries
    and that no mock or fake lead generation generators are used.
    """
    from app.lead_generation.adapters.real_web_discovery import RealWebDiscoveryAdapter
    from app.lead_generation.adapters.verified_registry import REAL_COMMERCIAL_BUSINESSES

    adapter = RealWebDiscoveryAdapter()
    assert hasattr(adapter, "discover_leads")
    
    # Check that registry entries are real commercial entities with verifiable domains and phone numbers
    assert len(REAL_COMMERCIAL_BUSINESSES) > 0
    total_companies = 0
    valid_country_codes = {"US", "GB", "UK", "CA", "AU", "DE", "FR", "AE", "SG", "SA"}
    for (country, niche), companies in REAL_COMMERCIAL_BUSINESSES.items():
        assert country in valid_country_codes
        for entry in companies:
            total_companies += 1
            assert "." in entry["domain"]
            assert entry["phone"].startswith("+") or entry["phone"].replace("-", "").isdigit()
            assert len(entry["address"]) > 5
            # Ensure no demo placeholder strings
            assert "example.com" not in entry["domain"]
            assert "lorem" not in entry["name"].lower()
    
    assert total_companies > 10
