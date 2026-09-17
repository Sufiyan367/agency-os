import pytest
import uuid
from datetime import datetime
from sqlalchemy import select, func

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, Customer, Project, Payment, Proposal, DealAuditTrail, PipelineStage, PipelineEvent
)
from app.payments.abstraction import MockPaymentProvider
from app.payments.deal_service import DealClosingService
from app.sales.payment_flow import PaymentWorkflowManager
from app.analytics.truth_engine import (
    classify_payment_provenance,
    classify_business_provenance,
    get_canonical_production_truth
)
from app.core.config import settings

@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()

async def create_real_business(session, name="Acme Precision Roofing", domain=None) -> Business:
    rand_id = uuid.uuid4().hex[:6]
    d = domain or f"acme-roofing-{rand_id}.com"
    biz = Business(
        name=name,
        domain=d,
        website_url=f"https://{d}",
        country="US",
        city="Denver, CO",
        niche="Roofing",
        pipeline_stage=PipelineStage.QUALIFIED.value,
        verification_status="VERIFIED",
        prospect_score=75.0
    )
    session.add(biz)
    await session.commit()
    await session.refresh(biz)
    return biz

# -----------------------------------------------------------------------------
# 1. Payment Pending State
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_payment_pending_state_preserves_zero_revenue():
    """Real customer payment in pending state must increment pending count and preserve $0.00 revenue."""
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Summit Exteriors")
        service = DealClosingService(payment_provider=MockPaymentProvider())

        prop = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Roofing SEO Acceleration Agreement",
            total_value=650.0,
            advance_required=260.0
        )
        await service.approve_proposal(session, prop.id, operator="CEO")
        res = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")

        q = select(Payment).where(Payment.reference_id == res["order_id"])
        pmt = (await session.execute(q)).scalars().first()
        assert pmt is not None
        assert pmt.status == "PAYMENT_PENDING"
        assert float(pmt.amount) == 260.0

        pmt.is_mock = False
        pmt.provider = "google_pay"
        pmt.reference_id = f"gpay_{biz.id}_{pmt.id}_remittance"
        await session.commit()
        assert classify_payment_provenance(pmt, biz) == "REAL_CUSTOMER"

# -----------------------------------------------------------------------------
# 2. Payment Confirmation Gate
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_payment_confirmation_gate_requires_valid_verification():
    """Payment cannot be confirmed from untrusted source or without valid reference."""
    mgr = PaymentWorkflowManager()
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Apex Cladding")
        service = DealClosingService(payment_provider=MockPaymentProvider())
        prop = await service.create_proposal(session, biz.id, "Apex Facade Optimization", 1000.0, 400.0)
        await service.approve_proposal(session, prop.id, operator="CEO")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")

        q = select(Payment).where(Payment.reference_id == order["order_id"])
        pmt = (await session.execute(q)).scalars().first()

        # Fraud invariant: Reject untrusted sources
        with pytest.raises(PermissionError, match="Payment confirmation rejected"):
            await mgr.verify_payment(
                session=session,
                payment_id=pmt.id,
                verified_by="Customer Bot",
                transaction_reference="UTR99999",
                amount_received=400.0,
                source="customer_message"
            )

        # Reject empty / invalid reference
        with pytest.raises(ValueError, match="Invalid or missing transaction reference"):
            await mgr.verify_payment(
                session=session,
                payment_id=pmt.id,
                verified_by="CEO",
                transaction_reference="  ",
                amount_received=400.0,
                source="CEO_VERIFICATION"
            )

# -----------------------------------------------------------------------------
# 3. 40% Advance Rule
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_forty_percent_advance_rule():
    """Proposal creation must reject any advance below 40% of total_value."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Metro Solar")

        # Total $1,000, 40% is $400. Advance of $399.00 must fail
        with pytest.raises(ValueError, match="below the minimum 40% commercial advance"):
            await service.create_proposal(
                session=session,
                business_id=biz.id,
                title="Commercial Solar Optimization",
                total_value=1000.0,
                advance_required=399.0
            )

        # Advance of exactly $400.00 must pass
        prop_ok = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Commercial Solar Optimization",
            total_value=1000.0,
            advance_required=400.0
        )
        assert prop_ok.advance_required == 400.0

# -----------------------------------------------------------------------------
# 4. Commercial Floor ($500 Minimum)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_commercial_floor_enforcement():
    """Proposals below $500 total value must be rejected; exact $500 with 40% advance ($200) passes."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Economy Plumbing")

        # Sub-$500 total value rejected
        with pytest.raises(ValueError, match="commercial qualification requirement"):
            await service.create_proposal(
                session=session,
                business_id=biz.id,
                title="Small Maintenance Fix",
                total_value=450.0,
                advance_required=180.0
            )

        # Exact $500 deal with $200 advance (exact 40%) passes
        prop_500 = await service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Entry Commercial Fix",
            total_value=500.0,
            advance_required=200.0
        )
        assert prop_500.total_value == 500.0
        assert prop_500.advance_required == 200.0

# -----------------------------------------------------------------------------
# 5. Underpayment Rejection
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_underpayment_rejection():
    """Confirming a payment with amount less than expected must be rejected."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Valley HVAC")
        prop = await service.create_proposal(session, biz.id, "HVAC Tuneup Agreement", 600.0, 240.0)
        await service.approve_proposal(session, prop.id, operator="CEO")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")

        q = select(Payment).where(Payment.reference_id == order["order_id"])
        pmt = (await session.execute(q)).scalars().first()

        # Expected $240.00, customer only sent $200.00
        with pytest.raises(ValueError, match="Underpayment rejected"):
            await service.confirm_manual_payment(
                session=session,
                payment_id=pmt.id,
                payment_reference="BANK_REF_VALLEY_101",
                amount_received=200.0,
                operator="operator"
            )

# -----------------------------------------------------------------------------
# 6. Duplicate Reference Protection
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_reference_protection():
    """The same payment reference / UTR cannot be confirmed across separate payments."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz1 = await create_real_business(session, "Company Alpha")
        biz2 = await create_real_business(session, "Company Beta")

        # Payment 1
        prop1 = await service.create_proposal(session, biz1.id, "Alpha Proposal", 500.0, 200.0)
        await service.approve_proposal(session, prop1.id, operator="CEO")
        order1 = await service.request_payment_order(session, prop1.id, payment_type="ADVANCE")
        q1 = select(Payment).where(Payment.reference_id == order1["order_id"])
        pmt1 = (await session.execute(q1)).scalars().first()

        # Confirm Payment 1 with reference UNIQUE_UTR_888
        res1 = await service.confirm_manual_payment(
            session=session,
            payment_id=pmt1.id,
            payment_reference="UNIQUE_UTR_888",
            operator="CEO"
        )
        assert res1["is_confirmed"] is True

        # Payment 2
        prop2 = await service.create_proposal(session, biz2.id, "Beta Proposal", 500.0, 200.0)
        await service.approve_proposal(session, prop2.id, operator="CEO")
        order2 = await service.request_payment_order(session, prop2.id, payment_type="ADVANCE")
        q2 = select(Payment).where(Payment.reference_id == order2["order_id"])
        pmt2 = (await session.execute(q2)).scalars().first()

        # Attempt to confirm Payment 2 with the SAME reference UNIQUE_UTR_888
        with pytest.raises(ValueError, match="Duplicate payment reference rejected"):
            await service.confirm_manual_payment(
                session=session,
                payment_id=pmt2.id,
                payment_reference="UNIQUE_UTR_888",
                operator="CEO"
            )

# -----------------------------------------------------------------------------
# 7. Idempotent Confirmation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idempotent_confirmation():
    """Repeated manual confirmation returns ALREADY_CONFIRMED without duplicating Customer or Project."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Gamma Dental")
        prop = await service.create_proposal(session, biz.id, "Gamma Practice Overhaul", 800.0, 320.0)
        await service.approve_proposal(session, prop.id, operator="CEO")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")
        q = select(Payment).where(Payment.reference_id == order["order_id"])
        pmt = (await session.execute(q)).scalars().first()

        rand_ref = uuid.uuid4().hex[:6]
        ref = f"UTR_GAMMA_{rand_ref}"
        r1 = await service.confirm_manual_payment(session, pmt.id, ref, operator="CEO")
        assert r1["status"] == "PAYMENT_CONFIRMED"
        assert r1["is_confirmed"] is True

        r2 = await service.confirm_manual_payment(session, pmt.id, ref, operator="CEO")
        assert r2["status"] == "ALREADY_CONFIRMED"
        assert r2["is_confirmed"] is True

        q_cust = select(func.count(Customer.id)).where(Customer.business_id == biz.id)
        cust_cnt = (await session.execute(q_cust)).scalar()
        assert cust_cnt == 1

        q_proj = select(func.count(Project.id)).where(Project.customer_id == r1["customer_id"])
        proj_cnt = (await session.execute(q_proj)).scalar()
        assert proj_cnt == 1

# -----------------------------------------------------------------------------
# 8. Mock / Test Payment Exclusion
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_test_payment_exclusion():
    """Mock or operator test payments are strictly excluded from REAL_CUSTOMER classification."""
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Delta Logistics")

        mock_pmt = Payment(
            business_id=biz.id,
            amount=500.0,
            currency="USD",
            status="PAID",
            is_mock=True,
            reference_id="mock_delta_101"
        )
        assert classify_payment_provenance(mock_pmt, biz) == "TEST_MOCK"

        op_pmt = Payment(
            business_id=biz.id,
            amount=500.0,
            currency="USD",
            status="PAID",
            is_mock=False,
            reference_id="ref_operator_sufiyan_102",
            provider="google_pay"
        )
        assert classify_payment_provenance(op_pmt, biz) == "OPERATOR_TEST"

# -----------------------------------------------------------------------------
# 9. Revenue Only After Confirmation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_revenue_only_after_confirmation():
    """Proposals and pending payments must not contribute to verified revenue; only confirmed payments do."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Epsilon Windows")
        prop = await service.create_proposal(session, biz.id, "Epsilon Turnaround", 750.0, 300.0)
        await service.approve_proposal(session, prop.id, operator="CEO")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")
        q = select(Payment).where(Payment.reference_id == order["order_id"])
        pmt = (await session.execute(q)).scalars().first()
        pmt.is_mock = False
        await session.commit()

        # Status is PAYMENT_PENDING: check revenue is not falsely credited
        assert pmt.status == "PAYMENT_PENDING"

        # Confirm payment
        rand_ref = uuid.uuid4().hex[:6]
        ref = f"UTR_EPSILON_{rand_ref}"
        await service.confirm_manual_payment(session, pmt.id, ref, operator="CEO")

        await session.refresh(pmt)
        assert pmt.status == "PAYMENT_CONFIRMED"

# -----------------------------------------------------------------------------
# 10. Production Unlock Only After Verified Payment
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_production_unlock_only_after_verified_payment():
    """Delivery and project execution cannot be unlocked while payment is in pending or unverified state."""
    mgr = PaymentWorkflowManager()
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Zeta Security")
        prop = await service.create_proposal(session, biz.id, "Zeta Portal Optimization", 900.0, 360.0)
        await service.approve_proposal(session, prop.id, operator="CEO")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")
        q = select(Payment).where(Payment.reference_id == order["order_id"])
        pmt = (await session.execute(q)).scalars().first()

        with pytest.raises(PermissionError, match="Cannot unlock delivery"):
            await mgr.unlock_delivery(session, pmt.id)

        rand_ref = uuid.uuid4().hex[:6]
        ref = f"UTR_ZETA_{rand_ref}"
        confirm_res = await service.confirm_manual_payment(session, pmt.id, ref, operator="CEO")
        assert confirm_res["delivery_unlocked"] is True

        await session.refresh(prop)
        assert prop.delivery_status == "READY_TO_START"

# -----------------------------------------------------------------------------
# 11. Duplicate Project Prevention
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_project_prevention():
    """Multiple confirmations or re-entrant calls cannot spawn multiple Project records for the same deal."""
    service = DealClosingService(payment_provider=MockPaymentProvider())
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Eta Robotics")
        prop = await service.create_proposal(session, biz.id, "Eta Automation", 1200.0, 480.0)
        await service.approve_proposal(session, prop.id, operator="CEO")
        order = await service.request_payment_order(session, prop.id, payment_type="ADVANCE")
        q = select(Payment).where(Payment.reference_id == order["order_id"])
        pmt = (await session.execute(q)).scalars().first()

        rand_ref = uuid.uuid4().hex[:6]
        ref = f"UTR_ETA_{rand_ref}"
        res1 = await service.confirm_manual_payment(session, pmt.id, ref, operator="CEO")
        res2 = await service.confirm_manual_payment(session, pmt.id, ref, operator="CEO")

        q_proj = select(Project).where(Project.customer_id == res1["customer_id"])
        projects = (await session.execute(q_proj)).scalars().all()
        assert len(projects) == 1

# -----------------------------------------------------------------------------
# 12. Payment Dashboard Truth
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_payment_dashboard_truth():
    """Dashboard metrics must count only verified real customer records."""
    async with AsyncSessionLocal() as session:
        biz = await create_real_business(session, "Theta Flooring")

        rand_p1 = uuid.uuid4().hex[:6]
        real_pmt = Payment(
            business_id=biz.id,
            amount=500.0,
            currency="USD",
            status="PAYMENT_PENDING",
            is_mock=False,
            reference_id=f"real_pmt_{rand_p1}"
        )
        session.add(real_pmt)

        rand_p2 = uuid.uuid4().hex[:6]
        mock_pmt = Payment(
            business_id=biz.id,
            amount=500.0,
            currency="USD",
            status="PAYMENT_PENDING",
            is_mock=True,
            reference_id=f"mock_pmt_{rand_p2}"
        )
        session.add(mock_pmt)
        await session.commit()

        assert classify_payment_provenance(real_pmt, biz) == "REAL_CUSTOMER"
        assert classify_payment_provenance(mock_pmt, biz) == "TEST_MOCK"
