"""
Tests for Phase 19: Acquisition Pipeline Router, Demo Factory, Automated QA,
Mock Reply Processing, CEO Notification, and Payment Handoff.
"""
import pytest
import uuid
import os
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, AuditFinding, Offer, LeadScore, OutreachMessage,
    OutreachStatus, PipelineStage, PipelineEvent, Proposal, ActiveOutreachLock,
    Artifact, Reply
)
from app.delivery.requirements_engine import requirements_engine, RequirementsPacket
from app.delivery.demo_factory import demo_factory, DemoGenerationResult
from app.delivery.demo_qa import demo_qa_engine, DemoQAResult
from app.orchestrator.pipeline_router import pipeline_router, PaymentHandoffObject, PipelineExecutionSummary
from app.crm.inbox_poller import inbox_poller
from app.crm.reply_classifier import reply_classifier, ReplyClassification
from app.scoring.engine import LeadScoringEngine
from app.core.config import settings


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()


async def create_homeiq_fixture(session: AsyncSession) -> Business:
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name=f"HomeIQ UAE {uid}",
        domain=f"homeiq-{uid}.ae",
        country="AE",
        city="Dubai",
        niche="plumbing-services",
        public_email=f"info@homeiq-{uid}.ae",
        email_status="verified",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    session.add(biz)
    await session.flush()

    audit = AuditRun(
        business_id=biz.id,
        url_audited=f"https://{biz.domain}/",
        performance_score=50.0,
        seo_score=100.0,
        a11y_score=76.0,
        ux_conversion_score=90.0,
        security_score=100.0,
        content_score=90.0,
        overall_health_score=80.9,
        summary="Diagnostic baseline: High overall health but delayed TTFB and un-deferred scripts."
    )
    session.add(audit)
    await session.flush()

    f1 = AuditFinding(
        audit_id=audit.id,
        category="Performance",
        finding="Excessive Server Response Time / TTFB",
        severity="HIGH",
        evidence="Initial response latency exceeded 1,200ms threshold.",
        url=f"https://{biz.domain}/",
        recommended_fix="Deploy edge CDN caching and static asset compression.",
        estimated_business_impact="Slow initial response causes visitor bounce on mobile networks."
    )
    f2 = AuditFinding(
        audit_id=audit.id,
        category="Performance",
        finding="Render-Blocking JavaScript Resources",
        severity="HIGH",
        evidence="Found external scripts loaded without defer or async.",
        url=f"https://{biz.domain}/",
        recommended_fix="Add defer or async attribute to non-critical scripts.",
        estimated_business_impact="Delays document rendering and increases total blocking time."
    )
    session.add_all([f1, f2])
    await session.flush()

    offer = Offer(
        business_id=biz.id,
        title="Core Web Vitals & Load Speed Acceleration",
        service_type="Speed Optimization",
        recommended_price=650.0,
        estimated_delivery_days=5,
        deliverables=[
            "Edge CDN caching configuration",
            "Asynchronous script loader deployment",
            "Next-gen WebP/AVIF image format conversion"
        ]
    )
    session.add(offer)
    await session.commit()
    await session.refresh(biz)
    return biz


@pytest.mark.asyncio
async def test_requirements_engine_packet_synthesis():
    """Validates deterministic synthesis of requirements packet from empirical audit data."""
    async with AsyncSessionLocal() as session:
        biz = await create_homeiq_fixture(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)

        assert packet.business_name == biz.name
        assert packet.domain == biz.domain
        assert packet.contact_email == biz.public_email
        assert packet.service_title == "Core Web Vitals & Load Speed Acceleration"
        assert packet.catalog_price_usd == 650.0
        assert packet.advance_amount_usd == 260.0  # 40%
        assert packet.turnaround_days == 5
        assert len(packet.requirements) == 2
        assert len(packet.deliverables) >= 3
        assert len(packet.architectural_constraints) >= 4


@pytest.mark.asyncio
async def test_demo_factory_deterministic_generation():
    """Validates that DemoFactory generates tangible HTML/JSON artifacts without external paid AI."""
    async with AsyncSessionLocal() as session:
        biz = await create_homeiq_fixture(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)

        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)

        assert demo_res.success is True
        assert demo_res.demo_id.startswith(f"DEMO-{biz.id}-")
        assert os.path.exists(demo_res.metadata.html_file_path)
        assert os.path.exists(demo_res.metadata.json_spec_path)
        assert demo_res.artifact_id is not None

        # Verify HTML content
        assert biz.domain in demo_res.html_content
        assert "$650.00" in demo_res.html_content
        assert "Core Web Vitals & Load Speed Acceleration" in demo_res.html_content


@pytest.mark.asyncio
async def test_demo_qa_engine_validation():
    """Validates that DemoQAEngine validates all 7 deterministic quality gates."""
    async with AsyncSessionLocal() as session:
        biz = await create_homeiq_fixture(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)

        qa_res = demo_qa_engine.validate_demo(demo_res, packet)

        assert qa_res.overall_passed is True
        assert qa_res.total_checks == 8
        assert qa_res.passed_checks == 8
        assert qa_res.failed_checks == 0
        assert qa_res.qa_signature.startswith("QA-PASS-")


@pytest.mark.asyncio
async def test_demo_qa_engine_catches_flaws():
    """Validates that DemoQAEngine catches injected template placeholders."""
    async with AsyncSessionLocal() as session:
        biz = await create_homeiq_fixture(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)

        # Inject flawed HTML with placeholders
        demo_res.html_content += "\n<div>{{TODO_INJECTED_PLACEHOLDER}}</div>"
        qa_res = demo_qa_engine.validate_demo(demo_res, packet)

        assert qa_res.overall_passed is False
        assert qa_res.failed_checks >= 1
        assert any(c.name == "ZERO_PLACEHOLDERS" and not c.passed for c in qa_res.checks)


@pytest.mark.asyncio
async def test_mock_reply_ingestion_and_state_advancement():
    """Validates that a mock positive reply advances pipeline to QUALIFIED_REPLY and cancels follow-ups."""
    async with AsyncSessionLocal() as session:
        biz = await create_homeiq_fixture(session)

        # Create simulated sent outreach message
        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject="Technical note on homeiq.ae",
            body="Hello, we noticed speed opportunities...",
            status=OutreachStatus.SENT.value
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)

        # Process mock reply through existing InboxPoller
        reply = await inbox_poller.process_inbound_message(
            session=session,
            sender_email=biz.public_email,
            subject=f"Re: {msg.subject}",
            body="We are interested in this speed turnaround demo. Please send over the breakdown.",
            in_reply_to=f"<msg_{msg.id}@agency.local>"
        )

        assert reply is not None
        assert reply.classification == ReplyClassification.INTERESTED.value

        # Refresh business stage
        await session.refresh(biz)
        assert biz.pipeline_stage in (PipelineStage.QUALIFIED_REPLY.value, PipelineStage.PROPOSAL.value)


@pytest.mark.asyncio
async def test_proposal_and_payment_handoff_structure():
    """Validates the provider-independent payment handoff object with payments safely disabled."""
    async with AsyncSessionLocal() as session:
        biz = await create_homeiq_fixture(session)
        summary = await pipeline_router.execute_full_cycle(session, biz.id)

        handoff = summary.payment_handoff
        assert handoff is not None
        assert handoff.business_id == biz.id
        assert handoff.catalog_price_usd == 650.0
        assert handoff.advance_required_usd == 260.0
        assert handoff.payments_enabled is False
        assert handoff.payment_provider == "dry_run"
        assert handoff.payment_status == "PENDING_AUTHORIZATION"
        assert handoff.approval_requirements == "HUMAN_APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_scoring_investigation_relationship():
    """
    Formally asserts the conceptual and mathematical relationship between
    prospect_score (deficiency), P(Win) (win probability), and EV (monetary expected value).
    """
    # 1. EV = P(Win) * Price
    p_win = 0.762
    price = 650.0
    ev = round(p_win * price, 2)
    assert ev == 495.30

    # 2. prospect_score represents deficiency / need for improvement (0-100)
    # A site with 80.9 health has a low deficiency (23.2)
    # A site with 40.0 health has a higher deficiency (e.g. >50)
    scoring_engine = LeadScoringEngine()

    class MockAuditRun:
        performance_score = 50.0
        seo_score = 100.0
        a11y_score = 76.0
        ux_conversion_score = 90.0
        overall_health_score = 80.9

    class MockCountry:
        name = "United Arab Emirates"
        gdp_per_capita = 53000.0

    class MockNiche:
        name = "Plumbing Services"
        avg_deal_size = 700.0

    class MockBiz:
        public_email = "info@homeiq.ae"
        email_status = "verified"
        phone = None

    score, priority, breakdown, rationale = scoring_engine.calculate_score(
        MockBiz(), MockAuditRun(), MockCountry(), MockNiche()
    )
    assert score == 23.2
    assert breakdown["performance_opp"] == 50.0
    assert breakdown["seo_opp"] == 0.0  # Perfect SEO = 0 opportunity/deficit


@pytest.mark.asyncio
async def test_full_15_stage_acquisition_cycle_homeiq():
    """
    Validates that HomeIQ UAE executes through all 15 stages of the acquisition lifecycle:
    DISCOVERY -> QUALIFICATION -> PERSONALIZATION -> OUTREACH_READY -> HUMAN_APPROVAL_REQUIRED
    -> DRY_RUN_OUTREACH -> MOCK_REPLY -> REPLY_CLASSIFIED -> INTERESTED -> CEO_NOTIFICATION
    -> REQUIREMENTS -> DEMO_GENERATION -> DEMO_QA -> PROPOSAL_READY -> PAYMENT_HANDOFF
    with ZERO real email transmissions and ZERO live payments.
    """
    async with AsyncSessionLocal() as session:
        biz = await create_homeiq_fixture(session)

        summary = await pipeline_router.execute_full_cycle(
            session=session,
            business_id=biz.id,
            mock_reply_body="Hi, we received your technical note. We are interested and would love to see the speed turnaround demo for homeiq.ae. What are the next steps?"
        )

        expected_stages = [
            "DISCOVERY",
            "QUALIFICATION",
            "PERSONALIZATION",
            "OUTREACH_READY",
            "HUMAN_APPROVAL_REQUIRED",
            "DRY_RUN_OUTREACH",
            "MOCK_REPLY",
            "REPLY_CLASSIFIED",
            "INTERESTED",
            "CEO_NOTIFICATION",
            "REQUIREMENTS",
            "DEMO_GENERATION",
            "DEMO_QA",
            "PROPOSAL_READY",
            "PAYMENT_HANDOFF"
        ]

        assert summary.stages_completed == expected_stages
        assert summary.qa_passed is True
        assert summary.zero_emails_transmitted is True
        assert summary.zero_payments_executed is True
        assert summary.payment_handoff.catalog_price_usd == 650.0
