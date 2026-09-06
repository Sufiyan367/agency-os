import pytest
import asyncio
import uuid
from datetime import datetime
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import (
    Business, Contact, Offer, Proposal, Payment, Customer, Project,
    OutreachMessage, OutreachStatus, PipelineStage, ReplyClassification
)
from app.api.app import app
from app.core.security import create_session_token
from app.core.config import settings
from app.agents.prospect_agent import SingleProspectAgent
from app.outreach.sender import outreach_sender_adapter
from app.crm.reply_classifier import reply_classifier
from app.payments.service import payment_service


@pytest.mark.asyncio
async def test_prospect_agent_prioritizes_contactable_leads():
    """Verifies that SingleProspectAgent prioritizes leads with verified public emails."""
    await init_db()
    uid = uuid.uuid4().hex[:6]

    async with AsyncSessionLocal() as session:
        # Lead A: No email
        biz_no_email = Business(
            name=f"No Email Biz {uid}",
            domain=f"noemail-{uid}.com",
            website_url=f"https://noemail-{uid}.com",
            country="US",
            city="Dallas",
            niche="roofing",
            public_email=None,
            pipeline_stage=PipelineStage.AUDITED.value
        )
        # Lead B: Has verified public email
        biz_with_email = Business(
            name=f"With Email Biz {uid}",
            domain=f"withemail-{uid}.com",
            website_url=f"https://withemail-{uid}.com",
            country="US",
            city="Dallas",
            niche="roofing",
            public_email=f"owner@{uid}.com",
            pipeline_stage=PipelineStage.AUDITED.value
        )
        session.add_all([biz_no_email, biz_with_email])
        await session.commit()

        agent = SingleProspectAgent(provider_type="mock")
        cand = await agent.get_next_uncontacted_prospect(session)
        assert cand is not None
        # Candidate with verified public email must be selected first
        assert cand.public_email is not None


@pytest.mark.asyncio
async def test_controlled_live_send_safety_validation():
    """Verifies force_live=True checks credentials cleanly and force_live=False runs safely simulated."""
    await init_db()
    uid = uuid.uuid4().hex[:6]

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Live Send Biz {uid}",
            domain=f"livesend-{uid}.com",
            country="US",
            city="Austin",
            niche="roofing",
            public_email=f"ceo@{uid}.com",
            pipeline_stage=PipelineStage.OUTREACH_READY.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject="Test live send safety",
            body="Hello, this is a test.",
            variant_name="Value-First Insight",
            status=OutreachStatus.APPROVED.value,
            confidence=0.95
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)

        # 1. Default send (force_live=False) succeeds in simulated dry-run mode
        res_dry = await outreach_sender_adapter.send_approved_message(session, msg.id, force_live=False)
        assert res_dry["event"] == "dry_run_simulated"
        assert msg.status == OutreachStatus.SENT.value

        # 2. Attempting to force live with unconfigured credentials raises clean ValueError
        msg2 = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject="Test live send unconfigured",
            body="Hello, this is another test.",
            variant_name="Value-First Insight",
            status=OutreachStatus.APPROVED.value,
            confidence=0.95
        )
        session.add(msg2)
        await session.commit()
        await session.refresh(msg2)

        with patch.object(settings, "RESEND_API_KEY", None), \
             patch.object(settings, "SMTP_HOST", None):
            with pytest.raises(ValueError) as exc:
                await outreach_sender_adapter.send_approved_message(session, msg2.id, force_live=True)
            assert "Cannot send live" in str(exc.value)


@pytest.mark.asyncio
async def test_autonomous_proposal_and_payment_link_on_interested_reply():
    """Verifies that an inbound commercial reply autonomously creates a Proposal (>= $500) and payment link."""
    await init_db()
    uid = uuid.uuid4().hex[:6]

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Commercial Prospect {uid}",
            domain=f"commercial-{uid}.com",
            country="US",
            city="Austin",
            niche="roofing",
            public_email=f"owner@commercial-{uid}.com",
            pipeline_stage=PipelineStage.CONTACTED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Provide commercial offer >= $500
        offer = Offer(
            business_id=biz.id,
            service_type="web_performance",
            title="Mobile Conversion & Inquiry Acceleration",
            recommended_price=650.0,
            estimated_delivery_days=5,
            deliverables=["Above-fold CTA", "Click-to-call dialer"]
        )
        session.add(offer)
        await session.commit()

        # Inbound reply inquiring about price
        raw_reply = "Thanks for your email regarding our mobile site. How much does this turnaround package cost?"
        reply = await reply_classifier.process_incoming_reply(
            session=session,
            business_id=biz.id,
            sender_email=biz.public_email,
            raw_body=raw_reply
        )

        assert reply.classification in (ReplyClassification.PRICE_REQUEST.value, ReplyClassification.QUESTION.value, ReplyClassification.INTERESTED.value)
        assert biz.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value

        # Verify autonomous Proposal creation >= $500
        q_prop = select(Proposal).where(Proposal.business_id == biz.id)
        prop = (await session.execute(q_prop)).scalars().first()
        assert prop is not None
        assert prop.total_value >= 500.0
        assert prop.total_value == 650.0
        assert prop.advance_required == 260.0  # 40% of 650
        assert prop.status in ("DRAFT", "PENDING_APPROVAL")

        # Verify suggested response contains payment link and investment details
        assert "$650" in reply.suggested_response
        assert "$260" in reply.suggested_response
        assert ("checkout" in reply.suggested_response or "rzp.io" in reply.suggested_response)


@pytest.mark.asyncio
async def test_send_proposal_to_client_endpoint():
    """Tests the owner single-click proposal & payment link dispatch API endpoint."""
    await init_db()
    uid = uuid.uuid4().hex[:6]

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Proposal Client {uid}",
            domain=f"propclient-{uid}.com",
            country="US",
            city="Houston",
            niche="roofing",
            public_email=f"contact@propclient-{uid}.com",
            pipeline_stage=PipelineStage.QUALIFIED_REPLY.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        prop = Proposal(
            business_id=biz.id,
            title="Mobile Conversion Remediation",
            service_type="Conversion Optimization",
            total_value=650.0,
            advance_required=260.0,
            status="DRAFT",
            is_mock=True
        )
        session.add(prop)
        await session.commit()
        await session.refresh(prop)
        prop_id = prop.id

    token = create_session_token("admin", role="admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("agency_session", token)

        # Dispatch proposal to client (dry-run mode)
        resp = await client.post(
            f"/api/proposals/{prop_id}/send-to-client",
            json={"send_live": False}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SENT"
        assert data["recipient"] == f"contact@propclient-{uid}.com"
        assert "checkout_url" in data
        assert data["send_result"]["event"] == "dry_run_simulated"

    # Verify stage advanced to PROPOSAL
    async with AsyncSessionLocal() as verify_session:
        updated_biz = await verify_session.get(Business, biz.id)
        assert updated_biz.pipeline_stage == PipelineStage.PROPOSAL.value


@pytest.mark.asyncio
async def test_payment_idempotency_and_won_transition():
    """Verifies that verifying payment advances the lead to WON and creates onboarding artifacts idempotently."""
    await init_db()
    uid = uuid.uuid4().hex[:6]

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Paid Client {uid}",
            domain=f"paidclient-{uid}.com",
            country="US",
            city="Austin",
            niche="roofing",
            public_email=f"finance@paidclient-{uid}.com",
            pipeline_stage=PipelineStage.PROPOSAL.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        offer = Offer(
            business_id=biz.id,
            service_type="web_performance",
            title="Complete Web Turnaround",
            recommended_price=750.0,
            estimated_delivery_days=7,
            deliverables=["Core Web Vitals", "Schema Injection"]
        )
        session.add(offer)
        await session.commit()

        ref_id = f"pay_real_{uid}"

        # 1. First confirmation
        res1 = await payment_service.confirm_payment_and_onboard(
            session=session,
            business_id=biz.id,
            amount_usd=750.0,
            reference_id=ref_id,
            payer_email=biz.public_email
        )
        assert res1["status"] == "SUCCESS"
        assert res1["amount_paid"] == 750.0
        assert biz.pipeline_stage == PipelineStage.WON.value

        # Verify Customer & Project provisioned
        q_cust = select(Customer).where(Customer.business_id == biz.id)
        cust = (await session.execute(q_cust)).scalars().first()
        assert cust is not None
        assert cust.contract_amount == 750.0

        q_proj = select(Project).where(Project.customer_id == cust.id)
        proj = (await session.execute(q_proj)).scalars().first()
        assert proj is not None
        assert proj.status == "IN_PROGRESS"
        assert len(proj.tasks) == 2

        # 2. Duplicate payment event (Idempotency test)
        res2 = await payment_service.confirm_payment_and_onboard(
            session=session,
            business_id=biz.id,
            amount_usd=750.0,
            reference_id=ref_id,
            payer_email=biz.public_email
        )
        assert res2["status"] == "ALREADY_PROCESSED"
        assert res2["customer_id"] == cust.id


@pytest.mark.asyncio
async def test_decoupled_email_provider_resolution():
    """Verifies that EMAIL_DRY_RUN=False activates live provider even when global DRY_RUN=True."""
    from app.outreach.providers.factory import get_email_provider
    from app.outreach.providers.resend_provider import ResendEmailProvider
    from app.outreach.providers.dry_run import DryRunEmailProvider

    orig_email_dry = settings.EMAIL_DRY_RUN
    orig_dry = settings.DRY_RUN
    orig_provider = settings.EMAIL_PROVIDER
    orig_key = settings.RESEND_API_KEY

    try:
        settings.DRY_RUN = True
        settings.EMAIL_DRY_RUN = False
        settings.EMAIL_PROVIDER = "resend"
        settings.RESEND_API_KEY = "re_test_dummy_key"

        provider = get_email_provider()
        assert isinstance(provider, ResendEmailProvider), "EMAIL_DRY_RUN=False should resolve Resend despite DRY_RUN=True"

        # Toggling back to True returns DryRun
        settings.EMAIL_DRY_RUN = True
        provider_dry = get_email_provider()
        assert isinstance(provider_dry, DryRunEmailProvider)
    finally:
        settings.EMAIL_DRY_RUN = orig_email_dry
        settings.DRY_RUN = orig_dry
        settings.EMAIL_PROVIDER = orig_provider
        settings.RESEND_API_KEY = orig_key


@pytest.mark.asyncio
async def test_decoupled_payment_provider_enablement():
    """Verifies that PAYMENT_DRY_RUN=False activates live payment gateways even when global DRY_RUN=True."""
    from app.payments.razorpay import RazorpayPaymentProvider
    from app.payments.provider import StripePaymentProvider

    orig_dry = settings.DRY_RUN
    orig_pay_dry = settings.PAYMENT_DRY_RUN
    orig_pay_enabled = settings.PAYMENTS_ENABLED
    orig_provider = settings.PAYMENT_PROVIDER

    try:
        settings.DRY_RUN = True
        settings.PAYMENT_DRY_RUN = False
        settings.PAYMENTS_ENABLED = True
        settings.PAYMENT_PROVIDER = "razorpay"

        rzp = RazorpayPaymentProvider(key_id="rzp_test_123", key_secret="sec_123")
        assert rzp.enabled is True, "PAYMENT_DRY_RUN=False should enable Razorpay despite DRY_RUN=True"

        settings.PAYMENT_PROVIDER = "stripe"
        stripe = StripePaymentProvider(secret_key="sk_test_123")
        assert stripe.enabled is True, "PAYMENT_DRY_RUN=False should enable Stripe despite DRY_RUN=True"

        # Toggling back to True disables live calls
        settings.PAYMENT_DRY_RUN = True
        rzp_dry = RazorpayPaymentProvider(key_id="rzp_test_123", key_secret="sec_123")
        assert rzp_dry.enabled is False
    finally:
        settings.DRY_RUN = orig_dry
        settings.PAYMENT_DRY_RUN = orig_pay_dry
        settings.PAYMENTS_ENABLED = orig_pay_enabled
        settings.PAYMENT_PROVIDER = orig_provider


@pytest.mark.asyncio
async def test_cli_approve_supports_live_flag():
    """Verifies that the CLI approve command supports --live flag and forwards force_live."""
    from typer.testing import CliRunner
    from app.cli import cli_app
    from app.database.models import OutreachMessage, OutreachStatus

    runner = CliRunner()
    await init_db()
    uid = uuid.uuid4().hex[:6]

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"CLI Lead {uid}",
            domain=f"clilead-{uid}.com",
            country="US",
            city="Dallas",
            niche="roofing",
            public_email=f"ceo@clilead-{uid}.com",
            pipeline_stage=PipelineStage.APPROVAL.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        msg1 = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject="Website Audit Observations",
            body="Hello, we noticed an issue on your website.",
            status=OutreachStatus.PENDING_APPROVAL.value
        )
        session.add(msg1)

        msg2 = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject="Website Audit Observations Part 2",
            body="Hello, we noticed another issue on your website.",
            status=OutreachStatus.PENDING_APPROVAL.value
        )
        session.add(msg2)

        await session.commit()
        await session.refresh(msg1)
        await session.refresh(msg2)
        msg_id_1 = msg1.id
        msg_id_2 = msg2.id

    # Test approve without --live (defaults to simulated) running in separate thread
    res_dry = await asyncio.to_thread(runner.invoke, cli_app, ["approve", str(msg_id_1)])
    assert res_dry.exit_code == 0
    assert "APPROVED" in res_dry.output
    assert "SIMULATED" in res_dry.output

    # Test approve with --live
    res_live = await asyncio.to_thread(runner.invoke, cli_app, ["approve", str(msg_id_2), "--live"])
    assert res_live.exit_code == 0
    assert "APPROVED" in res_live.output
    assert "LIVE DISPATCH" in res_live.output




@pytest.mark.asyncio
async def test_discovery_deduplication_stores_new_businesses():
    """Verifies that lead discovery excludes pre-existing businesses and persists authentic new businesses."""
    from app.lead_generation.discovery import lead_discovery_coordinator
    from app.database.models import VerificationStatus

    await init_db()
    uid = uuid.uuid4().hex[:6]
    test_dom = f"existingroofingcorp-{uid}.com"

    async with AsyncSessionLocal() as session:
        # Pre-seed one business to simulate prior discovery
        pre_biz = Business(
            name="Existing Roofing Corp",
            domain=test_dom,
            country="US",
            city="Austin",
            niche="roofing-contractors",
            public_email=f"info@{test_dom}",
            pipeline_stage=PipelineStage.DISCOVERED.value
        )
        session.add(pre_biz)
        await session.commit()

        # Run discovery for target=2
        discovered = await lead_discovery_coordinator.run_discovery_and_verification(
            session=session,
            country_code="US",
            niche_slug="roofing-contractors",
            target=2
        )
        assert len(discovered) >= 1
        discovered_domains = {b.domain for b in discovered}
        assert "existingroofingcorp-test.com" not in discovered_domains
        for b in discovered:
            assert b.id is not None
            assert b.verification_status in (VerificationStatus.VERIFIED.value, VerificationStatus.REJECTED.value)


@pytest.mark.asyncio
async def test_llm_client_fallback_on_unauthorized_and_not_found():
    """Verifies that LLMClient catches API failures (e.g. 401/404) and falls back to deterministic heuristic generation."""
    from app.core.llm import llm_client

    orig_provider = llm_client.provider
    orig_key = llm_client.openai_key

    try:
        # Set invalid key that triggers fallback
        llm_client.provider = "openai"
        llm_client.openai_key = "sk-invalid-mock-key-testing-401"

        # Should NOT raise an unhandled exception, but return clean heuristic fallback
        text_out = await llm_client.generate_text("Draft a high-conversion cold outreach email")
        assert len(text_out) > 30
        assert "Elena Vance" in text_out or "Hi there" in text_out

        json_out = await llm_client.generate_json("Classify this prospect reply: Yes, send pricing details.")
        assert isinstance(json_out, dict)
        assert "classification" in json_out or "status" in json_out
    finally:
        llm_client.provider = orig_provider
        llm_client.openai_key = orig_key

