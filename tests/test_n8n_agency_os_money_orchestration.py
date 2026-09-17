"""
Focused Integration Test Suite: Agency OS + Existing N8N as One Money-First Operating System.

Covers the 12 required invariants:
1. Agency OS -> n8n event forwarding
2. n8n -> existing Agency OS API (/api/inbound/webhook)
3. Qualified lead notification triggers CEO approval context
4. CEO approval handoff observes Agency OS dispatch without duplicate sender
5. Real reply alert triggers operator task
6. DEMO_REQUESTED handoff generates demo without revenue implication
7. Payment action alert notifies operator for review
8. Confirmed-payment handoff unlocks onboarding
9. Duplicate event / idempotency deduplication
10. No fake/synthetic event becomes real
11. No automation bypasses CEO approval (safety gate)
12. Dashboard reflects canonical state and n8n telemetry
"""

import pytest
import uuid
from httpx import AsyncClient, ASGITransport

from app.api.app import app
from app.core.event_bus import AgencyEvent, event_bus
from app.automations.n8n_orchestrator import n8n_orchestrator, InboundN8nEnvelope
from app.database.models import Business, PipelineStage
from app.analytics.truth_engine import get_canonical_production_truth
from sqlalchemy import select


@pytest.fixture(autouse=True)
def setup_n8n_bridge():
    """Ensures n8n orchestrator is hooked into event bus with clean state before tests."""
    n8n_orchestrator.hook_event_bus()
    n8n_orchestrator._mock_sink.clear()
    n8n_orchestrator._seen_execution_ids.clear()
    n8n_orchestrator._seen_event_ids.clear()
    event_bus.clear()
    event_bus.subscribe("*", n8n_orchestrator.handle_agency_event)
    yield
    n8n_orchestrator._mock_sink.clear()


@pytest.mark.asyncio
async def test_1_agency_os_to_n8n_event():
    """Invariant 1: Agency OS lifecycle events are translated into canonical n8n event envelopes."""
    evt = AgencyEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        correlation_id="CORR-TEST-001",
        event_type="COMMERCIAL_QUALIFICATION",
        entity_type="business",
        entity_id=101,
        payload={"score": 82.5, "niche": "dental", "domain": "austindental.com"}
    )
    published = await event_bus.publish(evt)
    assert published is True

    # Verify event was forwarded to n8n sink
    assert len(n8n_orchestrator._mock_sink) > 0
    forwarded = n8n_orchestrator._mock_sink[-1]
    assert forwarded["source"] == "agency_os.core"
    assert forwarded["entity_id"] == 101
    assert forwarded["correlation_id"] == "CORR-TEST-001"
    assert forwarded["payload"]["target_workflow"] == "lead_qualification"


@pytest.mark.asyncio
async def test_2_n8n_to_existing_agency_os_api():
    """Invariant 2: Inbound webhook from n8n integration edge is accepted by Agency OS."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "event_id": f"n8n_evt_{uuid.uuid4().hex[:12]}",
            "event_type": "N8N_WORKFLOW_EXECUTED",
            "source": "agency_os.n8n_edge",
            "correlation_id": "CORR-EDGE-002",
            "payload": {
                "action": "OPERATOR_NOTE_ADDED",
                "note": "Prospect verified via n8n domain enrichment workflow"
            }
        }
        res = await ac.post("/api/inbound/webhook", json=payload)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["success"] is True
        assert data["status"] == "NOTE_RECORDED"


@pytest.mark.asyncio
async def test_3_qualified_lead_notification():
    """Invariant 3: Qualified lead (score >= 55) triggers preparation of CEO approval context."""
    evt = AgencyEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        correlation_id="CORR-QUAL-003",
        event_type="COMMERCIAL_QUALIFICATION",
        entity_type="business",
        entity_id=102,
        payload={"score": 77.0, "status": "QUALIFIED"}
    )
    await event_bus.publish(evt)

    assert len(n8n_orchestrator._mock_sink) > 0
    latest = n8n_orchestrator._mock_sink[-1]
    ctx = latest["payload"]["orchestration_context"]
    assert ctx["action"] == "PREPARE_CEO_APPROVAL_CONTEXT"
    assert ctx["requires_ceo_review"] is True
    assert ctx["business_id"] == 102


@pytest.mark.asyncio
async def test_4_ceo_approval_handoff():
    """Invariant 4: CEO approval handoff observes Agency OS dispatch without creating a second sender."""
    evt = AgencyEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        correlation_id="CORR-APPR-004",
        event_type="OUTREACH_APPROVED",
        entity_type="outreach_message",
        entity_id=205,
        payload={"message_id": 205, "approved_by": "CEO"}
    )
    await event_bus.publish(evt)

    assert len(n8n_orchestrator._mock_sink) > 0
    latest = n8n_orchestrator._mock_sink[-1]
    assert latest["payload"]["target_workflow"] == "personalized_outreach"
    ctx = latest["payload"]["orchestration_context"]
    assert ctx["action"] == "OUTREACH_APPROVED_OBSERVED"
    assert "Agency OS sender handles physical dispatch" in ctx["note"]


@pytest.mark.asyncio
async def test_5_reply_alert():
    """Invariant 5: Real customer reply triggers immediate CEO alert and follow-up task."""
    evt = AgencyEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        correlation_id="CORR-REP-005",
        event_type="REPLY_CLASSIFIED",
        entity_type="reply",
        entity_id=301,
        payload={"reply_id": 301, "intent": "INTERESTED", "sentiment": "POSITIVE"}
    )
    await event_bus.publish(evt)

    assert len(n8n_orchestrator._mock_sink) > 0
    latest = n8n_orchestrator._mock_sink[-1]
    assert latest["payload"]["target_workflow"] == "reply_classification"
    ctx = latest["payload"]["orchestration_context"]
    assert ctx["action"] == "ALERT_CEO_REAL_REPLY"
    assert ctx["intent"] == "INTERESTED"
    assert ctx["urgency"] == "HIGH"


@pytest.mark.asyncio
async def test_6_demo_requested_handoff(db_session):
    """Invariant 6: DEMO_REQUESTED handoff uses Demo Factory with explicit non-revenue implication."""
    biz = Business(
        name="Apex Diagnostics",
        domain="apexdiagnostics.com",
        website_url="https://apexdiagnostics.com",
        country="US",
        niche="medical-clinics",
        public_email="info@apexdiagnostics.com",
        pipeline_stage=PipelineStage.DEMO_REQUESTED.value
    )
    db_session.add(biz)
    await db_session.commit()

    # Outbound event test
    evt = AgencyEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        correlation_id="CORR-DEMO-006",
        event_type="DEMO_REQUESTED",
        entity_type="business",
        entity_id=biz.id,
        payload={"verified_facts": ["Clinic operating in US"]}
    )
    await event_bus.publish(evt)

    latest = n8n_orchestrator._mock_sink[-1]
    assert latest["payload"]["target_workflow"] == "demo_factory"
    assert "Demo generation never implies revenue" in latest["payload"]["orchestration_context"]["commercial_warning"]

    # Inbound trigger test
    envelope = InboundN8nEnvelope(
        event_id=f"n8n_demo_{uuid.uuid4().hex[:8]}",
        event_type="TRIGGER_DEMO_BUILD",
        entity_id=str(biz.id),
        payload={"action": "TRIGGER_DEMO_BUILD", "business_id": biz.id}
    )
    res = await n8n_orchestrator.process_inbound_n8n_event(envelope, session=db_session)
    assert res["success"] is True
    assert res["status"] == "DEMO_BUILT"
    assert res["revenue_implied"] is False


@pytest.mark.asyncio
async def test_7_payment_action_alert():
    """Invariant 7: Payment action required triggers immediate CEO alert for verified review."""
    evt = AgencyEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        correlation_id="CORR-PAY-007",
        event_type="PAYMENT_REVIEW_REQUIRED",
        entity_type="payment",
        entity_id=501,
        payload={"payment_id": 501, "amount": 750.0}
    )
    await event_bus.publish(evt)

    assert len(n8n_orchestrator._mock_sink) > 0
    latest = n8n_orchestrator._mock_sink[-1]
    assert latest["payload"]["target_workflow"] == "payment_ops"
    ctx = latest["payload"]["orchestration_context"]
    assert ctx["action"] == "IMMEDIATE_CEO_PAYMENT_ALERT"
    assert ctx["amount"] == 750.0
    assert "Operator verification required" in ctx["note"]


@pytest.mark.asyncio
async def test_8_confirmed_payment_handoff():
    """Invariant 8: Confirmed payment triggers production onboarding handoff."""
    evt = AgencyEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        correlation_id="CORR-CONF-008",
        event_type="PAYMENT_CONFIRMED",
        entity_type="payment",
        entity_id=502,
        payload={"payment_id": 502, "amount": 1200.0}
    )
    await event_bus.publish(evt)

    assert len(n8n_orchestrator._mock_sink) > 0
    latest = n8n_orchestrator._mock_sink[-1]
    assert latest["payload"]["target_workflow"] == "customer_onboarding"
    ctx = latest["payload"]["orchestration_context"]
    assert ctx["action"] == "INITIATE_ONBOARDING_HANDOFF"
    assert ctx["production_unlocked"] is True


@pytest.mark.asyncio
async def test_9_duplicate_event_idempotency():
    """Invariant 9: Duplicate n8n execution IDs are safely deduplicated and ignored."""
    dup_id = f"n8n_dup_{uuid.uuid4().hex[:10]}"
    envelope = InboundN8nEnvelope(
        event_id=dup_id,
        event_type="N8N_WORKFLOW_EXECUTED",
        correlation_id="EXEC-DUP-999",
        payload={"action": "OPERATOR_NOTE_ADDED", "note": "First attempt"}
    )
    res1 = await n8n_orchestrator.process_inbound_n8n_event(envelope)
    assert res1["success"] is True
    assert res1["status"] == "NOTE_RECORDED"

    # Second attempt with same event_id and correlation_id
    res2 = await n8n_orchestrator.process_inbound_n8n_event(envelope)
    assert res2["success"] is True
    assert res2["status"] == "DEDUPLICATED"
    assert "already processed" in res2["message"]


@pytest.mark.asyncio
async def test_10_no_fake_synthetic_event_becomes_real(db_session):
    """Invariant 10: Synthetic/mock data cannot alter canonical revenue or confirmed counts."""
    truth_before = await get_canonical_production_truth(db_session)
    revenue_before = truth_before["real_verified_revenue"]

    # Inbound test event attempting to inflate revenue
    envelope = InboundN8nEnvelope(
        event_id=f"n8n_fake_{uuid.uuid4().hex[:8]}",
        event_type="SYNTHETIC_REVENUE_REPORT",
        payload={"action": "RECORD_FAKE_INCOME", "amount": 50000.0}
    )
    await n8n_orchestrator.process_inbound_n8n_event(envelope)

    truth_after = await get_canonical_production_truth(db_session)
    assert truth_after["real_verified_revenue"] == revenue_before
    assert truth_after["real_payments_confirmed"] == truth_before["real_payments_confirmed"]


@pytest.mark.asyncio
async def test_11_no_automation_bypasses_ceo_approval():
    """Invariant 11: Safety gates reject any external attempt to bypass CEO outreach approval."""
    bypass_envelope = InboundN8nEnvelope(
        event_id=f"n8n_bypass_{uuid.uuid4().hex[:8]}",
        event_type="FORCE_DISPATCH",
        payload={"action": "BYPASS_APPROVAL_AND_SEND", "message_id": 999}
    )
    res = await n8n_orchestrator.process_inbound_n8n_event(bypass_envelope)
    assert res["success"] is False
    assert res["status"] == "FORBIDDEN"
    assert "Safety violation" in res["error"]


@pytest.mark.asyncio
async def test_12_dashboard_reflects_canonical_state():
    """Invariant 12: Dashboard state returns canonical truth metrics and n8n orchestration status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/dashboard/state")
        assert res.status_code == 200
        data = res.json()

        # Canonical metrics present
        assert "metrics" in data
        metrics = data["metrics"]
        assert "real_verified_revenue" in metrics or "revenue_collected" in metrics
        assert "outreach_awaiting_approval" in metrics

        # N8N orchestration telemetry integrated
        assert "n8n_orchestration" in metrics
        n8n_tel = metrics["n8n_orchestration"]
        assert n8n_tel["status"] == "OPERATIONAL"
        assert n8n_tel["registered_templates_count"] >= 9
        assert n8n_tel["safety_invariants"]["ceo_approval_bypass_allowed"] is False
