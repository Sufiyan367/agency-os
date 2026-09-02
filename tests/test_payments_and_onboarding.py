import pytest
import hmac
import hashlib
import time
from sqlalchemy import select
from app.database.models import Business, Offer, Customer, Project, Payment, PipelineStage
from app.payments.provider import stripe_payment_provider, StripePaymentProvider
from app.payments.service import payment_service

@pytest.mark.asyncio
async def test_stripe_checkout_session_dry_run():
    res = await stripe_payment_provider.create_checkout_session(
        business_id=1,
        offer_id=2,
        title="Website Turnaround Package",
        amount_usd=750.0,
        customer_email="billing@client.com"
    )
    assert res["status"] == "open"
    assert res["amount"] == 750.0
    assert "checkout.stripe.com" in res["checkout_url"]
    assert res["mode"] == "dry_run"

def test_stripe_hmac_signature_verification():
    secret = "whsec_test_secret_abc123"
    provider = StripePaymentProvider(webhook_secret=secret)
    provider.enabled = True

    payload = b'{"type": "checkout.session.completed", "id": "evt_test123"}'
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    v1_sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    header = f"t={timestamp},v1={v1_sig}"

    # Valid signature
    is_valid, reason = provider.verify_webhook_signature(payload, header)
    assert is_valid is True
    assert reason == "Valid signature"

    # Forged signature
    bad_header = f"t={timestamp},v1=forged_signature_hex"
    is_valid, reason = provider.verify_webhook_signature(payload, bad_header)
    assert is_valid is False
    assert "mismatch" in reason.lower()

    # Expired timestamp (> 300s old)
    old_timestamp = timestamp - 400
    old_signed = f"{old_timestamp}.".encode("utf-8") + payload
    old_v1 = hmac.new(secret.encode("utf-8"), old_signed, hashlib.sha256).hexdigest()
    is_valid, reason = provider.verify_webhook_signature(payload, f"t={old_timestamp},v1={old_v1}")
    assert is_valid is False
    assert "tolerance" in reason.lower()

@pytest.mark.asyncio
async def test_payment_confirmation_and_automatic_onboarding(db_session):
    biz = Business(
        name="Paramount Construction Roofing",
        domain="paramountroofing.com",
        website_url="https://paramountroofing.com",
        country="US",
        niche="commercial_roofing",
        public_email="contact@paramountroofing.com",
        pipeline_stage=PipelineStage.PROPOSAL.value
    )
    db_session.add(biz)
    await db_session.flush()

    offer = Offer(
        business_id=biz.id,
        title="Turnkey Commercial Speed & Conversion Package",
        service_type="Website Turnaround",
        scope_description="Turnkey remediation of Core Web Vitals, mobile CRO, and local schema.",
        recommended_price=850.0,
        deliverables=["Core Web Vitals Optimization", "Mobile Conversion Header", "Local Schema"]
    )
    db_session.add(offer)
    await db_session.commit()

    # Confirm Payment
    res = await payment_service.confirm_payment_and_onboard(
        session=db_session,
        business_id=biz.id,
        amount_usd=850.0,
        reference_id="cs_test_payment_998877",
        payer_email="contact@paramountroofing.com"
    )

    assert res["status"] == "SUCCESS"
    assert res["amount_paid"] == 850.0

    # 1. Verify Pipeline Stage moved to WON
    await db_session.refresh(biz)
    assert biz.pipeline_stage == PipelineStage.WON.value

    # 2. Verify Customer created
    cust = await db_session.get(Customer, res["customer_id"])
    assert cust is not None
    assert cust.company_name == "Paramount Construction Roofing"
    assert cust.contract_amount == 850.0
    assert cust.onboarding_status == "ONBOARDING_COMPLETED"

    # 3. Verify Project created with tasks
    proj = await db_session.get(Project, res["project_id"])
    assert proj is not None
    assert len(proj.tasks) == 3
    assert proj.status == "IN_PROGRESS"
    assert proj.qa_checklist["production_deployed"] is False

    # 4. Verify Payment record created
    pmt = await db_session.get(Payment, res["payment_id"])
    assert pmt is not None
    assert pmt.amount == 850.0
    assert pmt.status == "COMPLETED"
    assert pmt.reference_id == "cs_test_payment_998877"

    # 5. Verify Idempotency on duplicate payment event
    res_dup = await payment_service.confirm_payment_and_onboard(
        session=db_session,
        business_id=biz.id,
        amount_usd=850.0,
        reference_id="cs_test_payment_998877"
    )
    assert res_dup["status"] == "ALREADY_PROCESSED"
