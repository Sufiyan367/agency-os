"""
Phase 17 Comprehensive Test Suite: Autonomous Voice / Call Operations Layer.
Tests:
- Voice provider abstraction operations (create, terminate, events, transcript, completion, metadata)
- Deterministic 15-state conversation state machine
- Transcript processing & factual objection handling
- Commercial negotiation ($500 floor, review, and auto-approval)
- Human escalation triggers (legal, privacy, hostility, explicit human)
- Suppression & duplicate call prevention
- Payment handoff without premature deal closing (WON remains guarded)
- Factual claims & transparent AI identity disclosure
- Secret and credential redaction from speech transcripts
- Call interruption, hydration, and resumption
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import Business, CallLog, Meeting, Payment, SuppressionList, PipelineStage
from app.core.config import settings
from app.communications.voice_provider import (
    DryRunVoiceProvider,
    MockVoiceProvider,
    get_active_voice_provider,
    format_e164_phone
)
from app.communications.voice_state_machine import VoiceCallState, VoiceCallSession
from app.communications.voice_escalation import voice_escalation_engine, VoiceEscalationReason
from app.agents.voice_sales_agent import VoiceSalesAgent
from app.services.voice_service import voice_sales_service, VoiceSalesService
from app.outreach.compliance import compliance_guard


@pytest.fixture(autouse=True)
def restore_settings():
    orig_state = {k: getattr(settings, k) for k in type(settings).model_fields.keys()}
    yield
    for k, v in orig_state.items():
        try:
            setattr(settings, k, v)
        except Exception:
            pass


@pytest_asyncio.fixture
async def db_session():
    await init_db()
    async with AsyncSessionLocal() as session:
        yield session


import random

@pytest_asyncio.fixture
async def sample_business(db_session: AsyncSession):
    uid = uuid.uuid4().hex[:6]
    rand_digits = random.randint(1000, 9999)
    biz = Business(
        name=f"Apex Commercial Roofing {uid}",
        domain=f"apexroofing-{uid}.co.uk",
        phone=f"+4420794{rand_digits}",
        country="GB",
        city="London",
        niche="Commercial Roofing",
        pipeline_stage=PipelineStage.CONTACTED.value,
        prospect_score=85.0
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)
    return biz


# ==============================================================
# 1. VOICE PROVIDER ABSTRACTION TESTS
# ==============================================================

@pytest.mark.asyncio
async def test_voice_provider_abstraction_operations():
    provider = MockVoiceProvider()

    # 1. create_call
    res = await provider.create_call(
        phone="+1-512-555-0188",
        script_context="Your mobile website loads in 4.3 seconds.",
        language="en"
    )
    assert res.success is True
    assert res.call_id.startswith("CA_dry_")
    assert res.status == "COMPLETED"

    # 2. retrieve_call_metadata
    meta = await provider.retrieve_call_metadata(res.call_id)
    assert meta["call_id"] == res.call_id
    assert meta["status"] == "COMPLETED"

    # 3. terminate_call
    term = await provider.terminate_call(res.call_id)
    assert term["terminated"] is True
    assert term["status"] == "TERMINATED"

    # 4. receive_call_event
    ev = await provider.receive_call_event({"event": "ringing", "call_id": res.call_id})
    assert ev["processed"] is True

    # 5. receive_transcript
    tr = await provider.receive_transcript(res.call_id, {"text": "Yes, we are interested in speed fixes."})
    assert tr["processed"] is True

    # 6. receive_call_completion
    comp = await provider.receive_call_completion(res.call_id, {"duration": 45, "status": "completed"})
    assert comp["status"] == "COMPLETED"


# ==============================================================
# 2. CONVERSATION STATE MACHINE TESTS
# ==============================================================

def test_state_machine_valid_progression():
    session = VoiceCallSession(call_sid="CA_test_sm_1", recipient_phone="+15125550100")
    assert session.current_state == VoiceCallState.CALL_INITIATED

    # Step through valid sequence
    session.transition_to(VoiceCallState.DISCOVERY, reason="Intro complete")
    session.transition_to(VoiceCallState.PAIN_QUALIFICATION, reason="Discussed mobile speed")
    session.transition_to(VoiceCallState.SERVICE_EXPLANATION, reason="Explained turnaround")
    session.transition_to(VoiceCallState.QUESTIONS, reason="Prospect asked details")
    session.transition_to(VoiceCallState.OBJECTION_HANDLING, reason="Addressed webmaster concerns")
    session.transition_to(VoiceCallState.PRICE_DISCUSSION, reason="Prospect asked pricing")
    session.transition_to(VoiceCallState.NEGOTIATION, reason="Offered counter proposal")
    session.transition_to(VoiceCallState.PROPOSAL_READY, reason="Terms accepted")
    session.transition_to(VoiceCallState.PAYMENT_REQUESTED, reason="Checkout dispatched")
    session.transition_to(VoiceCallState.CALL_COMPLETED, reason="Session concluded")

    assert session.current_state == VoiceCallState.CALL_COMPLETED
    assert len(session.history) == 10


def test_state_machine_illegal_transition_raises():
    session = VoiceCallSession(call_sid="CA_test_sm_2", recipient_phone="+15125550100")
    assert session.current_state == VoiceCallState.CALL_INITIATED

    # Jumping directly from INITIATED to PAYMENT_REQUESTED is illegal
    with pytest.raises(ValueError, match="Illegal voice state transition"):
        session.transition_to(VoiceCallState.PAYMENT_REQUESTED, reason="Premature jump")


# ==============================================================
# 3. SALES BEHAVIOR & FACTUAL GROUNDING TESTS
# ==============================================================

def test_script_generation_grounded_in_audit():
    audit = {"performance_score": 42.0, "load_time_seconds": 5.4}
    script = VoiceSalesAgent.generate_call_script(
        business_name="Precision Metalworks",
        niche="Manufacturing",
        city="Detroit",
        audit_evidence=audit,
        language="en"
    )
    assert "5.4 seconds" in script
    assert "42/100" in script
    assert "Precision Metalworks" in script
    # Verify no fabricated guarantee claims
    assert "guarantee" not in script.lower()
    assert "100%" not in script.lower()


def test_ai_identity_transparency_disclosure():
    audit = {"performance_score": 50.0}
    res = VoiceSalesAgent.process_prospect_speech("Wait, are you an AI bot?", audit)
    assert res.intent == "AI_IDENTITY_DISCLOSED"
    assert "automated technical assistant" in res.suggested_reply.lower()
    assert "agency growth" in res.suggested_reply.lower()


# ==============================================================
# 4. OBJECTION HANDLING & NEGOTIATION TESTS
# ==============================================================

def test_routine_objection_handled_without_escalation():
    audit = {"performance_score": 50.0}
    res = VoiceSalesAgent.process_prospect_speech("We already have an in-house web guy who handles this.", audit)
    assert res.intent == "OBJECTION_HANDLED"
    assert res.escalate_to_human is False
    assert "developer" in res.suggested_reply.lower()


def test_negotiation_floor_rejection():
    audit = {"performance_score": 50.0}
    # Offer $350 (below $500 floor)
    res = VoiceSalesAgent.process_prospect_speech("Can you do this for $350?", audit)
    assert res.intent == "NEGOTIATION"
    assert res.offered_price == 350.0
    assert "$500" in res.suggested_reply
    assert "strict engineering minimum" in res.suggested_reply


def test_negotiation_human_review_range():
    audit = {"performance_score": 50.0}
    # Offer $750 (between $500 and $999)
    res = VoiceSalesAgent.process_prospect_speech("I have a budget of $750 for this.", audit)
    assert res.intent == "NEGOTIATION"
    assert res.offered_price == 750.0
    assert res.escalate_to_human is True
    assert res.escalation_reason == "PRICING_BELOW_TARGET_REQUIRES_REVIEW"


def test_negotiation_auto_approval_range():
    audit = {"performance_score": 50.0}
    # Offer $1200 (>= $1000)
    res = VoiceSalesAgent.process_prospect_speech("Can we do the full package for $1200?", audit)
    assert res.intent == "PROPOSAL_READY"
    assert res.agreed_price == 1200.0
    assert res.escalate_to_human is False
    assert "$1,200" in res.suggested_reply or "$1200" in res.suggested_reply


# ==============================================================
# 5. HUMAN ESCALATION ENGINE TESTS
# ==============================================================

def test_escalation_on_legal_threat():
    res = voice_escalation_engine.evaluate("I'm going to talk to my lawyer and sue you in court.")
    assert res.should_escalate is True
    assert res.reason == VoiceEscalationReason.LEGAL_THREAT


def test_escalation_on_privacy_request():
    res = voice_escalation_engine.evaluate("Under GDPR, where did you get my number? Delete my data immediately.")
    assert res.should_escalate is True
    assert res.reason == VoiceEscalationReason.PRIVACY_REQUEST


def test_escalation_on_explicit_human_request():
    res = voice_escalation_engine.evaluate("I don't want to talk to an automated system, transfer me to a real person please.")
    assert res.should_escalate is True
    assert res.reason == VoiceEscalationReason.EXPLICIT_HUMAN_REQUEST


def test_escalation_on_payment_dispute():
    res = voice_escalation_engine.evaluate("This sounds like a scam, you stole money from my colleague!")
    assert res.should_escalate is True
    assert res.reason == VoiceEscalationReason.PAYMENT_DISPUTE


# ==============================================================
# 6. SUPPRESSION & DUPLICATE CALL PREVENTION TESTS
# ==============================================================

@pytest.mark.asyncio
async def test_opt_out_suppresses_phone(db_session: AsyncSession, sample_business: Business):
    phone = sample_business.phone
    sid = f"CA_optout_{uuid.uuid4().hex[:8]}"

    # Process an opt-out utterance
    call_log = CallLog(
        business_id=sample_business.id,
        call_sid=sid,
        caller_id="+15125550100",
        recipient_phone=phone,
        status="IN_PROGRESS",
        call_state=VoiceCallState.DISCOVERY.value
    )
    db_session.add(call_log)
    await db_session.commit()

    res = await voice_sales_service.process_call_transcript(
        call_sid=sid,
        transcript="Please stop calling this number and take me off your list.",
        db=db_session
    )
    assert res["call_state"] == VoiceCallState.DO_NOT_CONTACT.value

    # Verify phone is now in SuppressionList
    is_supp = await compliance_guard.is_suppressed(db_session, phone=phone)
    assert is_supp is True

    # Calling again is immediately blocked
    call_attempt = await voice_sales_service.initiate_outbound_call(
        prospect_phone=phone,
        business_name=sample_business.name,
        business_id=sample_business.id,
        db=db_session
    )
    assert call_attempt["success"] is False
    assert call_attempt["status"] == "SUPPRESSED"


@pytest.mark.asyncio
async def test_duplicate_active_call_blocked(db_session: AsyncSession):
    phone = f"+1512555{random.randint(1000, 9999)}"
    sid = f"CA_active_dup_{uuid.uuid4().hex[:8]}"

    # Add in-progress call
    call_log = CallLog(
        call_sid=sid,
        caller_id="+15125550100",
        recipient_phone=phone,
        status="IN_PROGRESS",
        call_state=VoiceCallState.DISCOVERY.value
    )
    db_session.add(call_log)
    await db_session.commit()

    # Second call to same phone should be blocked
    attempt = await voice_sales_service.initiate_outbound_call(
        prospect_phone=phone,
        business_name="Test Business",
        db=db_session
    )
    assert attempt["success"] is False
    assert attempt["status"] == "DUPLICATE_CALL_BLOCKED"


# ==============================================================
# 7. PAYMENT HANDOFF & NO PREMATURE WON TESTS
# ==============================================================

@pytest.mark.asyncio
async def test_payment_handoff_without_premature_won(db_session: AsyncSession, sample_business: Business):
    sid = f"CA_pay_handoff_{uuid.uuid4().hex[:8]}"
    call_log = CallLog(
        business_id=sample_business.id,
        call_sid=sid,
        caller_id="+15125550100",
        recipient_phone=sample_business.phone,
        status="IN_PROGRESS",
        call_state=VoiceCallState.DISCOVERY.value
    )
    db_session.add(call_log)
    await db_session.commit()

    # Prospect agrees to terms
    res = await voice_sales_service.process_call_transcript(
        call_sid=sid,
        transcript="Sounds great, I agree to the price. Send me the invoice and payment link.",
        db=db_session
    )

    assert res["call_state"] == VoiceCallState.PAYMENT_REQUESTED.value
    assert res["payment_requested"] is True

    # Verify a Payment record was created with status PAYMENT_PENDING
    q_pay = select(Payment).where(Payment.business_id == sample_business.id)
    payment = (await db_session.execute(q_pay)).scalars().first()
    assert payment is not None
    assert payment.status == "PAYMENT_PENDING"
    assert payment.amount >= 500.0

    # CRITICAL INVARIANT: Business must NOT be marked WON prematurely!
    await db_session.refresh(sample_business)
    assert sample_business.pipeline_stage != PipelineStage.WON.value
    assert sample_business.pipeline_stage == PipelineStage.PROPOSAL.value


# ==============================================================
# 8. SECRET REDACTION TESTS
# ==============================================================

def test_secret_redaction_in_transcripts():
    raw = "My API key is re_1234567890abcdef12345678 and credit card is 4111 2222 3333 4444 with password: SecretPassword123"
    redacted = VoiceSalesAgent.redact_sensitive_content(raw)
    assert "re_1234567890abcdef12345678" not in redacted
    assert "4111 2222 3333 4444" not in redacted
    assert "SecretPassword123" not in redacted
    assert "[REDACTED_API_KEY]" in redacted
    assert "[REDACTED_CARD_NUMBER]" in redacted


# ==============================================================
# 9. CALL RESUMPTION & HYDRATION TESTS
# ==============================================================

@pytest.mark.asyncio
async def test_call_interruption_and_recovery(db_session: AsyncSession, sample_business: Business):
    sid = f"CA_resume_{uuid.uuid4().hex[:8]}"
    call_log = CallLog(
        business_id=sample_business.id,
        call_sid=sid,
        caller_id="+15125550100",
        recipient_phone=sample_business.phone,
        status="IN_PROGRESS",
        call_state=VoiceCallState.DISCOVERY.value
    )
    db_session.add(call_log)
    await db_session.commit()

    # Turn 1: Discuss service
    turn1 = await voice_sales_service.resume_call_session(
        call_sid=sid,
        new_utterance="What services do you provide?",
        db=db_session
    )
    assert turn1["call_state"] == VoiceCallState.SERVICE_EXPLANATION.value

    # Turn 2: Discuss pricing
    turn2 = await voice_sales_service.resume_call_session(
        call_sid=sid,
        new_utterance="How much does this speed turnaround cost?",
        db=db_session
    )
    assert turn2["call_state"] == VoiceCallState.PRICE_DISCUSSION.value

    # Turn 3: Book meeting
    turn3 = await voice_sales_service.resume_call_session(
        call_sid=sid,
        new_utterance="Sure, let's schedule a walkthrough for Thursday.",
        db=db_session
    )
    assert turn3["call_state"] == VoiceCallState.CALL_COMPLETED.value
    assert turn3["meeting_booked"] is True
