import pytest
import uuid
from datetime import datetime
from sqlalchemy import select, func

from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import (
    Business, Proposal, Payment, Customer, Project, PipelineStage
)
from app.payments.abstraction import get_payment_provider, GooglePayPaymentProvider
from app.payments.deal_service import deal_closing_service
from app.core.config import settings
from httpx import AsyncClient, ASGITransport
from app.api.app import app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_google_pay_manual_provider_properties():
    """Verify Google Pay manual provider properties and safety constraints."""
    provider = get_payment_provider()
    assert isinstance(provider, GooglePayPaymentProvider)
    assert provider.provider_name in ("google_pay_manual", "google_pay")
    # Anti-fake invariant: Standalone GPay must NEVER claim server-side webhook automation
    assert provider.is_automated_webhook_supported is False

    # Also test aliases
    assert isinstance(get_payment_provider("google_pay_manual"), GooglePayPaymentProvider)
    assert isinstance(get_payment_provider("google_pay"), GooglePayPaymentProvider)
    assert isinstance(get_payment_provider("upi_manual"), GooglePayPaymentProvider)


@pytest.mark.asyncio
async def test_generate_payment_instructions_fields():
    """Verify generated remittance payment instructions format and fields."""
    provider = GooglePayPaymentProvider()
    res = await provider.generate_payment_instructions(
        deal_id=401,
        proposal_id=502,
        amount_usd=1000.0,
        currency="USD",
        customer_name="Grand Auto Repair",
        customer_email="billing@grandauto.ae"
    )

    assert res["amount"] == 1000.0
    assert res["currency"] == "USD"
    assert "OS-REM-502-" in res["payment_reference"]
    assert res["status"] == "PAYMENT_REQUESTED"
    assert res["verification_requirement"] == "HUMAN_OPERATOR_VERIFICATION"
    assert res["recipient_upi_id"] is not None
    assert "@" in res["recipient_upi_id"]
    assert res["recipient_name"] is not None
    assert "expires_at" in res
    assert "created_at" in res
    # Clean customer instructions: must include reference code and VPA
    assert res["payment_reference"] in res["instructions"]
    assert res["recipient_upi_id"] in res["instructions"]
    # Invariant: Never leak database connection strings or secrets
    assert "sqlite" not in res["instructions"].lower()
    assert "secret" not in res["instructions"].lower()


@pytest.mark.asyncio
async def test_operator_confirm_payment_flow_and_delivery_unlock():
    """
    End-to-End Google Pay Remittance Flow:
    1. Proposal accepted and payment requested
    2. Payment record created with status PAYMENT_PENDING / PAYMENT_REQUESTED
    3. Operator explicitly confirms incoming remittance with bank UTR reference
    4. Transition to PAYMENT_CONFIRMED
    5. Existing delivery automation unlocks (Customer + Project provisioned)
    """
    async with AsyncSessionLocal() as session:
        # Create prospect and proposal
        biz = Business(
            domain=f"gpay-remit-{uuid.uuid4().hex[:6]}.com",
            name="Apex Fleet Engineering",
            niche="Commercial Fleet",
            city="Dubai",
            country="AE",
            pipeline_stage=PipelineStage.PROPOSAL.value
        )
        session.add(biz)
        await session.flush()

        prop = await deal_closing_service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Full Autonomous Turnaround",
            total_value=1200.0,
            advance_required=600.0
        )
        await deal_closing_service.approve_proposal(session, prop.id, operator="operator")

        # Request payment order
        order_res = await deal_closing_service.request_payment_order(
            session=session,
            proposal_id=prop.id,
            payment_type="ADVANCE"
        )
        assert order_res["status"] == "ORDER_CREATED"

        # Find payment record
        q_pmt = select(Payment).where(Payment.proposal_id == prop.id)
        pmt = (await session.execute(q_pmt)).scalars().first()
        assert pmt is not None
        assert pmt.status in ("PAYMENT_PENDING", "PAYMENT_REQUESTED")

        # Operator confirms payment manually
        utr_code = f"HDFC_UTR_{uuid.uuid4().hex[:10].upper()}"
        confirm_res = await deal_closing_service.confirm_manual_payment(
            session=session,
            payment_id=pmt.id,
            payment_reference=utr_code,
            operator="operator_john",
            amount_received=600.0,
            notes="Verified against bank inward remittance ledger."
        )

        assert confirm_res["status"] == "PAYMENT_CONFIRMED"
        assert confirm_res["is_confirmed"] is True
        assert confirm_res["delivery_unlocked"] is True
        assert confirm_res["payment_reference"] == utr_code
        assert confirm_res["verified_by"] == "operator_john"

        # Verify Payment state in DB
        await session.refresh(pmt)
        assert pmt.status == "PAYMENT_CONFIRMED"
        assert pmt.verification_method == "HUMAN_OPERATOR_VERIFICATION"
        assert pmt.verified_by == "operator_john"
        assert pmt.gpay_reference == utr_code
        assert pmt.paid_at is not None

        # Verify Proposal state
        await session.refresh(prop)
        assert prop.status == "ADVANCE_RECEIVED"
        assert prop.advance_received == 600.0
        assert prop.remaining_balance == 600.0
        assert prop.delivery_status == "READY_TO_START"

        # Verify Customer and Project provisioned
        cust = await session.get(Customer, confirm_res["customer_id"])
        assert cust is not None
        assert cust.onboarding_status == "ONBOARDED"

        proj = await session.get(Project, confirm_res["project_id"])
        assert proj is not None
        assert proj.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_confirm_manual_payment_idempotency():
    """Verify that confirming payment twice is strictly idempotent."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            domain=f"gpay-idemp-{uuid.uuid4().hex[:6]}.com",
            name="Prestige Motors",
            niche="Automotive Repair",
            city="Dubai",
            country="AE",
            pipeline_stage=PipelineStage.PROPOSAL.value
        )
        session.add(biz)
        await session.flush()

        prop = await deal_closing_service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Website Turnaround Package",
            total_value=1000.0,
            advance_required=1000.0
        )
        await deal_closing_service.approve_proposal(session, prop.id, operator="operator")
        await deal_closing_service.request_payment_order(session=session, proposal_id=prop.id)

        q_pmt = select(Payment).where(Payment.proposal_id == prop.id)
        pmt = (await session.execute(q_pmt)).scalars().first()

        utr = "SBI_INWARD_9827361928"
        # First confirmation
        res1 = await deal_closing_service.confirm_manual_payment(
            session=session,
            payment_id=pmt.id,
            payment_reference=utr,
            operator="lead_operator"
        )
        assert res1["status"] == "PAYMENT_CONFIRMED"

        # Count projects
        q_proj_cnt = select(func.count(Project.id)).where(Project.customer_id == res1["customer_id"])
        cnt1 = (await session.execute(q_proj_cnt)).scalar()

        # Second confirmation (Duplicate call)
        res2 = await deal_closing_service.confirm_manual_payment(
            session=session,
            payment_id=pmt.id,
            payment_reference=utr,
            operator="lead_operator"
        )
        assert res2["status"] == "ALREADY_CONFIRMED"
        assert res2["is_confirmed"] is True

        # Invariant: No double project created
        cnt2 = (await session.execute(q_proj_cnt)).scalar()
        assert cnt1 == cnt2 == 1


@pytest.mark.asyncio
async def test_confirm_manual_payment_validations():
    """Verify validations: invalid reference and underpayment rejection."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            domain=f"gpay-val-{uuid.uuid4().hex[:6]}.com",
            name="Validation Motors",
            niche="Automotive Repair",
            city="Dubai",
            country="AE",
            pipeline_stage=PipelineStage.PROPOSAL.value
        )
        session.add(biz)
        await session.flush()

        prop = await deal_closing_service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Performance Package",
            total_value=800.0,
            advance_required=800.0
        )
        await deal_closing_service.approve_proposal(session, prop.id, operator="operator")
        await deal_closing_service.request_payment_order(session=session, proposal_id=prop.id)

        q_pmt = select(Payment).where(Payment.proposal_id == prop.id)
        pmt = (await session.execute(q_pmt)).scalars().first()

        # 1. Reject invalid / empty reference
        with pytest.raises(ValueError, match="Invalid transaction reference"):
            await deal_closing_service.confirm_manual_payment(
                session=session,
                payment_id=pmt.id,
                payment_reference="",
                operator="operator"
            )

        # 2. Reject underpayment
        with pytest.raises(ValueError, match="Underpayment rejected"):
            await deal_closing_service.confirm_manual_payment(
                session=session,
                payment_id=pmt.id,
                payment_reference="VALID_UTR_12345",
                operator="operator",
                amount_received=200.0  # expected 800.0
            )


@pytest.mark.asyncio
async def test_payment_api_confirm_and_instructions_endpoints():
    """Verify REST API: GET instructions and POST confirm."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with AsyncSessionLocal() as session:
            biz = Business(
                domain=f"api-gpay-test-{uuid.uuid4().hex[:6]}.com",
                name="Elite Logistics Hub",
                niche="Logistics",
                city="Dubai",
                country="AE",
                pipeline_stage=PipelineStage.PROPOSAL.value
            )
            session.add(biz)
            await session.flush()

            prop = await deal_closing_service.create_proposal(
                session=session,
                business_id=biz.id,
                title="Logistics Workflow Automation",
                total_value=1500.0,
                advance_required=750.0
            )
            await deal_closing_service.approve_proposal(session, prop.id, operator="owner")
            order_res = await deal_closing_service.request_payment_order(session=session, proposal_id=prop.id)

            q_pmt = select(Payment).where(Payment.proposal_id == prop.id)
            pmt = (await session.execute(q_pmt)).scalars().first()
            payment_id = pmt.id

        # 1. GET instructions
        r_inst = await client.get(f"/api/payments/{payment_id}/instructions")
        assert r_inst.status_code == 200
        inst_data = r_inst.json()
        assert inst_data["amount"] == 750.0
        assert "recipient_upi_id" in inst_data
        assert "instructions" in inst_data

        # 2. POST confirm
        r_confirm = await client.post(
            f"/api/payments/{payment_id}/confirm",
            json={
                "payment_reference": "ICICI_REMITTANCE_REF_8819283",
                "operator": "finance_desk",
                "notes": "Wire settled via international partner."
            }
        )
        assert r_confirm.status_code == 200
        conf_data = r_confirm.json()
        assert conf_data["status"] == "PAYMENT_CONFIRMED"
        assert conf_data["is_confirmed"] is True
        assert conf_data["delivery_unlocked"] is True

        # 3. Duplicate POST confirm returns ALREADY_CONFIRMED idempotently
        r_dup = await client.post(
            f"/api/payments/{payment_id}/confirm",
            json={
                "payment_reference": "ICICI_REMITTANCE_REF_8819283",
                "operator": "finance_desk"
            }
        )
        assert r_dup.status_code == 200
        assert r_dup.json()["status"] == "ALREADY_CONFIRMED"
