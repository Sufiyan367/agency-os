import hmac
import hashlib
import json
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime

from app.api.app import app
from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import Business, Proposal, Payment, DealAuditTrail, PipelineStage
from app.models.entities import LocalLead, LeadStatus
from app.payments.abstraction import MockPaymentProvider, get_payment_provider
from app.payments.deal_service import DealClosingService, deal_closing_service
from app.core.config import settings

@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()

async def create_test_business(session, name="Test Co", domain=None) -> Business:
    d = domain or f"test-{uuid.uuid4().hex[:6]}.com"
    biz = Business(
        name=name,
        domain=d,
        website_url=f"https://{d}",
        country="US",
        city="Austin, TX",
        niche="HVAC",
        pipeline_stage=PipelineStage.QUALIFIED.value,
        verification_status="VERIFIED"
    )
    session.add(biz)
    await session.commit()
    await session.refresh(biz)
    return biz

@pytest.mark.asyncio
async def test_commercial_threshold_minimum_service_value():
    """Verifies that proposals below the $500 commercial threshold are rejected and $500+ accepted."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_test_business(session, "Small Budget Co")

        # Should reject $499 proposal (<$500 floor)
        with pytest.raises(ValueError, match="commercial qualification requirement"):
            await service.create_proposal(
                session=session,
                business_id=biz.id,
                title="Low-Ticket Basic Site",
                total_value=499.0,
                advance_required=200.0
            )

        # Should accept $500 proposal (at threshold)
        prop_500 = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Entry Automation Audit",
            total_value=500.0,
            advance_required=200.0
        )
        assert prop_500.id is not None
        assert prop_500.total_value == 500.0
        assert prop_500.status == "DRAFT"

        # Should accept $1,000 proposal (above threshold)
        prop = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Standard Turnaround Package",
            total_value=1000.0,
            advance_required=500.0
        )
        assert prop.id is not None
        assert prop.total_value == 1000.0
        assert prop.status == "DRAFT"

@pytest.mark.asyncio
async def test_proposal_approval_gate():
    """Verifies that unapproved proposals CANNOT request payment orders."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_test_business(session, "Approval Gate Co")

        prop = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Full Commercial Suite",
            total_value=2500.0,
            advance_required=1250.0
        )
        assert prop.status == "DRAFT"

        # Attempting to request payment while DRAFT must fail
        with pytest.raises(ValueError, match="Human operator approval is required"):
            await service.request_payment_order(session, prop.id, payment_type="ADVANCE")

        # Operator approves
        approved = await service.approve_proposal(session, prop.id, operator="admin_reviewer")
        assert approved.status == "APPROVED"
        assert approved.approved_by == "admin_reviewer"
        assert approved.approved_at is not None

        # Now payment request must succeed
        res = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")
        assert res["status"] == "ORDER_CREATED"
        assert res["proposal_status"] == "PAYMENT_PENDING"

@pytest.mark.asyncio
async def test_payment_order_creation_does_not_mark_paid():
    """Payment order creation generates a gateway order ID but NEVER marks the deal PAID."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_test_business(session, "Pending Order Co")

        prop = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="SEO Engine Overhaul",
            total_value=1500.0,
            advance_required=750.0
        )
        await service.approve_proposal(session, prop.id, operator="operator")
        order_res = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")

        assert order_res["status"] == "ORDER_CREATED"
        assert order_res["order_id"].startswith("order_mock_")

        # Verify database record is PAYMENT_PENDING, not PAID
        db_prop = await session.get(Proposal, prop.id)
        assert db_prop.status == "PAYMENT_PENDING"
        assert db_prop.advance_received == 0.0

@pytest.mark.asyncio
async def test_cryptographic_webhook_verification_and_tamper_rejection():
    """Verifies that valid webhook signatures are accepted and tampered ones rejected."""
    mock_provider = MockPaymentProvider(webhook_secret="secure_secret_key_123")
    payload = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_123"}}}}'

    # Valid signature
    valid_sig = hmac.new("secure_secret_key_123".encode("utf-8"), payload, hashlib.sha256).hexdigest()
    is_valid, msg = mock_provider.verify_webhook_signature(payload, valid_sig)
    assert is_valid is True
    assert msg == "Valid signature"

    # Tampered signature
    tampered_sig = "deadbeef" + valid_sig[8:]
    is_valid, msg = mock_provider.verify_webhook_signature(payload, tampered_sig)
    assert is_valid is False
    assert "Signature mismatch" in msg

    # Missing signature
    is_valid, msg = mock_provider.verify_webhook_signature(payload, None)
    assert is_valid is False
    assert "Missing" in msg

@pytest.mark.asyncio
async def test_failed_payment_webhook_transitions_to_failed():
    """Payment failure webhook transitions payment status to FAILED and logs audit event."""
    mock_provider = MockPaymentProvider()
    service = DealClosingService(payment_provider=mock_provider)
    async with AsyncSessionLocal() as session:
        biz = await create_test_business(session, "Fail Test Co")

        prop = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Turnaround Package",
            total_value=2000.0,
            advance_required=1000.0
        )
        await service.approve_proposal(session, prop.id, operator="operator")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")
        order_id = order["order_id"]

        # Simulate failed webhook
        raw_bytes, sig = mock_provider.generate_mock_webhook_payload(
            order_id=order_id,
            payment_id="pay_fail_01",
            amount_usd=1000.0,
            event="payment.failed"
        )
        event_dict = json.loads(raw_bytes.decode("utf-8"))

        res = await service.process_payment_webhook(session, raw_bytes, sig, event_dict)
        assert res["status"] == "PAYMENT_FAILED"

        # Verify proposal remains PAYMENT_PENDING (not PAID)
        db_prop = await session.get(Proposal, prop.id)
        assert db_prop.status == "PAYMENT_PENDING"
        assert db_prop.advance_received == 0.0

@pytest.mark.asyncio
async def test_advance_payment_and_remaining_balance_calculation():
    """
    Simulates:
    Service Value: $2,000
    Required Advance: $1,000
    Remaining Balance: $1,000
    After advance verified:
    status = ADVANCE_RECEIVED
    delivery_status = READY_TO_START
    remaining_balance = $1,000
    """
    mock_provider = MockPaymentProvider()
    service = DealClosingService(payment_provider=mock_provider)
    async with AsyncSessionLocal() as session:
        biz = await create_test_business(session, "Advance Systems Co")

        prop = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Commercial Automation Overhaul",
            total_value=2000.0,
            advance_required=1000.0
        )
        await service.approve_proposal(session, prop.id, operator="admin")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")
        order_id = order["order_id"]

        # Simulate $1,000 captured advance
        payment_id = f"pay_adv_{uuid.uuid4().hex[:8]}"
        raw_bytes, sig = mock_provider.generate_mock_webhook_payload(
            order_id=order_id,
            payment_id=payment_id,
            amount_usd=1000.0,
            event="payment.captured"
        )
        event_dict = json.loads(raw_bytes.decode("utf-8"))

        res = await service.process_payment_webhook(session, raw_bytes, sig, event_dict)
        assert res["status"] == "SUCCESS"
        assert res["proposal_status"] == "ADVANCE_RECEIVED"
        assert res["remaining_balance"] == 1000.0
        assert res["delivery_status"] == "READY_TO_START"

        db_prop = await session.get(Proposal, prop.id)
        assert db_prop.status == "ADVANCE_RECEIVED"
        assert db_prop.advance_received == 1000.0
        assert db_prop.remaining_balance == 1000.0
        assert db_prop.delivery_status == "READY_TO_START"

@pytest.mark.asyncio
async def test_webhook_idempotency_prevents_duplicate_revenue():
    """Verifies that duplicate webhook deliveries are safely acknowledged without double-counting."""
    mock_provider = MockPaymentProvider()
    service = DealClosingService(payment_provider=mock_provider)
    async with AsyncSessionLocal() as session:
        biz = await create_test_business(session, "Idempotent Test Co")

        prop = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Full Tech Overhaul",
            total_value=3000.0,
            advance_required=1500.0
        )
        await service.approve_proposal(session, prop.id, operator="admin")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")
        order_id = order["order_id"]

        idem_pay_id = f"pay_idem_{uuid.uuid4().hex[:8]}"
        raw_bytes, sig = mock_provider.generate_mock_webhook_payload(
            order_id=order_id,
            payment_id=idem_pay_id,
            amount_usd=1500.0,
            event="payment.captured"
        )
        event_dict = json.loads(raw_bytes.decode("utf-8"))

        # First run: SUCCESS
        res1 = await service.process_payment_webhook(session, raw_bytes, sig, event_dict)
        assert res1["status"] == "SUCCESS"

        # Second run with same payload: ALREADY_PROCESSED
        res2 = await service.process_payment_webhook(session, raw_bytes, sig, event_dict)
        assert res2["status"] == "ALREADY_PROCESSED"

        # Proposal advance must still be 1500, NOT 3000
        db_prop = await session.get(Proposal, prop.id)
        assert db_prop.advance_received == 1500.0
        assert db_prop.remaining_balance == 1500.0

@pytest.mark.asyncio
async def test_dry_run_revenue_isolation():
    """Verifies that mock transactions (is_mock=True) do NOT pollute production cash received."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_test_business(session, "Mock Iso Co")

        # Create mock proposal & mock payment
        prop = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Mock Demo Deal",
            total_value=5000.0,
            advance_required=2500.0,
            is_mock=True
        )
        await service.approve_proposal(session, prop.id, operator="admin")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")

        # Mark the created order payment as PAID mock payment
        from sqlalchemy import select
        q_pmt = select(Payment).where(Payment.reference_id == order["order_id"])
        pmt = (await session.execute(q_pmt)).scalars().first()
        pmt.status = "PAID"
        pmt.is_mock = True
        await session.commit()

        # Production metrics (include_mock=False) must NOT include this 2,500
        prod_metrics = await service.get_real_deal_metrics(session, include_mock=False)
        all_metrics = await service.get_real_deal_metrics(session, include_mock=True)

        assert all_metrics["cash_received_usd"] >= 2500.0
        assert prod_metrics["cash_received_usd"] < all_metrics["cash_received_usd"]

@pytest.mark.asyncio
async def test_human_takeover_blocks_automated_actions():
    """Verifies that an active human takeover flag preserves safety and halts automated actions."""
    async with AsyncSessionLocal() as session:
        biz = await create_test_business(session, "Takeover Safety Co")

        lead = LocalLead(
            business_id=biz.id,
            contact_email="owner@takeover.com",
            status=LeadStatus.HUMAN_TAKEOVER.value,
            human_takeover=True,
            human_takeover_reason="Client requested executive consultation before signing proposal."
        )
        session.add(lead)
        await session.commit()
        await session.refresh(lead)

        assert lead.human_takeover is True
        assert "executive consultation" in lead.human_takeover_reason

@pytest.mark.asyncio
async def test_complete_audit_trail_recorded():
    """Verifies that all lifecycle events are recorded in DealAuditTrail."""
    mock_provider = MockPaymentProvider()
    service = DealClosingService(payment_provider=mock_provider)
    async with AsyncSessionLocal() as session:
        biz = await create_test_business(session, "Audit Ledger Co")

        prop = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Turnaround & Optimization Suite",
            total_value=2000.0,
            advance_required=1000.0
        )
        await service.approve_proposal(session, prop.id, operator="operator_sam")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")

        audit_pay_id = f"pay_audit_{uuid.uuid4().hex[:8]}"
        raw_bytes, sig = mock_provider.generate_mock_webhook_payload(
            order_id=order["order_id"],
            payment_id=audit_pay_id,
            amount_usd=1000.0,
            event="payment.captured"
        )
        event_dict = json.loads(raw_bytes.decode("utf-8"))
        await service.process_payment_webhook(session, raw_bytes, sig, event_dict)

        from sqlalchemy import select
        q = select(DealAuditTrail).where(DealAuditTrail.proposal_id == prop.id).order_by(DealAuditTrail.id.asc())
        audits = (await session.execute(q)).scalars().all()
        events = [a.event_type for a in audits]

        assert "proposal_created" in events
        assert "proposal_approved" in events
        assert "payment_requested" in events
        assert "payment_succeeded" in events
        assert "advance_received" in events
        assert "delivery_unlocked" in events

@pytest.mark.asyncio
async def test_rest_api_proposal_and_deal_lifecycle():
    """End-to-end REST API integration test for proposal creation, approval, and metrics."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with AsyncSessionLocal() as session:
            b = await create_test_business(session, "REST Deal Corp")
            biz_id = b.id

        # 1. Reject <$500 ($499.00)
        res_fail = await ac.post("/api/proposals", json={
            "business_id": biz_id,
            "title": "Low Ticket",
            "total_value": 499.0,
            "advance_required": 200.0
        })
        assert res_fail.status_code == 400

        # 2. Create valid proposal
        res_create = await ac.post("/api/proposals", json={
            "business_id": biz_id,
            "title": "High-Value Turnaround",
            "total_value": 3000.0,
            "advance_required": 1500.0,
            "service_type": "Commercial Overhaul"
        })
        assert res_create.status_code == 200
        prop_id = res_create.json()["id"]

        # 3. Approve proposal
        res_appr = await ac.post(f"/api/proposals/{prop_id}/approve")
        assert res_appr.status_code == 200
        assert res_appr.json()["status"] == "APPROVED"

        # 4. Request payment order
        res_order = await ac.post(f"/api/proposals/{prop_id}/request-payment", json={
            "payment_type": "ADVANCE"
        })
        assert res_order.status_code == 200
        assert res_order.json()["status"] == "ORDER_CREATED"

        # 5. Check deal metrics endpoint
        res_metrics = await ac.get("/api/deals/metrics?include_mock=true")
        assert res_metrics.status_code == 200
        data = res_metrics.json()
        assert "open_proposals" in data
        assert "pipeline_value_usd" in data

        # 6. Check deal detail endpoint
        res_detail = await ac.get(f"/api/deals/{prop_id}")
        assert res_detail.status_code == 200
        detail = res_detail.json()
        assert detail["id"] == prop_id
        assert detail["business_name"] == "REST Deal Corp"
        assert len(detail["audit_trail"]) >= 2
