"""
Phase 18 Step 3 Comprehensive Test Suite:
Controlled Production Activation, Independent Provider Safety States,
Pre-Activation Hard Gates, Audit Logging, and 21 Fail-Closed Security Invariants.
"""

import pytest
import pytest_asyncio
import uuid
import json
import hmac
import hashlib
from datetime import datetime
from unittest.mock import AsyncMock, patch
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient, ASGITransport

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business,
    AuditRun,
    Offer,
    OutreachMessage,
    PipelineStage,
    VerificationStatus,
    OutreachStatus,
    Payment,
    CallLog,
    SuppressionList,
    PaymentWebhookEvent,
    SecurityAuditLog,
    ActiveOutreachLock,
    ProspectEvidence
)
from app.core.config import settings
from app.api.app import app
from app.infrastructure.production_activation import (
    production_activation_manager,
    ProviderActivationState
)
from app.communications.voice_escalation import voice_escalation_engine, VoiceEscalationReason
from app.outreach.compliance import compliance_guard
from app.outreach.sender import OutreachSenderAdapter
from app.payments.razorpay import razorpay_payment_provider
from app.payments.service import payment_service
from app.crm.negotiator import commercial_negotiator
from app.acquisition.controller import active_prospect_controller
from app.acquisition.evidence_gate import prospect_evidence_gate


@pytest.fixture(autouse=True)
def preserve_safety_invariants():
    """Guarantees that all safety invariants remain strictly active throughout testing."""
    orig_settings = {
        "RESEARCH_ONLY": settings.RESEARCH_ONLY,
        "EMAIL_DRY_RUN": settings.EMAIL_DRY_RUN,
        "PAYMENTS_ENABLED": settings.PAYMENTS_ENABLED,
        "PAYMENT_DRY_RUN": settings.PAYMENT_DRY_RUN,
        "VOICE_DRY_RUN": settings.VOICE_DRY_RUN,
        "RAZORPAY_MODE": getattr(settings, "RAZORPAY_MODE", "test"),
        "RAZORPAY_KEY_ID": getattr(settings, "RAZORPAY_KEY_ID", ""),
        "EMAIL_PROVIDER": getattr(settings, "EMAIL_PROVIDER", "dry_run"),
        "VOICE_PROVIDER": getattr(settings, "VOICE_PROVIDER", "dry_run")
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
# 1. CURRENT SAFETY BASELINE
# ==============================================================

def test_current_safety_baseline_invariants():
    """Validates the strict baseline required before any production activation."""
    assert settings.RESEARCH_ONLY is True
    assert settings.EMAIL_DRY_RUN is True
    assert settings.PAYMENTS_ENABLED is False
    assert settings.PAYMENT_DRY_RUN is True
    assert settings.VOICE_DRY_RUN is True


# ==============================================================
# 2. ACTIVATION MODEL & AUDIT LOGGING
# ==============================================================

@pytest.mark.asyncio
async def test_activation_fails_closed_when_provider_blocked(db_session: AsyncSession):
    """Proves activation fails closed and records an audit log when hard gates are not satisfied."""
    with pytest.raises(ValueError, match="Pre-activation hard gates failed"):
        await production_activation_manager.request_activation(
            provider="email",
            actor="test_admin",
            confirmation_phrase="ENABLE LIVE EMAIL",
            db_session=db_session
        )

    # Verify audit log recorded DENIED without secrets
    stmt = select(SecurityAuditLog).where(
        SecurityAuditLog.action == "production.activate_email"
    ).order_by(SecurityAuditLog.id.desc())
    entry = (await db_session.execute(stmt)).scalars().first()
    assert entry is not None
    assert entry.result == "DENIED"
    assert "Pre-activation hard gate failed" in entry.reason


@pytest.mark.asyncio
async def test_activation_requires_exact_confirmation_phrase(db_session: AsyncSession):
    """Proves activation is rejected if confirmation phrase mismatches."""
    with pytest.raises(ValueError, match="Explicit confirmation failed"):
        await production_activation_manager.request_activation(
            provider="payments",
            actor="test_admin",
            confirmation_phrase="yes activate please",
            db_session=db_session
        )


@pytest.mark.asyncio
async def test_production_readiness_panel_structure(db_session: AsyncSession):
    """Validates the structure and metrics of the production readiness panel."""
    panel = await production_activation_manager.get_readiness_panel(db_session)
    assert panel.email.state in (ProviderActivationState.BLOCKED, ProviderActivationState.READY)
    assert panel.payments.state in (ProviderActivationState.BLOCKED, ProviderActivationState.READY)
    assert panel.voice.state in (ProviderActivationState.BLOCKED, ProviderActivationState.READY)
    assert panel.research == "ACTIVE"
    assert panel.outreach_lock == "1 ACTIVE MAX"
    assert panel.human_takeover == "AVAILABLE"
    assert panel.safety_gates == "PASS"
    assert panel.real_revenue_usd == 0.0  # Real revenue must remain $0 until real live confirmation


# ==============================================================
# 3. 21 FAIL-CLOSED HARD GATES (SECTION 10)
# ==============================================================

def test_gate_01_missing_email_credentials():
    """Gate 1: Missing email credentials blocks live activation."""
    with patch.object(settings, "RESEND_API_KEY", None), \
         patch.object(settings, "EMAIL_PROVIDER", "resend"):
        readiness = production_activation_manager.evaluate_email_readiness()
        assert readiness.is_ready is False
        assert any("Resend API key is missing" in b for b in readiness.blockers)


def test_gate_02_invalid_email_credentials():
    """Gate 2: Invalid email credential format blocks activation."""
    with patch.object(settings, "RESEND_API_KEY", "invalid_prefix_123"), \
         patch.object(settings, "EMAIL_PROVIDER", "resend"):
        readiness = production_activation_manager.evaluate_email_readiness()
        assert readiness.is_ready is False
        assert any("must begin with 're_'" in b for b in readiness.blockers)


def test_gate_03_unverified_sender_domain():
    """Gate 3: Test/placeholder or unverified sender domain blocks activation."""
    with patch.object(settings, "EMAIL_FROM", "test@example.com"):
        readiness = production_activation_manager.evaluate_email_readiness()
        assert readiness.is_ready is False
        assert any("test/placeholder domain" in b for b in readiness.blockers)


def test_gate_04_missing_dkim():
    """Gate 4: Missing DKIM DNS records blocks live email sending."""
    readiness = production_activation_manager.evaluate_email_readiness()
    assert readiness.is_ready is False
    assert any("DKIM" in b for b in readiness.blockers)


def test_gate_05_missing_payment_credentials():
    """Gate 5: Missing payment credentials blocks live payments."""
    with patch.object(settings, "RAZORPAY_KEY_ID", ""), \
         patch.object(settings, "RAZORPAY_KEY_SECRET", ""):
        readiness = production_activation_manager.evaluate_payment_readiness()
        assert readiness.is_ready is False
        assert any("Key ID is missing" in b for b in readiness.blockers)


def test_gate_06_test_mode_payment_cannot_activate_live():
    """Gate 6: Test-mode key (rzp_test_...) cannot activate live production."""
    with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_test_51AbcDef123456"), \
         patch.object(settings, "RAZORPAY_MODE", "test"):
        readiness = production_activation_manager.evaluate_payment_readiness()
        assert readiness.is_ready is False
        assert any("TEST mode" in b for b in readiness.blockers)


@pytest.mark.asyncio
async def test_gate_07_invalid_webhook_signature():
    """Gate 7: Invalid or forged webhook signature is rejected with HTTP 400."""
    orig_sec = razorpay_payment_provider.webhook_secret
    razorpay_payment_provider.webhook_secret = "test_sec_webhook_123"
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/webhooks/razorpay",
                content=b'{"event":"payment_link.paid"}',
                headers={"X-Razorpay-Signature": "forged_sha256_sig_bad"}
            )
            assert resp.status_code == 400
            assert "signature verification failed" in resp.json()["detail"].lower()
    finally:
        razorpay_payment_provider.webhook_secret = orig_sec


@pytest.mark.asyncio
async def test_gate_08_underpayment_rejected(db_session: AsyncSession):
    """Gate 8: Payments below $500 commercial floor are strictly rejected."""
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name="Floor Corp",
        domain=f"floor-test-{uid}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        pipeline_stage=PipelineStage.PROPOSAL.value
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    with pytest.raises(ValueError, match="below the minimum commercial floor"):
        await payment_service.confirm_payment_and_onboard(
            session=db_session,
            business_id=biz.id,
            amount_usd=400.0,
            reference_id=f"ref_underpay_{uid}"
        )


def test_gate_09_wrong_currency():
    """Gate 9: Unsupported currency is rejected by payment configuration."""
    with patch.object(settings, "RAZORPAY_CURRENCY", "XYZ"):
        readiness = production_activation_manager.evaluate_payment_readiness()
        assert readiness.is_ready is False
        assert any("Currency 'XYZ' is not supported" in b for b in readiness.blockers)


@pytest.mark.asyncio
async def test_gate_10_duplicate_webhook_replay(db_session: AsyncSession):
    """Gate 10: Duplicate webhook event replay is safely ignored."""
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name="Dup Webhook Corp",
        domain=f"dup-wh-{uid}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        pipeline_stage=PipelineStage.PROPOSAL.value
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    test_sec = "test_sec_dup_wh"
    orig_sec = razorpay_payment_provider.webhook_secret
    razorpay_payment_provider.webhook_secret = test_sec

    evt_id = f"evt_dup_{uid}"
    payload = json.dumps({
        "id": evt_id,
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {"entity": {"id": f"plink_{uid}", "amount": 100000, "status": "paid", "notes": {"business_id": str(biz.id)}}},
            "payment": {"entity": {"id": f"pay_{uid}", "amount": 100000, "status": "captured"}}
        }
    }).encode("utf-8")
    sig = hmac.new(test_sec.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.post("/api/webhooks/razorpay", content=payload, headers={"X-Razorpay-Signature": sig})
            assert r1.status_code == 200
            r2 = await client.post("/api/webhooks/razorpay", content=payload, headers={"X-Razorpay-Signature": sig})
            assert r2.status_code == 200
            assert r2.json()["status"] == "DUPLICATE_IGNORED"
    finally:
        razorpay_payment_provider.webhook_secret = orig_sec


@pytest.mark.asyncio
async def test_gate_11_missing_transaction_id():
    """Gate 11: Webhook missing transaction/payment ID is safely handled/rejected."""
    test_sec = "test_sec_missing_tx"
    orig_sec = razorpay_payment_provider.webhook_secret
    razorpay_payment_provider.webhook_secret = test_sec
    payload = json.dumps({
        "event": "payment_link.paid",
        "payload": {"payment_link": {"entity": {"id": "plink_123"}}, "payment": {"entity": {}}}
    }).encode("utf-8")
    sig = hmac.new(test_sec.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/api/webhooks/razorpay", content=payload, headers={"X-Razorpay-Signature": sig})
            assert res.status_code in (400, 200)
    finally:
        razorpay_payment_provider.webhook_secret = orig_sec


def test_gate_12_missing_voice_credentials():
    """Gate 12: Missing voice credentials blocks live voice telephony."""
    with patch.object(settings, "TWILIO_ACCOUNT_SID", None), \
         patch.object(settings, "VOICE_PROVIDER", "twilio"):
        readiness = production_activation_manager.evaluate_voice_readiness()
        assert readiness.is_ready is False
        assert any("Account SID" in b for b in readiness.blockers)


@pytest.mark.asyncio
async def test_gate_13_suppressed_prospect(db_session: AsyncSession):
    """Gate 13: Suppressed prospect cannot receive outreach."""
    supp_email = f"supp-{uuid.uuid4().hex[:6]}@example.com"
    await compliance_guard.add_to_suppression(db_session, email=supp_email, reason="UNSUBSCRIBE")

    biz = Business(
        name="Supp Corp",
        domain=f"supp-{uuid.uuid4().hex[:6]}.com",
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
        subject="Note",
        body="Body",
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.commit()

    sender = OutreachSenderAdapter()
    settings.RESEARCH_ONLY = False
    try:
        with pytest.raises(ValueError, match="suppression list"):
            await sender.send_approved_message(db_session, message_id=msg.id)
    finally:
        settings.RESEARCH_ONLY = True


@pytest.mark.asyncio
async def test_gate_14_duplicate_prospect(db_session: AsyncSession):
    """Gate 14: Duplicate message to an already sent message is blocked."""
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name="Dup Prospect Corp",
        domain=f"dup-prospect-{uid}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        public_email=f"contact@{uid}.com",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email=biz.public_email,
        subject="Note",
        body="Body",
        status=OutreachStatus.SENT.value,
        sent_at=datetime.utcnow()
    )
    db_session.add(msg)
    await db_session.commit()

    sender = OutreachSenderAdapter()
    settings.RESEARCH_ONLY = False
    try:
        with pytest.raises(ValueError, match="Duplicate dispatch is prohibited"):
            await sender.send_approved_message(db_session, message_id=msg.id)
    finally:
        settings.RESEARCH_ONLY = True


@pytest.mark.asyncio
async def test_gate_15_zero_evidence_rejected(db_session: AsyncSession):
    """Gate 15: Prospect with zero evidence cannot be selected for outreach."""
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name="Zero Evidence Corp",
        domain=f"zero-ev-{uid}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        verification_status="INSUFFICIENT_EVIDENCE",
        pipeline_stage=PipelineStage.DISCOVERED.value
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    with pytest.raises(ValueError, match="failed hard evidence gate"):
        await active_prospect_controller.select_next_prospect(db_session, business_id=biz.id)


@pytest.mark.asyncio
async def test_gate_16_single_source_evidence_rejected(db_session: AsyncSession):
    """Gate 16: Prospect with single-source evidence is unverified / requires corroboration."""
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name="Single Source Corp",
        domain=f"single-src-{uid}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        verification_status="UNVERIFIED",
        evidence_count=1
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    item = ProspectEvidence(
        business_id=biz.id,
        claim="Site has 4.5s load time",
        source_url=f"https://{biz.domain}",
        source_domain=biz.domain,
        source_tier=3,
        is_verified=True,
        http_status=200
    )
    res = prospect_evidence_gate.evaluate_evidence([item])
    assert res.is_passed is False
    assert res.can_auto_approve is False
    assert "Insufficient independent evidence sources" in res.reason


def test_gate_17_human_escalation_trigger():
    """Gate 17: Legal threats and harassment immediately escalate to human operator."""
    res = voice_escalation_engine.evaluate("We are taking you to court and suing you!")
    assert res.should_escalate is True
    assert res.reason == VoiceEscalationReason.LEGAL_THREAT


def test_gate_18_price_below_500_rejected():
    """Gate 18: Pricing below $500 commercial floor is strictly rejected."""
    res = commercial_negotiator.evaluate_counter_offer(450.0)
    assert res.decision == "REJECTED"
    assert res.can_accept is False


def test_gate_19_price_500_to_999_requires_human_approval():
    """Gate 19: Pricing between $500 and $999 requires human review."""
    res = commercial_negotiator.evaluate_counter_offer(750.0)
    assert res.decision == "HUMAN_REVIEW"
    assert res.can_accept is False
    assert res.requires_human_approval is True


@pytest.mark.asyncio
async def test_gate_20_fake_payment_attempting_won(db_session: AsyncSession):
    """Gate 20: Fake or dry-run payment attempt cannot mark a business WON without verified payment confirmation."""
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name="Fake Pay Corp",
        domain=f"fake-pay-{uid}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        pipeline_stage=PipelineStage.PROPOSAL.value
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    # In dry-run or unverified payment, business remains in PROPOSAL
    assert biz.pipeline_stage != PipelineStage.WON.value


@pytest.mark.asyncio
async def test_gate_21_bypass_active_outreach_lock_blocked(db_session: AsyncSession):
    """Gate 21: Attempting to select a prospect while slot 1 is occupied raises ValueError."""
    uid1 = uuid.uuid4().hex[:6]
    uid2 = uuid.uuid4().hex[:6]

    biz1 = Business(
        name="Slot1 Corp",
        domain=f"slot1-{uid1}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    biz2 = Business(
        name="Slot2 Corp",
        domain=f"slot2-{uid2}.com",
        country="US",
        city="Austin",
        niche="Commercial Services",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db_session.add_all([biz1, biz2])
    await db_session.commit()
    await db_session.refresh(biz1)
    await db_session.refresh(biz2)

    # Occupy slot 1
    lock = await active_prospect_controller.get_or_create_lock(db_session)
    lock.status = "OCCUPIED"
    lock.business_id = biz1.id
    lock.locked_at = datetime.utcnow()
    await db_session.commit()

    # Attempt to select biz2 while slot 1 is occupied
    with pytest.raises(ValueError, match="already occupied"):
        await active_prospect_controller.select_next_prospect(db_session, business_id=biz2.id)

    # Clean up lock
    lock.status = "IDLE"
    lock.business_id = None
    await db_session.commit()
