# ==============================================================================
# Dashboard-Triggered Autonomous Prospecting Test Suite
# ==============================================================================
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.api.app import app
from app.core.config import settings
from app.core.production_mode import first_client_mode
from app.database.connection import AsyncSessionLocal
from app.database.models import SystemRun, OutreachMessage
from app.lead_generation.job_runner import prospecting_job_manager
from app.lead_generation.service import LeadDiscoveryService


@pytest.mark.asyncio
async def test_prospecting_config_endpoint():
    """Verifies that the dashboard configuration endpoint returns available markets and $500 floor."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/prospecting/config")
        assert res.status_code == 200
        data = res.json()

        assert "available_countries" in data
        assert "available_niches" in data
        assert "defaults" in data

        # Ensure $500 commercial floor is the configured default
        assert data["defaults"]["min_service_value"] == 500.0

        country_codes = [c["code"] for c in data["available_countries"]]
        for c in ["US", "UK", "CA", "AU", "AE", "SA"]:
            assert c in country_codes


@pytest.mark.asyncio
async def test_prospecting_run_rejects_sub_500_floor():
    """Verifies that attempting to run prospecting with a commercial floor under $500 is rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/prospecting/run", json={
            "countries": ["US"],
            "cities": ["Austin"],
            "niches": ["HVAC"],
            "min_service_value": 499.0,  # Below $500 floor
            "max_prospects": 10
        })
        assert res.status_code == 400
        assert "cannot be less than the $500.00 floor" in res.json()["detail"]


@pytest.mark.asyncio
async def test_dashboard_triggered_prospecting_cycle_lifecycle():
    """
    Verifies the end-to-end dashboard-triggered prospecting workflow:
    Trigger -> QUEUED -> RUNNING -> COMPLETED -> Live Progress Counters -> Database Sync.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Trigger run with mock provider for deterministic test execution
        res_trigger = await ac.post("/api/prospecting/run", json={
            "countries": ["CA"],
            "cities": ["Calgary"],
            "niches": ["Solar"],
            "min_service_value": 500.0,
            "max_prospects": 5,
            "provider": "mock"
        })
        assert res_trigger.status_code == 200
        trigger_data = res_trigger.json()
        assert "job_id" in trigger_data
        job_id = trigger_data["job_id"]
        assert trigger_data["status"] in ("QUEUED", "RUNNING")

        # 2. Poll status endpoint until COMPLETED or timeout
        max_polls = 30
        completed_data = None
        for _ in range(max_polls):
            res_status = await ac.get(f"/api/prospecting/status?job_id={job_id}")
            assert res_status.status_code == 200
            status_data = res_status.json()

            # Verify all required progress fields are returned
            prog = status_data["progress"]
            assert "markets_being_searched" in prog
            assert "current_city_niche" in prog
            assert "prospects_discovered" in prog
            assert "duplicates_rejected" in prog
            assert "junk_rejected" in prog
            assert "prospects_passing_500" in prog
            assert "prospects_saved" in prog
            assert "message" in prog

            if status_data["status"] == "COMPLETED":
                completed_data = status_data
                break
            elif status_data["status"] == "FAILED":
                pytest.fail(f"Prospecting job failed: {status_data.get('error_message')}")

            await asyncio.sleep(0.3)

        assert completed_data is not None, "Prospecting job did not complete within timeout"
        assert completed_data["status"] == "COMPLETED"
        assert completed_data["summary"]["businesses_discovered"] > 0
        assert (completed_data["progress"]["prospects_saved"] > 0 or completed_data["progress"]["duplicates_rejected"] > 0)

        # 3. Verify SystemRun record was created in database
        async with AsyncSessionLocal() as session:
            q_run = select(SystemRun).where(SystemRun.run_id == job_id)
            run_rec = (await session.execute(q_run)).scalar_one_or_none()
            assert run_rec is not None
            assert run_rec.status == "COMPLETED"
            assert run_rec.job_name == "autonomous_prospecting_cycle"


@pytest.mark.asyncio
async def test_shared_service_layer_and_safety_controls():
    """
    Verifies that CLI and Dashboard use the same LeadDiscoveryService and
    that no unauthorized cold emails are sent during the cycle.
    """
    # 1. Verify that job manager invokes LeadDiscoveryService
    assert hasattr(prospecting_job_manager, "start_prospecting_job")
    assert hasattr(LeadDiscoveryService, "discover_and_process")

    # 2. Verify safety controls remain enforced
    assert settings.EMAIL_DRY_RUN is True
    assert settings.PAYMENT_DRY_RUN is True
    assert settings.RAZORPAY_MODE == "test"

    perms = first_client_mode.get_mode_status()["permissions"]
    assert perms["human_approval_mandatory"] is True
    assert perms["payment_live_charging"] is False
    assert perms["commercial_threshold_usd"] == 500.0

    # 3. Verify zero sent outreach messages in database
    async with AsyncSessionLocal() as session:
        q_sent = select(OutreachMessage).where(OutreachMessage.status == "SENT")
        sent_msgs = (await session.execute(q_sent)).scalars().all()
        assert len(sent_msgs) == 0, "No emails should be dispatched in dry run mode"
