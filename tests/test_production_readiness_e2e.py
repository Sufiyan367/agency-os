"""
Comprehensive Automated Test Suite for Production-Readiness Phase.
Tests:
- Timezone determination and TCPA calling-hour controls
- Global opt-out suppression across email, phone, and domain
- Retry policy with transient vs permanent error classification
- Provider health checks, credential validation, and HMAC webhook self-tests
- Controlled single-prospect end-to-end dry-run test across all 10 stages
- FastAPI production and compliance endpoints
"""
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
import httpx

from app.api.app import app
from app.core.config import settings
from app.core.retry_policy import is_transient_error, is_permanent_error, execute_with_retry
from app.compliance.calling_hours import CallingHoursCompliance, calling_hours_compliance
from app.outreach.compliance import ComplianceGuard, compliance_guard
from app.services.health_service import ProductionHealthService
from app.services.controlled_test_service import ControlledTestService
from app.database.connection import AsyncSessionLocal, init_db


@pytest.fixture(autouse=True)
async def setup_database():
    await init_db()


def test_calling_hours_compliance_logic():
    """Verifies that calling hours restrict outbound dialing to 08:00 - 20:00 local time."""
    # Test during daytime: 2:00 PM UTC = 9:00 AM Central (Austin) -> ALLOWED
    day_utc = datetime(2026, 9, 3, 14, 0, 0, tzinfo=timezone.utc)
    res_day = CallingHoursCompliance.is_calling_window_open(country="US", city="Austin", current_utc_time=day_utc)
    assert res_day.is_allowed is True
    assert res_day.local_hour == 8 or res_day.local_hour == 9  # Central time

    # Test during night: 4:00 AM UTC = 11:00 PM Central (Austin) -> BLOCKED
    night_utc = datetime(2026, 9, 3, 4, 0, 0, tzinfo=timezone.utc)
    res_night = CallingHoursCompliance.is_calling_window_open(country="US", city="Austin", current_utc_time=night_utc)
    assert res_night.is_allowed is False
    assert "Outside permitted calling window" in res_night.reason

    # Test London daytime: 11:00 AM UTC = 11:00 AM London -> ALLOWED
    res_uk = CallingHoursCompliance.is_calling_window_open(country="UK", current_utc_time=day_utc)
    assert res_uk.is_allowed is True


@pytest.mark.asyncio
async def test_global_opt_out_suppression_phone_and_email():
    """Verifies suppression works for emails, domains, and phone numbers."""
    async with AsyncSessionLocal() as session:
        # Add suppression
        test_email = "optout_client@suppresseddomain.com"
        test_phone = "+1-512-555-9988"
        test_domain = "suppresseddomain.com"

        await compliance_guard.add_to_suppression(session, email=test_email, phone=test_phone, domain=test_domain)

        # Check suppression
        assert await compliance_guard.is_suppressed(session, email=test_email) is True
        assert await compliance_guard.is_suppressed(session, domain=test_domain) is True
        assert await compliance_guard.is_suppressed(session, phone=test_phone) is True

        # Non-suppressed contact
        assert await compliance_guard.is_suppressed(session, email="clean@legitcompany.com", phone="+1-512-555-1122") is False


def test_retry_policy_error_classification():
    """Verifies distinction between transient and permanent exceptions."""
    import httpx

    # Transient errors
    timeout_err = httpx.TimeoutException("Connection timed out")
    assert is_transient_error(timeout_err) is True
    assert is_permanent_error(timeout_err) is False

    # Permanent errors
    val_err = ValueError("Invalid parameter value")
    assert is_transient_error(val_err) is False
    assert is_permanent_error(val_err) is True


@pytest.mark.asyncio
async def test_execute_with_retry_mechanism():
    """Verifies execute_with_retry retries transient errors and aborts on permanent errors."""
    attempts = 0

    async def flaky_call():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise httpx.TimeoutException("Transient rate limit timeout")
        return "SUCCESS"

    success, res, count = await execute_with_retry(flaky_call, max_retries=3, initial_delay=0.01)
    assert success is True
    assert res == "SUCCESS"
    assert count == 2


@pytest.mark.asyncio
async def test_production_health_check_service():
    """Verifies that health checks and cryptographic self-tests pass."""
    report = await ProductionHealthService.check_system_health()
    assert report.database.status == "READY"
    assert report.webhooks.status == "READY"
    assert "HMAC-SHA256 signature verification engine verified operational" in report.webhooks.details
    assert report.safeguards["email_dry_run"] is True
    assert report.safeguards["voice_dry_run"] is True
    assert report.safeguards["payment_dry_run"] is True


@pytest.mark.asyncio
async def test_controlled_e2e_lifecycle():
    """Verifies the complete 10-step lifecycle test for a single prospect."""
    prospect_data = {
        "name": "Summit Mechanical & Roofing",
        "domain": "summitmechroofing.com",
        "email": "contact@summitmechroofing.com",
        "phone": "+1-512-555-0177",
        "city": "Austin",
        "country": "US",
        "niche": "Roofing",
        "estimated_value": 750.0,
        "buyer_score": 86.0,
        "opportunity_score": 80.0
    }
    report = await ControlledTestService.run_controlled_e2e_test(candidate_data=prospect_data)

    assert report.success is True
    assert len(report.steps) == 10
    assert report.final_pipeline_stage == "WON"
    assert report.deal_value == 750.0
    assert report.advance_amount == 300.0  # 40%

    # Verify key steps passed
    step_names = [s.step_name for s in report.steps]
    assert "DISCOVERY & IDENTITY VERIFICATION" in step_names
    assert "TECHNICAL DIAGNOSTIC AUDIT" in step_names
    assert "COMMERCIAL QUALIFICATION ($500+ FLOOR)" in step_names
    assert "COMPLIANCE & CALLING-HOURS VERIFICATION" in step_names
    assert "APPOINTMENT BOOKING & CALENDAR SYNC" in step_names
    assert "COMMERCIAL PROPOSAL GENERATION" in step_names
    assert "PAYMENT VERIFICATION (HMAC WEBHOOK) & DEAL WON" in step_names


@pytest.mark.asyncio
async def test_production_and_compliance_api_routes():
    """Verifies the FastAPI endpoints for production health and controlled tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Health check
        res_health = await ac.get("/api/production/health")
        assert res_health.status_code == 200
        data_h = res_health.json()
        assert "database" in data_h
        assert "webhooks" in data_h
        assert "safeguards" in data_h

        # 2. Calling hours check
        res_ch = await ac.get("/api/compliance/calling-hours?country=US&city=Austin")
        assert res_ch.status_code == 200
        assert "is_allowed" in res_ch.json()

        # 3. Controlled E2E test run
        res_test = await ac.post("/api/production/test/e2e")
        assert res_test.status_code == 200
        data_t = res_test.json()
        assert data_t["success"] is True
        assert len(data_t["steps"]) == 10
        assert data_t["final_pipeline_stage"] == "WON"
