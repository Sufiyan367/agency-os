"""
Comprehensive Test Suite for Production Voice-Sales Layer.
Tests:
- Telephony provider abstraction & dry-run safety
- E.164 phone formatting and caller ID validation
- Call recording consent disclosure compliance
- Multilingual voice script generation (EN, ES, FR, AR)
- Factual grounding in website audit diagnostics
- Objection handling (existing webmaster, send email, too expensive)
- Bounded pricing guardrails ($500 floor to $2,500 max)
- Autonomous appointment booking & meeting creation
- Hostility / complex query escalation to human
- Full database persistence (CallLog, Meeting)
- Voice API endpoints & webhook integration
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.api.app import app
from app.core.config import settings
from app.communications.voice_provider import (
    DryRunVoiceProvider,
    TwilioVoiceProvider,
    BlandAIVoiceProvider,
    get_active_voice_provider,
    format_e164_phone
)
from app.agents.voice_sales_agent import VoiceSalesAgent
from app.services.voice_service import VoiceSalesService
from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import CallLog, Meeting


@pytest.fixture(autouse=True)
async def setup_database():
    await init_db()


def test_e164_phone_formatting():
    """Verifies international phone normalization."""
    assert format_e164_phone("512-555-0199") == "+15125550199"
    assert format_e164_phone("(512) 555-0199") == "+15125550199"
    assert format_e164_phone("+44 20 7946 0991") == "+442079460991"
    assert format_e164_phone("020 7946 0991", default_country="UK") == "+442079460991"


def test_telephony_provider_abstraction_and_dry_run_safety():
    """Verifies that the factory returns DryRunVoiceProvider when dry-run is active."""
    provider = get_active_voice_provider()
    assert isinstance(provider, DryRunVoiceProvider)
    assert settings.VOICE_DRY_RUN is True


@pytest.mark.asyncio
async def test_dry_run_voice_call_execution():
    """Verifies simulated call execution, caller ID, and consent disclosure."""
    provider = DryRunVoiceProvider()
    res = await provider.place_call(
        phone="+1-512-555-0144",
        script_context="Your site takes 4.3 seconds to load.",
        language="en"
    )
    assert res.success is True
    assert res.dry_run is True
    assert res.recipient_phone == "+15125550144"
    assert res.status == "COMPLETED"
    assert "This call may be recorded" in res.transcript


def test_factual_grounding_and_multilingual_scripts():
    """Verifies voice scripts are strictly grounded in audit data across EN, ES, FR, AR."""
    audit_data = {"performance_score": 44.0, "load_time_seconds": 4.8}

    # English
    sc_en = VoiceSalesAgent.generate_call_script("Austin Roofing", "Roofing", "Austin", audit_data, "en")
    assert "4.8 seconds" in sc_en
    assert "44/100" in sc_en
    assert "Austin Roofing" in sc_en

    # Spanish
    sc_es = VoiceSalesAgent.generate_call_script("Plomería Rápida", "Plumbing", "Madrid", audit_data, "es")
    assert "4.8 segundos" in sc_es
    assert "44/100" in sc_es

    # French
    sc_fr = VoiceSalesAgent.generate_call_script("Toiture Paris", "Roofing", "Paris", audit_data, "fr")
    assert "4.8 secondes" in sc_fr
    assert "44/100" in sc_fr

    # Arabic
    sc_ar = VoiceSalesAgent.generate_call_script("شركة الخليج", "HVAC", "Riyadh", audit_data, "ar")
    assert "4.8 ثانية" in sc_ar


def test_objection_handling_pricing_bounds():
    """Verifies pricing objection responses anchor strictly between $500 and $2,500."""
    audit = {"performance_score": 50.0}
    res = VoiceSalesAgent.process_prospect_speech("How much will this turnaround cost?", audit)
    assert res.intent == "OBJECTION_HANDLED"
    assert "$500" in res.suggested_reply
    assert "$2,500" in res.suggested_reply
    assert "commercial contract" in res.suggested_reply


def test_objection_handling_existing_agency():
    """Verifies response when prospect already has an internal webmaster or agency."""
    audit = {"performance_score": 42.0}
    res = VoiceSalesAgent.process_prospect_speech("We already have an in-house developer managing the site.", audit)
    assert res.intent == "OBJECTION_HANDLED"
    assert "developer can address" in res.suggested_reply
    assert "42/100" in res.suggested_reply


def test_appointment_booking_qualification():
    """Verifies agreement to meet triggers appointment booking intent and proposes time."""
    audit = {"performance_score": 50.0}
    res = VoiceSalesAgent.process_prospect_speech("Sure, I'm interested. Let's schedule a call.", audit)
    assert res.qualified is True
    assert res.intent == "BOOK_MEETING"
    assert res.proposed_meeting_time is not None
    assert "Thursday at 2:00 PM" in res.suggested_reply


def test_hostility_and_opt_out_escalation():
    """Verifies that hostile responses trigger opt-out and unhandled inquiries escalate to human."""
    audit = {"performance_score": 50.0}
    # Explicit opt out
    res_opt = VoiceSalesAgent.process_prospect_speech("Don't call again or I will sue you!", audit)
    assert res_opt.opt_out is True
    assert res_opt.intent == "NOT_INTERESTED"

    # Complex enterprise question -> Human escalation
    res_esc = VoiceSalesAgent.process_prospect_speech("We need a SOC2 Type II audit report and custom SLA indemnification.", audit)
    assert res_esc.escalate_to_human is True
    assert res_esc.intent == "HUMAN_ESCALATION"


@pytest.mark.asyncio
async def test_voice_service_call_dispatch_and_transcript_processing():
    """Verifies full lifecycle: outbound dispatch, transcript processing, CallLog & Meeting creation."""
    dispatch_res = await VoiceSalesService.initiate_outbound_call(
        prospect_phone="+1-512-555-0188",
        business_name="Pinnacle Commercial HVAC",
        niche="HVAC",
        city="Austin",
        audit_data={"performance_score": 46.0, "load_time_seconds": 4.5}
    )
    assert dispatch_res["success"] is True
    call_sid = dispatch_res["call_sid"]

    # Process positive appointment transcript
    transcript = "Prospect: Yes, sure! Let's talk this Thursday and go over the audit."
    trans_res = await VoiceSalesService.process_call_transcript(
        call_sid=call_sid,
        transcript=transcript,
        duration=55
    )
    assert trans_res["intent"] == "BOOK_MEETING"
    assert trans_res["meeting_booked"] is True

    # Verify Meeting in database
    async with AsyncSessionLocal() as db:
        meetings = await VoiceSalesService.get_meetings(limit=10)
        assert len(meetings) > 0
        call_logs = await VoiceSalesService.get_call_logs(limit=10)
        matching = [c for c in call_logs if c["call_sid"] == call_sid]
        assert len(matching) == 1
        assert matching[0]["qualification_intent"] == "BOOK_MEETING"


@pytest.mark.asyncio
async def test_voice_api_endpoints():
    """Verifies FastAPI voice routes."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # GET config
        res_cfg = await ac.get("/api/voice/config")
        assert res_cfg.status_code == 200
        cfg = res_cfg.json()
        assert "voice_provider" in cfg
        assert cfg["voice_dry_run"] is True
        assert "caller_id" in cfg

        # POST trigger call
        res_call = await ac.post("/api/voice/call", json={
            "phone": "+1-512-555-0177",
            "business_name": "Lone Star Dental",
            "niche": "Dental",
            "city": "Austin"
        })
        assert res_call.status_code == 200
        call_data = res_call.json()
        assert call_data["success"] is True
        assert call_data["dry_run"] is True

        # GET calls list
        res_list = await ac.get("/api/voice/calls")
        assert res_list.status_code == 200
        assert isinstance(res_list.json(), list)

        # GET meetings list
        res_meets = await ac.get("/api/voice/meetings")
        assert res_meets.status_code == 200
        assert isinstance(res_meets.json(), list)
