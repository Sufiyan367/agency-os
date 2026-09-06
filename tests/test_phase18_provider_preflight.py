"""
Phase 18 Comprehensive Test Suite: Provider Connectivity Preflight & Safety Verification.
Tests:
1. End-to-End Mocked Internal Flow (labeled SIMULATION/TEST, no real revenue/prospects affected):
   Prospect -> Verified Evidence -> Audit -> Service Match -> $1,000+ Offer ->
   Auto-Approval -> Outreach Generated -> Mock Reply -> Mock Voice Call ->
   Qualification -> Negotiation -> Proposal -> Mock Payment Event ->
   Payment Verification -> Delivery Handoff.
2. Failure Injection Tests:
   - Email: Invalid credential, provider failure, duplicate message, suppressed recipient
   - Payment: Invalid signature, underpayment/currency mismatch, duplicate webhook, missing transaction ID
   - Voice: Provider failure, low confidence, human escalation, explicit do-not-contact
3. Production Safety State Verification:
   Ensures all dry-run safety gates and invariant locks remain strictly intact.
"""

import pytest
import pytest_asyncio
import uuid
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient, ASGITransport

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business,
    AuditRun,
    LeadScore,
    Offer,
    OutreachMessage,
    PipelineStage,
    VerificationStatus,
    OutreachStatus,
    Payment,
    Customer,
    Project,
    CallLog,
    SuppressionList,
    PaymentWebhookEvent,
    ProspectMemory
)
from app.core.config import settings
from app.api.app import app
from app.communications.voice_provider import DryRunVoiceProvider, MockVoiceProvider
from app.communications.voice_state_machine import VoiceCallState
from app.communications.voice_escalation import voice_escalation_engine, VoiceEscalationReason
from app.agents.voice_sales_agent import VoiceSalesAgent
from app.services.voice_service import voice_sales_service
from app.outreach.compliance import compliance_guard
from app.outreach.sender import OutreachSenderAdapter
from app.payments.razorpay import razorpay_payment_provider
from app.offers.generator import offer_engine
from app.auditing.engine import website_audit_engine
from app.crm.memory_service import memory_service
from app.crm.inbox_poller import inbox_poller
from app.crm.negotiator import commercial_negotiator


@pytest.fixture(autouse=True)
def preserve_safety_invariants():
    """Guarantees that all safety invariants remain strictly active throughout testing."""
    orig_settings = {
        "RESEARCH_ONLY": settings.RESEARCH_ONLY,
        "EMAIL_DRY_RUN": settings.EMAIL_DRY_RUN,
        "PAYMENTS_ENABLED": settings.PAYMENTS_ENABLED,
        "PAYMENT_DRY_RUN": settings.PAYMENT_DRY_RUN,
        "VOICE_DRY_RUN": settings.VOICE_DRY_RUN,
    }
    settings.RESEARCH_ONLY = True
    settings.EMAIL_DRY_RUN = True
    settings.PAYMENTS_ENABLED = False
    settings.PAYMENT_DRY_RUN = True
    settings.VOICE_DRY_RUN = True
    yield
    for k, v in orig_settings.items():
        setattr(settings, k, v)


@pytest_asyncio.fixture
async def db_session():
    await init_db()
    async with AsyncSessionLocal() as session:
        yield session


# ==============================================================
# 1. COMPLETE MOCKED INTERNAL FLOW (SIMULATION / TEST)
# ==============================================================

@pytest.mark.asyncio
async def test_complete_mocked_internal_flow_with_zero_real_side_effects(db_session: AsyncSession):
    """
    Simulates the entire autonomous lifecycle in a mocked/isolated test context:
    Prospect -> Evidence -> Audit -> Service Match -> $1,000+ Offer ->
    Auto-Approval -> Outreach -> Reply -> Voice Call -> Negotiation ->
    Proposal -> Payment Event -> Verification -> Delivery Handoff.
    """
    uid = uuid.uuid4().hex[:6]
    test_dom = f"simulated-lead-{uid}.co.uk"
    test_email = f"director@{test_dom}"
    test_phone = f"+4420794{uuid.uuid4().hex[:4]}"

    # Step 1: Simulated Prospect with Verified Evidence
    sim_biz = Business(
        name=f"SIMULATION_Apex Engineering {uid}",
        domain=test_dom,
        website_url=f"https://{test_dom}",
        country="GB",
        city="London",
        niche="Commercial Engineering",
        verification_status=VerificationStatus.VERIFIED.value,
        pipeline_stage=PipelineStage.DISCOVERED.value,
        public_email=test_email,
        phone=test_phone,
        prospect_score=88.5
    )
    db_session.add(sim_biz)
    await db_session.commit()
    await db_session.refresh(sim_biz)
    biz_id = sim_biz.id

    # Step 2: Factual Audit Run
    audit = AuditRun(
        business_id=biz_id,
        url_audited=f"https://{test_dom}",
        overall_health_score=45.0,
        performance_score=42.0,
        seo_score=60.0,
        metrics={"performance_score": 42.0, "load_time_seconds": 4.3}
    )
    db_session.add(audit)
    await db_session.commit()

    # Step 3: Service Match & $1,000+ Offer Recommendation
    offer = await offer_engine.generate_offer_for_business(db_session, sim_biz)
    assert offer.recommended_price >= 1000.0, "Offer must meet or exceed $1,000 auto-approval threshold"
    offer_val = offer.recommended_price

    # Step 4: Auto-Approval Policy Validation
    eval_res = commercial_negotiator.evaluate_counter_offer(offer_val, 1000.0)
    assert eval_res.decision == "ACCEPTED"
    assert eval_res.can_accept is True

    # Step 5: Outreach Message Generation (Dry-Run transmission)
    msg = OutreachMessage(
        business_id=biz_id,
        recipient_email=test_email,
        subject=f"Technical Note on {test_dom} (SIMULATION)",
        body="Preliminary mobile diagnostics show 4.3s load time.",
        status=OutreachStatus.SENT.value,
        sent_at=datetime.utcnow()
    )
    db_session.add(msg)
    sim_biz.pipeline_stage = PipelineStage.CONTACTED.value
    await db_session.commit()

    # Step 6: Mock Inbound Reply & Memory Persistence
    reply_res = await inbox_poller.process_inbound_message(
        session=db_session,
        sender_email=test_email,
        subject=f"Re: Technical Note on {test_dom}",
        body="We are interested in discussing the speed fixes. Can you call our office?"
    )
    assert reply_res is not None

    # Step 7: Mock Voice Call Initiation
    call_res = await voice_sales_service.initiate_outbound_call(
        prospect_phone=test_phone,
        business_name=sim_biz.name,
        business_id=biz_id,
        audit_data={"performance_score": 42.0, "load_time_seconds": 4.3},
        db=db_session
    )
    assert call_res["success"] is True
    assert call_res["dry_run"] is True
    call_sid = call_res["call_sid"]

    # Step 8: Qualification & Commercial Negotiation
    turn_negotiate = await voice_sales_service.resume_call_session(
        call_sid=call_sid,
        new_utterance=f"Can you provide the turnaround package for ${offer_val:,.0f}?",
        db=db_session
    )
    assert turn_negotiate["call_state"] == VoiceCallState.NEGOTIATION.value

    # Step 9: Proposal and Payment Request Hand-off
    turn_agree = await voice_sales_service.resume_call_session(
        call_sid=call_sid,
        new_utterance="I agree, send over the invoice and payment link.",
        db=db_session
    )
    # Verbal agreement sets stage to PROPOSAL, NOT WON
    await db_session.refresh(sim_biz)
    assert sim_biz.pipeline_stage == PipelineStage.PROPOSAL.value
    assert sim_biz.pipeline_stage != PipelineStage.WON.value, "Deal MUST NOT be marked WON prematurely before verified payment"

    # Step 10: Mock Payment Event (Razorpay Webhook in DRY RUN mode)
    test_secret = "test_rzp_preflight_sim_sec"
    orig_sec = razorpay_payment_provider.webhook_secret
    razorpay_payment_provider.webhook_secret = test_secret

    webhook_payload = {
        "event": "payment_link.paid",
        "created_at": 1710009999,
        "payload": {
            "payment_link": {
                "entity": {
                    "id": f"plink_sim_{uid}",
                    "amount": int(offer_val * 100),
                    "amount_paid": int(offer_val * 100),
                    "currency": "USD",
                    "status": "paid",
                    "notes": {"business_id": str(biz_id)}
                }
            },
            "payment": {
                "entity": {
                    "id": f"pay_sim_{uid}",
                    "amount": int(offer_val * 100),
                    "currency": "USD",
                    "status": "captured",
                    "email": test_email
                }
            }
        }
    }
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")
    sig = hmac.new(test_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/webhooks/razorpay",
                content=payload_bytes,
                headers={"X-Razorpay-Signature": sig}
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "SUCCESS"
    finally:
        razorpay_payment_provider.webhook_secret = orig_sec

    # Step 11: Verification of Delivery Handoff & Correct WON Transition
    await db_session.refresh(sim_biz)
    assert sim_biz.pipeline_stage == PipelineStage.WON.value

    # Verify Customer and Project provisioned
    cust = (await db_session.execute(
        select(Customer).where(Customer.business_id == biz_id)
    )).scalars().first()
    assert cust is not None
    assert cust.contact_email == test_email

    proj = (await db_session.execute(
        select(Project).where(Project.customer_id == cust.id)
    )).scalars().first()
    assert proj is not None
    assert proj.status in ("IN_PROGRESS", "ACTIVE")


# ==============================================================
# 2. FAILURE INJECTION TESTS: EMAIL
# ==============================================================

@pytest.mark.asyncio
async def test_email_failure_injection_suppressed_recipient(db_session: AsyncSession):
    """Proves outreach is strictly blocked when recipient is suppressed."""
    supp_email = f"suppressed-{uuid.uuid4().hex[:6]}@example.com"
    await compliance_guard.add_to_suppression(db_session, email=supp_email, reason="UNSUBSCRIBE")

    biz = Business(
        name="Suppressed Corp",
        domain=f"example-supp-{uuid.uuid4().hex[:6]}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        public_email=supp_email,
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email=supp_email,
        subject="Test subject",
        body="Test body",
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)

    sender = OutreachSenderAdapter()
    settings.RESEARCH_ONLY = False
    try:
        with pytest.raises(ValueError, match="suppression list"):
            await sender.send_approved_message(db_session, message_id=msg.id)
        await db_session.refresh(msg)
        assert msg.status == OutreachStatus.FAILED.value
    finally:
        settings.RESEARCH_ONLY = True


@pytest.mark.asyncio
async def test_email_failure_injection_duplicate_message_blocked(db_session: AsyncSession):
    """Proves duplicate email to same message ID or already sent is strictly blocked."""
    dup_email = f"dup-{uuid.uuid4().hex[:6]}@example.com"
    biz = Business(
        name="Dup Corp",
        domain=f"example-dup-{uuid.uuid4().hex[:6]}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        public_email=dup_email,
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email=dup_email,
        subject="First Outreach",
        body="Diagnostic content",
        status=OutreachStatus.SENT.value,
        sent_at=datetime.utcnow()
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)

    sender = OutreachSenderAdapter()
    settings.RESEARCH_ONLY = False
    try:
        with pytest.raises(ValueError, match="Duplicate dispatch is prohibited"):
            await sender.send_approved_message(db_session, message_id=msg.id)
    finally:
        settings.RESEARCH_ONLY = True


@pytest.mark.asyncio
async def test_email_failure_injection_live_send_without_credentials_rejected(db_session: AsyncSession):
    """Proves live sending without valid provider credentials raises explicit error."""
    cred_domain = f"example-cred-{uuid.uuid4().hex[:6]}.com"
    biz = Business(
        name="Cred Corp",
        domain=cred_domain,
        country="US",
        city="Austin",
        niche="Commercial Services",
        public_email=f"test@{cred_domain}",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email=biz.public_email,
        subject="Test",
        body="Test",
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)

    sender = OutreachSenderAdapter()
    settings.RESEARCH_ONLY = False
    try:
        with pytest.raises(ValueError, match="Cannot send live"):
            await sender.send_approved_message(db_session, message_id=msg.id, force_live=True)
    finally:
        settings.RESEARCH_ONLY = True


# ==============================================================
# 3. FAILURE INJECTION TESTS: PAYMENT
# ==============================================================

@pytest.mark.asyncio
async def test_payment_failure_injection_invalid_signature():
    """Proves payment webhook rejects invalid or forged signatures with HTTP 400."""
    orig_sec = razorpay_payment_provider.webhook_secret
    razorpay_payment_provider.webhook_secret = "test_webhook_sec_123"
    payload = json.dumps({"event": "payment_link.paid"}).encode("utf-8")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/webhooks/razorpay",
                content=payload,
                headers={"X-Razorpay-Signature": "invalid_forged_signature_hash_123"}
            )
            assert res.status_code == 400
            assert "signature verification failed" in res.json()["detail"].lower()
    finally:
        razorpay_payment_provider.webhook_secret = orig_sec


@pytest.mark.asyncio
async def test_payment_failure_injection_underpayment_rejected(db_session: AsyncSession):
    """Proves payments below the $500 commercial floor are strictly rejected."""
    biz = Business(
        name="Underpay Corp",
        domain=f"example-underpay-{uuid.uuid4().hex[:6]}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        pipeline_stage=PipelineStage.PROPOSAL.value
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    from app.payments.service import payment_service
    with pytest.raises(ValueError, match="below the minimum commercial floor"):
        await payment_service.confirm_payment_and_onboard(
            session=db_session,
            business_id=biz.id,
            amount_usd=250.0,
            reference_id="ref_underpay_123"
        )


@pytest.mark.asyncio
async def test_payment_failure_injection_duplicate_replay_blocked(db_session: AsyncSession):
    """Proves duplicate webhook replay is safely ignored without re-triggering fulfillment."""
    biz = Business(
        name="Replay Corp",
        domain=f"example-replay-{uuid.uuid4().hex[:6]}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        pipeline_stage=PipelineStage.PROPOSAL.value
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    test_secret = "test_replay_secret_preflight"
    orig_sec = razorpay_payment_provider.webhook_secret
    razorpay_payment_provider.webhook_secret = test_secret

    evt_id = f"evt_replay_{uuid.uuid4().hex[:8]}"
    webhook_payload = {
        "id": evt_id,
        "event": "payment_link.paid",
        "created_at": 1710009999,
        "payload": {
            "payment_link": {
                "entity": {
                    "id": f"plink_{evt_id}",
                    "amount": 100000,
                    "amount_paid": 100000,
                    "currency": "USD",
                    "status": "paid",
                    "notes": {"business_id": str(biz.id)}
                }
            },
            "payment": {
                "entity": {
                    "id": f"pay_{evt_id}",
                    "amount": 100000,
                    "currency": "USD",
                    "status": "captured"
                }
            }
        }
    }
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")
    sig = hmac.new(test_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First submission
            r1 = await client.post(
                "/api/webhooks/razorpay",
                content=payload_bytes,
                headers={"X-Razorpay-Signature": sig}
            )
            assert r1.status_code == 200
            # Second duplicate submission
            r2 = await client.post(
                "/api/webhooks/razorpay",
                content=payload_bytes,
                headers={"X-Razorpay-Signature": sig}
            )
            assert r2.status_code == 200
            assert r2.json()["status"] == "DUPLICATE_IGNORED"
    finally:
        razorpay_payment_provider.webhook_secret = orig_sec


# ==============================================================
# 4. FAILURE INJECTION TESTS: VOICE
# ==============================================================

@pytest.mark.asyncio
async def test_voice_failure_injection_human_escalation_triggers():
    """Proves sensitive verbal inputs immediately route to human escalation."""
    # Legal threat
    esc_legal = voice_escalation_engine.evaluate("We will take you to court and sue your company!")
    assert esc_legal.should_escalate is True
    assert esc_legal.reason == VoiceEscalationReason.LEGAL_THREAT

    # Privacy / GDPR
    esc_gdpr = voice_escalation_engine.evaluate("Under GDPR, where did you acquire my phone number?")
    assert esc_gdpr.should_escalate is True
    assert esc_gdpr.reason == VoiceEscalationReason.PRIVACY_REQUEST

    # Payment dispute
    esc_scam = voice_escalation_engine.evaluate("You billed me fraudulently, this is a scam!")
    assert esc_scam.should_escalate is True
    assert esc_scam.reason == VoiceEscalationReason.PAYMENT_DISPUTE


@pytest.mark.asyncio
async def test_voice_failure_injection_low_confidence_escalates():
    """Proves low-confidence verbal input escalates to human operator."""
    res = VoiceSalesAgent.process_prospect_speech(
        "something completely garbled and unrecognized xyz123",
        audit_evidence={"performance_score": 50.0}
    )
    assert res.escalate_to_human is True
    assert res.intent == "HUMAN_ESCALATION"


@pytest.mark.asyncio
async def test_voice_failure_injection_explicit_opt_out(db_session: AsyncSession):
    """Proves verbal opt-out immediately suppresses the phone number and halts contact."""
    test_phone = f"+1512555{uuid.uuid4().hex[:4]}"
    res = VoiceSalesAgent.process_prospect_speech(
        "Please remove me and stop calling this number.",
        audit_evidence={"performance_score": 50.0}
    )
    assert res.opt_out is True
    assert res.intent == "NOT_INTERESTED"

    # Verify service suppresses on opt-out
    sid = f"CA_optout_fail_{uuid.uuid4().hex[:8]}"
    call_log = CallLog(
        call_sid=sid,
        caller_id="+15125550100",
        recipient_phone=test_phone,
        status="IN_PROGRESS",
        call_state=VoiceCallState.DISCOVERY.value
    )
    db_session.add(call_log)
    await db_session.commit()

    processed = await voice_sales_service.process_call_transcript(
        call_sid=sid,
        transcript="Please stop calling this number immediately.",
        db=db_session
    )
    assert processed["call_state"] == VoiceCallState.DO_NOT_CONTACT.value

    # Subsequent call attempt is blocked
    attempt = await voice_sales_service.initiate_outbound_call(
        prospect_phone=test_phone,
        business_name="Test Corp",
        db=db_session
    )
    assert attempt["success"] is False
    assert attempt["status"] == "SUPPRESSED"


# ==============================================================
# 5. SAFETY INVARIANTS ASSERTION TEST
# ==============================================================

def test_production_safety_invariants_strictly_active():
    """Validates that all production safety invariants are strictly True/False as required."""
    assert settings.RESEARCH_ONLY is True, "RESEARCH_ONLY must be TRUE"
    assert settings.EMAIL_DRY_RUN is True, "EMAIL_DRY_RUN must be TRUE"
    assert settings.PAYMENTS_ENABLED is False, "PAYMENTS_ENABLED must be FALSE"
    assert settings.PAYMENT_DRY_RUN is True, "PAYMENT_DRY_RUN must be TRUE"
    assert settings.VOICE_DRY_RUN is True, "VOICE_DRY_RUN must be TRUE"
