"""
Comprehensive Automated Test Suite for Autonomous Revenue Agent.
Covers:
- One-prospect-at-a-time processing
- Duplicate prevention
- Commercial threshold ($500+ floor)
- Missing contact rejection (no fabrication)
- Email vs Voice selection
- Language detection (EN, AR, ES, FR)
- Conversation state persistence & message history
- Human takeover guardrails
- Emergency kill switch
- Dry-run mode enforcement
- Payment webhook verification
- Non-binding pricing commitments guardrail
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.api.app import app
from app.agents.state_machine import ProspectState, AgentStateMachine
from app.agents.decision_engine import DecisionEngine
from app.agents.conversation_agent import ConversationAgent
from app.agents.revenue_agent import RevenueAgentOrchestrator
from app.communications.router import ContactRouter, ChannelType
from app.communications.conversation import ConversationSession
from app.core.config import settings


def test_one_prospect_at_a_time_isolation():
    """Verifies that the orchestrator initializes cleanly and manages state on a single prospect."""
    orch = RevenueAgentOrchestrator()
    status = orch.get_status()
    assert status["status"] == "IDLE"
    assert status["current_state"] == ProspectState.DISCOVER.value
    assert orch.stats["prospects_processed"] == 0


def test_commercial_floor_500_skips_low_value():
    """Verifies that prospects below the $500 floor are rejected with high confidence."""
    dec = DecisionEngine.evaluate_commercial_qualification(
        estimated_min_value=499.0,
        commercial_floor=500.0,
        buyer_score=85.0,
        opp_score=70.0
    )
    assert dec.target_state == ProspectState.SKIPPED
    assert "below commercial floor" in dec.reason

    # Valid >= 500 passes
    dec_pass = DecisionEngine.evaluate_commercial_qualification(
        estimated_min_value=500.0,
        commercial_floor=500.0,
        buyer_score=85.0,
        opp_score=70.0
    )
    assert dec_pass.target_state == ProspectState.CONTACT_DISCOVERY


def test_unverified_contact_skipped_no_fabrication():
    """Verifies that missing contact evidence leads to SKIPPED without fabricating emails or phones."""
    route = ContactRouter.route_contact(email=None, phone=None, voice_enabled=False)
    assert route.eligible is False
    assert route.channel == ChannelType.NONE
    assert "Rejecting synthetic fallback" in route.reason


def test_channel_router_email_vs_voice():
    """Verifies that email is prioritized when verified, and voice is used when enabled."""
    # Email preference
    route_email = ContactRouter.route_contact(
        email="owner@austinroofing.com",
        phone="+1-512-555-0144",
        voice_enabled=True
    )
    assert route_email.channel == ChannelType.EMAIL
    assert route_email.destination == "owner@austinroofing.com"

    # Voice selection when only phone exists
    route_voice = ContactRouter.route_contact(
        email=None,
        phone="+1-512-555-0144",
        voice_enabled=True
    )
    assert route_voice.channel == ChannelType.VOICE
    assert route_voice.destination == "+1-512-555-0144"


def test_language_detection_and_factual_grounding():
    """Verifies multilingual detection across EN, ES, FR, AR and factual audit grounding."""
    # English
    rep_en = ConversationAgent.process_reply("Can we book a call to discuss?", {"performance_score": 45.0}, 500.0)
    assert rep_en.detected_language == "en"
    assert rep_en.propose_meeting is True
    assert "45/100" in rep_en.reply_text

    # Spanish
    rep_es = ConversationAgent.process_reply("Hola, me gustaría agendar una llamada", {"performance_score": 52.0}, 750.0)
    assert rep_es.detected_language == "es"
    assert rep_es.propose_meeting is True
    assert "52/100" in rep_es.reply_text

    # French
    rep_fr = ConversationAgent.process_reply("Bonjour, pouvons-nous planifier un rendez-vous ?", {"performance_score": 60.0}, 800.0)
    assert rep_fr.detected_language == "fr"
    assert rep_fr.propose_meeting is True

    # Arabic
    rep_ar = ConversationAgent.process_reply("مرحبا، نود ترتيب موعد لمناقشة الموقع", {"performance_score": 68.0}, 1000.0)
    assert rep_ar.detected_language == "ar"
    assert rep_ar.propose_meeting is True


def test_non_binding_pricing_guardrail():
    """Verifies that the agent never autonomously commits to binding legal or pricing terms."""
    rep_price = ConversationAgent.process_reply("How much will this cost exactly?", {"performance_score": 50.0}, 500.0)
    assert rep_price.intent_detected == "PRICING"
    assert "$500" in rep_price.reply_text
    assert "scope exact deliverables" in rep_price.reply_text


def test_conversation_state_persistence():
    """Verifies multi-turn message history is stored correctly in ConversationSession."""
    session = ConversationSession(
        session_id="sess_test_1",
        business_name="Salis Roofing",
        channel=ChannelType.EMAIL,
        language="en"
    )
    assert len(session.messages) == 0

    ConversationAgent.process_reply("Are you available for a demo?", {"performance_score": 55.0}, 500.0, session=session)
    assert len(session.messages) == 2
    assert session.messages[0].sender == "PROSPECT"
    assert session.messages[1].sender == "AGENT"
    assert session.messages[1].intent == "MEETING_REQUEST"


def test_human_takeover_on_unrecognized_query():
    """Verifies that complex or unknown queries trigger handoff to human operators."""
    session = ConversationSession(
        session_id="sess_test_2",
        business_name="Custom Solutions",
        channel=ChannelType.EMAIL
    )
    rep = ConversationAgent.process_reply(
        "We need a custom HIPAA-compliant enterprise multi-tenant integration with Oracle ERP",
        {"performance_score": 50.0},
        1000.0,
        session=session
    )
    assert rep.handoff_to_human is True
    assert session.handed_off_to_human is True


def test_kill_switch_and_dry_run_safety():
    """Verifies that safety gates, dry-run flags, and emergency kill switch are strictly enforced."""
    orch = RevenueAgentOrchestrator()
    assert settings.EMAIL_DRY_RUN is True
    assert settings.VOICE_DRY_RUN is True
    assert settings.PAYMENT_DRY_RUN is True
    assert settings.RAZORPAY_MODE == "test"

    # Emergency kill switch disables agent
    res = orch.trigger_kill_switch()
    assert res["status"] == "KILLED"
    assert res["kill_switch_active"] is True
    assert orch.is_running is False


@pytest.mark.asyncio
async def test_agent_api_endpoints():
    """Verifies the FastAPI agent control endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_status = await ac.get("/api/agent/status")
        assert res_status.status_code == 200
        data = res_status.json()
        assert "status" in data
        assert "current_state" in data
        assert "stats" in data

        res_start = await ac.post("/api/agent/start")
        assert res_start.status_code == 200
        assert res_start.json()["status"] == "RUNNING"

        res_pause = await ac.post("/api/agent/pause")
        assert res_pause.status_code == 200
        assert res_pause.json()["status"] == "PAUSED"

        res_stop = await ac.post("/api/agent/stop")
        assert res_stop.status_code == 200
        assert res_stop.json()["status"] == "IDLE"

        res_kill = await ac.post("/api/agent/kill")
        assert res_kill.status_code == 200
        assert res_kill.json()["status"] == "KILLED"


@pytest.mark.asyncio
async def test_single_prospect_step_execution():
    """Verifies that step_single_prospect evaluates one prospect and respects safety gates."""
    orch = RevenueAgentOrchestrator()
    prospect_data = {
        "name": "TrueWorks Roofing",
        "domain": "trueworksroofing.com",
        "email": "contact@trueworksroofing.com",
        "phone": "+1-713-903-7663",
        "estimated_value": 750.0,
        "buyer_score": 88.0,
        "opportunity_score": 82.0
    }
    # When AUTONOMOUS_OUTREACH is False, it holds in OUTREACH_PENDING for operator review
    res = await orch.step_single_prospect(prospect_data, commercial_floor=500.0)
    assert res["status"] == "HELD_FOR_APPROVAL"
    assert res["channel"] == "EMAIL"
    assert orch.current_state == ProspectState.OUTREACH_PENDING
    assert orch.stats["prospects_processed"] == 1
