"""
Payment Provider Strategy & 5-Stage Lifecycle Test Suite.

Validates:
1. Google Pay as preferred customer-facing payment method.
2. Honest provider abstraction: Google Pay does not provide fake webhooks (is_automated_webhook_supported = False).
3. 5-Stage deterministic lifecycle:
   PROPOSAL_ACCEPTED -> PAYMENT_INSTRUCTIONS -> PAYMENT_PENDING -> VERIFIED_PAYMENT -> DELIVERY_UNLOCKED
4. Strict Anti-Fraud Guard: Rejects payment confirmation from:
   - customer message
   - screenshot
   - AI inference
   - manually typed claim
5. Trusted verification mechanism: CEO approval gate / bank reconciliation with recorded evidence & timestamp.
6. Delivery unlocking is strictly blocked until VERIFIED_PAYMENT.
7. Razorpay provider remains inactive unless explicitly configured and approved.
"""
import pytest
import uuid
from datetime import datetime
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import (
    Business, Proposal, Payment, Customer, Project, PipelineStage
)
from app.sales.payment_flow import payment_workflow_manager
from app.payments.abstraction import (
    GooglePayPaymentProvider, RealRazorpayPaymentProvider,
    MockPaymentProvider, get_payment_provider
)
from app.core.config import settings
from httpx import AsyncClient, ASGITransport
from app.api.app import app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_payment_provider_abstraction_and_gpay_properties():
    """Verify Google Pay provider properties and Razorpay safety gating."""
    gpay = GooglePayPaymentProvider()
    assert gpay.provider_name in ("google_pay", "google_pay_manual")
    # Invariant: Must NOT claim automated webhook support for Google Pay
    assert gpay.is_automated_webhook_supported is False

    # Instructions generation
    instructions = await gpay.generate_payment_instructions(
        deal_id=101,
        proposal_id=202,
        amount_usd=1250.0,
        currency="USD",
        customer_name="Apex Auto Clinic",
        customer_email="billing@apexauto.ae"
    )
    assert instructions["provider"] in ("google_pay", "google_pay_manual")
    assert instructions["status"] in ("PAYMENT_INSTRUCTIONS", "PAYMENT_REQUESTED")
    assert instructions["amount"] == 1250.0
    assert "upi://" in instructions["gpay_uri"] or "pay" in instructions["gpay_uri"]
    assert "VERIFICATION" in instructions["verification_requirement"]

    # Razorpay must be inactive unless explicitly approved
    assert settings.RAZORPAY_ENABLED is False
    provider = get_payment_provider("razorpay")
    # When RAZORPAY_ENABLED is False, get_payment_provider gracefully falls back or returns mock in test
    assert provider.provider_name in ("google_pay", "google_pay_manual", "mock_payment_provider")


@pytest.mark.asyncio
async def test_5_stage_payment_lifecycle_google_pay_end_to_end():
    """
    Executes the full 5-stage lifecycle:
    PROPOSAL_ACCEPTED -> PAYMENT_INSTRUCTIONS -> PAYMENT_PENDING -> VERIFIED_PAYMENT -> DELIVERY_UNLOCKED
    """
    biz_domain = f"gpay-test-{uuid.uuid4().hex[:6]}.com"
    async with AsyncSessionLocal() as session:
        # Create Business & Proposal
        biz = Business(
            domain=biz_domain,
            name="Apex Precision Motors",
            niche="Automotive Repair",
            city="Dubai",
            country="AE",
            pipeline_stage=PipelineStage.PROPOSAL.value
        )
        session.add(biz)
        await session.flush()

        prop = Proposal(
            business_id=biz.id,
            title="Comprehensive Turnaround Optimization Package",
            total_value=1500.0,
            advance_required=1500.0,
            status="DRAFT"
        )
        session.add(prop)
        await session.commit()
        await session.refresh(prop)

        # -------------------------------------------------------------
        # STAGE 1: PROPOSAL_ACCEPTED
        # -------------------------------------------------------------
        prop_accepted = await payment_workflow_manager.accept_proposal(
            session=session,
            proposal_id=prop.id,
            accepted_by="Managing Director",
            note="Client signed digital proposal"
        )
        assert prop_accepted.status == "PROPOSAL_ACCEPTED"
        assert prop_accepted.approved_by == "Managing Director"

        # -------------------------------------------------------------
        # STAGE 2: PAYMENT_INSTRUCTIONS -> PAYMENT_PENDING
        # -------------------------------------------------------------
        inst_res = await payment_workflow_manager.issue_payment_instructions(
            session=session,
            proposal_id=prop.id,
            provider_name="google_pay",
            amount_usd=1500.0
        )
        assert inst_res["status"] == "PAYMENT_PENDING"
        assert inst_res["provider"] == "google_pay"
        payment_id = inst_res["payment_id"]

        # Check Payment state in database
        pmt = await session.get(Payment, payment_id)
        assert pmt is not None
        assert pmt.status == "PAYMENT_PENDING"
        assert pmt.provider == "google_pay"
        assert pmt.amount == 1500.0
        assert pmt.instructions_sent_at is not None

        # -------------------------------------------------------------
        # STAGE 3: Fraud Prevention — Reject Untrusted Confirmations
        # -------------------------------------------------------------
        # A. Reject customer text claim
        with pytest.raises(PermissionError, match="Payment confirmation rejected: Source 'customer_message' is untrusted"):
            await payment_workflow_manager.verify_payment(
                session=session,
                payment_id=payment_id,
                verified_by="AI_INBOX_POLLER",
                transaction_reference="CLAIM_12345",
                amount_received=1500.0,
                source="customer_message"
            )

        # B. Reject screenshot upload claim
        with pytest.raises(PermissionError, match="Payment confirmation rejected: Source 'screenshot' is untrusted"):
            await payment_workflow_manager.verify_payment(
                session=session,
                payment_id=payment_id,
                verified_by="OCR_BOT",
                transaction_reference="SCREENSHOT_RECEIPT_IMG",
                amount_received=1500.0,
                source="screenshot"
            )

        # C. Reject AI inference claim
        with pytest.raises(PermissionError, match="Payment confirmation rejected: Source 'ai_inference' is untrusted"):
            await payment_workflow_manager.verify_payment(
                session=session,
                payment_id=payment_id,
                verified_by="LLM_SALES_AGENT",
                transaction_reference="INFERRED_PAYMENT",
                amount_received=1500.0,
                source="ai_inference"
            )

        # D. Reject unverified manual claim
        with pytest.raises(PermissionError, match="Payment confirmation rejected: Source 'manual_claim' is untrusted"):
            await payment_workflow_manager.verify_payment(
                session=session,
                payment_id=payment_id,
                verified_by="STAFF",
                transaction_reference="UNVERIFIED_PHONE_CALL",
                amount_received=1500.0,
                source="manual_claim"
            )

        # Verify payment is still in PAYMENT_PENDING
        await session.refresh(pmt)
        assert pmt.status == "PAYMENT_PENDING"

        # Invariant: Attempting to unlock delivery before verification MUST fail
        with pytest.raises(PermissionError, match="Trusted payment verification must precede delivery unlocking"):
            await payment_workflow_manager.unlock_delivery(session=session, payment_id=payment_id)

        # -------------------------------------------------------------
        # STAGE 4: VERIFIED_PAYMENT (Explicit CEO Verification Gate)
        # -------------------------------------------------------------
        ceo_verify_res = await payment_workflow_manager.verify_payment(
            session=session,
            payment_id=payment_id,
            verified_by="CEO",
            transaction_reference="HDFC_UTR_982736192837",
            amount_received=1500.0,
            source="CEO_APPROVAL",
            evidence={
                "bank_utr": "HDFC_UTR_982736192837",
                "bank_name": "HDFC Bank Corporate",
                "settlement_timestamp": datetime.utcnow().isoformat(),
                "verified_by_role": "CEO",
                "method": "GOOGLE_PAY_BUSINESS"
            }
        )
        assert ceo_verify_res.is_confirmed is True
        assert ceo_verify_res.pipeline_stage == "VERIFIED_PAYMENT"

        await session.refresh(pmt)
        assert pmt.status == "VERIFIED_PAYMENT"
        assert pmt.verified_by == "CEO"
        assert pmt.verification_method == "CEO_APPROVAL"
        assert pmt.extra_metadata["verification_evidence"]["bank_utr"] == "HDFC_UTR_982736192837"

        # -------------------------------------------------------------
        # STAGE 5: DELIVERY_UNLOCKED
        # -------------------------------------------------------------
        unlock_res = await payment_workflow_manager.unlock_delivery(session=session, payment_id=payment_id)
        assert unlock_res["is_unlocked"] is True
        assert unlock_res["delivery_stage"] == "ONBOARDING"
        assert unlock_res["business_pipeline_stage"] == PipelineStage.WON.value

        # Confirm database records updated
        await session.refresh(pmt)
        assert pmt.status == "DELIVERY_UNLOCKED"

        cust = await session.get(Customer, unlock_res["customer_id"])
        assert cust is not None
        assert cust.onboarding_status == "ONBOARDED"

        proj = await session.get(Project, unlock_res["project_id"])
        assert proj is not None
        assert proj.delivery_stage == "ONBOARDING"
        assert proj.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_payment_api_endpoints_and_untrusted_rejections():
    """
    Tests payment REST endpoints:
    1. POST /api/proposals/{proposal_id}/accept
    2. POST /api/proposals/{proposal_id}/payment-instructions
    3. POST /api/payments/{payment_id}/verify (rejection on untrusted source + success on CEO)
    4. POST /api/payments/{payment_id}/unlock-delivery
    5. GET /api/payments/{payment_id}/instructions
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create test business and proposal in DB
        async with AsyncSessionLocal() as session:
            biz = Business(
                domain=f"api-gpay-{uuid.uuid4().hex[:6]}.ae",
                name="Emirates Dental Specialists",
                niche="Dental Clinic",
                city="Abu Dhabi",
                country="AE",
                pipeline_stage=PipelineStage.PROPOSAL.value
            )
            session.add(biz)
            await session.flush()

            prop = Proposal(
                business_id=biz.id,
                title="Clinic Patient Booking Automation",
                total_value=1200.0,
                advance_required=1200.0,
                status="DRAFT"
            )
            session.add(prop)
            await session.commit()
            prop_id = prop.id

        # 1. Accept Proposal via API
        r_accept = await client.post(
            f"/api/proposals/{prop_id}/accept",
            json={"accepted_by": "Dr. Tariq Al-Mansoor", "notes": "Approved patient booking portal deliverables"}
        )
        assert r_accept.status_code == 200
        assert r_accept.json()["status"] == "PROPOSAL_ACCEPTED"

        # 2. Issue Payment Instructions via API (Google Pay)
        r_inst = await client.post(
            f"/api/proposals/{prop_id}/payment-instructions",
            json={"provider": "google_pay", "amount_usd": 1200.0}
        )
        assert r_inst.status_code == 200
        inst_data = r_inst.json()
        assert inst_data["provider"] == "google_pay"
        assert inst_data["status"] == "PAYMENT_PENDING"
        payment_id = inst_data["payment_id"]

        # 3. GET payment instructions
        r_get_inst = await client.get(f"/api/payments/{payment_id}/instructions")
        assert r_get_inst.status_code == 200
        assert r_get_inst.json()["provider"] == "google_pay"
        assert "instructions" in r_get_inst.json()

        # 4. Attempt verification with UNTRUSTED source (customer_message) -> Must return 403 Forbidden
        r_untrusted_msg = await client.post(
            f"/api/payments/{payment_id}/verify",
            json={
                "transaction_reference": "WHATSAPP_TEXT_PROOF",
                "amount_received": 1200.0,
                "source": "customer_message"
            }
        )
        assert r_untrusted_msg.status_code == 403
        assert "untrusted" in r_untrusted_msg.json()["detail"].lower()

        # 5. Attempt verification with UNTRUSTED screenshot -> Must return 403 Forbidden
        r_untrusted_screen = await client.post(
            f"/api/payments/{payment_id}/verify",
            json={
                "transaction_reference": "SCREENSHOT_OF_GPAY_SCREEN",
                "amount_received": 1200.0,
                "source": "screenshot"
            }
        )
        assert r_untrusted_screen.status_code == 403
        assert "untrusted" in r_untrusted_screen.json()["detail"].lower()

        # 6. Attempt delivery unlock BEFORE verified payment -> Must return 403 Forbidden
        r_unlock_early = await client.post(f"/api/payments/{payment_id}/unlock-delivery")
        assert r_unlock_early.status_code == 403
        assert "must precede delivery unlocking" in r_unlock_early.json()["detail"].lower()

        # 7. Valid CEO Verification -> Succeeds
        r_ceo_verify = await client.post(
            f"/api/payments/{payment_id}/verify",
            json={
                "transaction_reference": "ADCB_BANK_REF_98127391823",
                "amount_received": 1200.0,
                "source": "CEO_APPROVAL",
                "evidence": {
                    "settlement_ledger": "ADCB_CORPORATE_LEDGER",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
        )
        assert r_ceo_verify.status_code == 200
        assert r_ceo_verify.json()["is_confirmed"] is True
        assert r_ceo_verify.json()["pipeline_stage"] == "VERIFIED_PAYMENT"

        # 8. Delivery Unlock -> Succeeds
        r_unlock = await client.post(f"/api/payments/{payment_id}/unlock-delivery")
        assert r_unlock.status_code == 200
        assert r_unlock.json()["is_unlocked"] is True
        assert r_unlock.json()["delivery_stage"] == "ONBOARDING"
        assert r_unlock.json()["business_pipeline_stage"] == PipelineStage.WON.value

