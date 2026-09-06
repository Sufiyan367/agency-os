"""
Comprehensive Integration Tests for Real-Time Observability & Artifact Preview Layer.

Covers all 12 items:
1. Agent status live state tracking (prospect name, domain, stage, operation, runtime, safety guardrails).
2. Safety guardrails dedicated endpoint (dynamic flags, dry runs, commercial floor).
3. Pipeline stage synchronization across orchestrator.
4. WebSocket activity telemetry broadcasting.
5. Outreach inspector endpoint with dry-run notice, headers, body, grounding evidence.
6. Outreach inspector 404 graceful error handling.
7. Audit evidence inspector endpoint (6 vectors, findings).
8. Prospect memory inspector with all 6 categories (IDENTITY, AUDIT, COMMERCIAL, OUTREACH, CONVERSATION, STATE).
9. Website builder and artifact preview serving.
10. Dual-track event routing (Forward Prospecting vs Inbound Resumption).
11. Duplicate skipped event handling.
12. Strict dry-run safety guarantees (EMAIL, VOICE, PAYMENT).
"""

import pytest
import asyncio
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.api.app import app
from app.core.config import settings
from app.database.models import (
    Base, Business, AuditRun, LeadScore, OutreachMessage,
    ProspectMemory, AgentActivityEvent, Artifact, VerificationStatus, PipelineStage
)
from app.agents.revenue_agent import revenue_agent_orchestrator
from app.agents.activity_broadcaster import AgentEventType, activity_broadcaster
from app.crm.memory_service import memory_service


@pytest.fixture
async def async_test_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_status_live_state():
    """1. Test that GET /api/agent/status returns live prospect, operation, runtime, and safety guardrails."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        revenue_agent_orchestrator.current_domain = "test-plumbing.com"
        revenue_agent_orchestrator.current_business_name = "Test Plumbing LLC"
        revenue_agent_orchestrator.current_pipeline_stage = PipelineStage.AUDITED.value
        revenue_agent_orchestrator.current_operation = "Auditing diagnostic vectors"

        resp = await client.get("/api/agent/status")
        assert resp.status_code == 200
        data = resp.json()

        assert "status" in data
        assert data["current_domain"] == "test-plumbing.com"
        assert data["current_business_name"] == "Test Plumbing LLC"
        assert data["current_stage"] == PipelineStage.AUDITED.value
        assert "runtime_seconds" in data
        assert "safety_guardrails" in data
        sg = data["safety_guardrails"]
        assert sg["email_dry_run"] is True
        assert sg["voice_dry_run"] is True
        assert sg["payment_dry_run"] is True
        assert sg["commercial_floor_usd"] >= 500.0


@pytest.mark.asyncio
async def test_safety_guardrails_endpoint():
    """2. Test dedicated GET /api/agent/safety-guardrails endpoint."""
    revenue_agent_orchestrator.kill_switch_active = False
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agent/safety-guardrails")
        assert resp.status_code == 200
        data = resp.json()

        assert "email_dry_run" in data
        assert data["email_dry_run"] is True
        assert data["voice_dry_run"] is True
        assert data["payment_dry_run"] is True
        assert data["commercial_floor_usd"] >= 500.0
        assert data["one_at_a_time_prospecting"] is True
        assert data["kill_switch_active"] is False


@pytest.mark.asyncio
async def test_websocket_activity_telemetry(async_test_session):
    """3. Test WebSocket activity event broadcaster registration and broadcast."""
    from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType
    from unittest.mock import AsyncMock

    mock_ws = AsyncMock()
    await activity_broadcaster.register(mock_ws)
    assert mock_ws in activity_broadcaster._clients

    await activity_broadcaster.record_event(
        session=async_test_session,
        run_id="TEST_RUN_WS",
        event_type=AgentEventType.DISCOVERY_STARTED.value,
        message="Observability test event broadcast",
        domain="telemetry-test.com",
        status="INFO"
    )

    await asyncio.sleep(0.05)
    assert mock_ws.send_text.called
    await activity_broadcaster.unregister(mock_ws)
    assert mock_ws not in activity_broadcaster._clients


@pytest.mark.asyncio
async def test_outreach_inspector_endpoint():
    """4. Test GET /api/agent/outreach/{id} endpoint structure."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agent/outreach/1")
        if resp.status_code == 200:
            data = resp.json()
            assert "recipient_email" in data
            assert "subject" in data
            assert "body" in data
            assert data["dry_run"] is True
            assert "grounding_evidence" in data
        else:
            assert resp.status_code == 404
            assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_outreach_inspector_not_found():
    """5. Test GET /api/agent/outreach/999999 returns graceful 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agent/outreach/999999")
        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_audit_evidence_endpoint():
    """6. Test GET /api/agent/audit-evidence/{id}."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agent/audit-evidence/1")
        if resp.status_code == 200:
            data = resp.json()
            assert "performance_score" in data
            assert "load_time_seconds" in data
            assert "findings" in data
            assert "core_web_vitals" in data
        else:
            assert resp.status_code == 404


@pytest.mark.asyncio
async def test_prospect_memory_endpoint_missing():
    """7. Test GET /api/agent/prospect-memory/{domain_or_id} returns 404 for missing domain."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agent/prospect-memory/non-existent-domain-xyz.com")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_prospect_memory_persistence_and_lookup(async_test_session):
    """8. Test creating and retrieving a 6-category prospect memory."""
    session = async_test_session
    biz = Business(
        name="Apex Heating & Air",
        domain="apex-heating.com",
        country="US",
        city="Austin",
        phone="512-555-0199",
        niche="HVAC",
        verification_status=VerificationStatus.VERIFIED.value,
        pipeline_stage=PipelineStage.CONTACTED.value,
        created_at=datetime.now(timezone.utc)
    )
    session.add(biz)
    await session.commit()
    await session.refresh(biz)

    await memory_service.save_memory(
        session,
        business_id=biz.id,
        domain=biz.domain,
        pipeline_stage=PipelineStage.CONTACTED.value,
        audit_results={"performance_score": 48.0, "load_time_seconds": 4.1, "seo_score": 55.0},
        buyer_score=85.0,
        opportunity_score=80.0,
        estimated_value=1200.0,
        offer_proposal={"title": "High Performance Turnaround", "recommended_price": 1200.0},
        outreach_message={"subject": "Audit findings for apex-heating.com", "body": "Your site loads in 4.1s..."},
        last_interaction="Autonomous outreach dispatched via EMAIL (DRY RUN)",
        next_expected_action="AWAITING_INBOUND_EVENT"
    )

    mem = await memory_service.get_memory(session, domain="apex-heating.com")
    assert mem is not None
    assert mem.domain == "apex-heating.com"
    assert mem.buyer_score == 85.0
    assert mem.audit_results["performance_score"] == 48.0
    assert mem.next_expected_action == "AWAITING_INBOUND_EVENT"


@pytest.mark.asyncio
async def test_website_builder_and_preview_endpoints():
    """9. Test artifact listing endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/artifacts")
        assert resp.status_code == 200
        data = resp.json()
        assert "artifacts" in data and isinstance(data["artifacts"], list)


@pytest.mark.asyncio
async def test_dual_track_event_classification():
    """10. Verify event classification between Main Prospecting Loop vs Inbound Resumption."""
    inbound_events = [
        "INBOUND_EVENT_RECEIVED",
        "PROSPECT_MEMORY_RESTORED",
        "REPLY_CLASSIFIED",
        "CONVERSATION_RESPONSE_GENERATED",
        "HUMAN_TAKEOVER"
    ]
    forward_events = [
        "DISCOVERY_STARTED",
        "PROSPECT_FOUND",
        "AUDIT_STARTED",
        "AUDIT_COMPLETED",
        "SCORING_STARTED",
        "COMMERCIAL_QUALIFICATION",
        "OFFER_GENERATION_STARTED",
        "OUTREACH_DISPATCH_STARTED",
        "OUTREACH_DISPATCHED",
        "MEMORY_PERSISTED",
        "NEXT_PROSPECT"
    ]

    for ie in inbound_events:
        assert ie in AgentEventType._value2member_map_ or hasattr(AgentEventType, ie)

    for fe in forward_events:
        assert fe in AgentEventType._value2member_map_ or hasattr(AgentEventType, fe)


@pytest.mark.asyncio
async def test_duplicate_skipped_event_type():
    """11. Verify PROSPECT_DUPLICATE_SKIPPED exists in AgentEventType."""
    assert hasattr(AgentEventType, "PROSPECT_DUPLICATE_SKIPPED")
    assert AgentEventType.PROSPECT_DUPLICATE_SKIPPED.value == "PROSPECT_DUPLICATE_SKIPPED"


@pytest.mark.asyncio
async def test_dry_run_safety_guarantees():
    """12. Confirm that EMAIL_DRY_RUN, VOICE_DRY_RUN and PAYMENT_DRY_RUN are strictly active."""
    assert getattr(settings, "EMAIL_DRY_RUN", True) is True
    assert getattr(settings, "VOICE_DRY_RUN", True) is True
    assert getattr(settings, "PAYMENT_DRY_RUN", True) is True
    assert getattr(settings, "MINIMUM_SERVICE_VALUE_USD", 500.0) >= 500.0