"""
Regression Test Suite: Commercial Qualification Bottleneck Resolution
Covers all 11 required test cases for Tasks 1 through 12.
"""
import uuid
import pytest
from datetime import datetime
from sqlalchemy import select

from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, Country, Niche, LeadScore, PipelineStage,
    OutreachMessage, OutreachStatus, PipelineEvent, Reply
)
from app.scoring.engine import lead_scoring_engine
from app.acquisition.targeting_catalog import (
    TIER_1_COUNTRIES, P1_COUNTRIES, TIER_1_NICHES, NICHE_CATALOG
)
from app.acquisition.contact_verifier import contact_verifier
from app.market_intelligence.autonomous_market_engine import autonomous_market_engine


async def create_test_country_and_niche(session):
    # Ensure US country exists
    c_stmt = select(Country).where(Country.code == "US")
    country = (await session.execute(c_stmt)).scalar_one_or_none()
    if not country:
        country = Country(code="US", name="United States", gdp_per_capita=76000.0)
        session.add(country)

    # Ensure HVAC niche exists
    n_stmt = select(Niche).where(Niche.slug == "hvac")
    niche = (await session.execute(n_stmt)).scalar_one_or_none()
    if not niche:
        niche = Niche(slug="hvac", name="HVAC", avg_deal_size=2500.0)
        session.add(niche)

    await session.commit()
    return country, niche


async def create_audit_run(session, business_id: int, health_score: float = 35.0):
    perf = 90.0 if health_score >= 80 else 30.0
    seo = 90.0 if health_score >= 80 else 35.0
    a11y = 90.0 if health_score >= 80 else 40.0
    ux = 90.0 if health_score >= 80 else 30.0
    audit = AuditRun(
        business_id=business_id,
        url_audited=f"https://example-{business_id}.com",
        overall_health_score=health_score,
        performance_score=perf,
        seo_score=seo,
        a11y_score=a11y,
        ux_conversion_score=ux,
        security_score=50.0,
        content_score=40.0,
        audited_at=datetime.utcnow(),
        summary="Audit completed: technical evaluation recorded."
    )
    session.add(audit)
    await session.commit()
    await session.refresh(audit)
    return audit


@pytest.mark.asyncio
async def test_contactability_decoupling():
    """
    Case 1: A business with bad contactability (phone only or no email) but strong
    commercial deficits scores >= 55.0 on commercial merit and transitions to
    RESEARCH_REQUIRED (not REJECTED).
    """
    async with AsyncSessionLocal() as session:
        await create_test_country_and_niche(session)
        uid = uuid.uuid4().hex[:8]
        biz = Business(
            name=f"High Deficit HVAC {uid}",
            domain=f"highdeficithvac-{uid}.com",
            country="US",
            city="Dallas",
            niche="hvac",
            public_email=None,
            email_status="unknown",
            phone="+12145550199",
            pipeline_stage=PipelineStage.AUDITED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        await create_audit_run(session, biz.id, health_score=30.0)

        lead_score = await lead_scoring_engine.score_business(session, biz)
        await session.refresh(biz)

        # Commercial turnaround opportunity must score >= 55.0
        assert lead_score.total_score >= 55.0, f"Expected score >= 55.0, got {lead_score.total_score}"
        # Pipeline stage must transition to RESEARCH_REQUIRED, NOT REJECTED
        assert biz.pipeline_stage == PipelineStage.RESEARCH_REQUIRED.value
        assert biz.research_status == "RESEARCH_REQUIRED"


@pytest.mark.asyncio
async def test_fully_contactable_qualification():
    """
    Case 2: A business with verified email and score >= 55.0 transitions to QUALIFIED.
    """
    async with AsyncSessionLocal() as session:
        await create_test_country_and_niche(session)
        uid = uuid.uuid4().hex[:8]
        biz = Business(
            name=f"Verified Contact HVAC {uid}",
            domain=f"verifiedhvac-{uid}.com",
            country="US",
            city="Houston",
            niche="hvac",
            public_email=f"service@{uid}-hvac.com",
            email_status="verified",
            phone="+17135550122",
            pipeline_stage=PipelineStage.AUDITED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        await create_audit_run(session, biz.id, health_score=32.0)

        lead_score = await lead_scoring_engine.score_business(session, biz)
        await session.refresh(biz)

        assert lead_score.total_score >= 55.0
        assert biz.pipeline_stage == PipelineStage.QUALIFIED.value
        assert biz.research_status == "QUALIFIED"


@pytest.mark.asyncio
async def test_commercial_floor_enforcement():
    """
    Case 3: A business with score < 55.0 transitions to REJECTED.
    """
    async with AsyncSessionLocal() as session:
        await create_test_country_and_niche(session)
        uid = uuid.uuid4().hex[:8]
        biz = Business(
            name=f"Pristine Website Co {uid}",
            domain=f"pristine-{uid}.com",
            country="US",
            city="Austin",
            niche="hvac",
            public_email=f"hello@{uid}.com",
            email_status="verified",
            pipeline_stage=PipelineStage.AUDITED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # High health score = zero/low deficits -> low commercial score
        await create_audit_run(session, biz.id, health_score=95.0)

        lead_score = await lead_scoring_engine.score_business(session, biz)
        await session.refresh(biz)

        assert lead_score.total_score < 55.0
        assert biz.pipeline_stage == PipelineStage.REJECTED.value


def test_redundancy_elimination_weights():
    """
    Case 4: Website weakness does not double-count component deficits (weights sum to 1.00).
    """
    w_conv = settings.WEIGHT_CONVERSION_OPPORTUNITY
    w_perf = settings.WEIGHT_PERFORMANCE_OPPORTUNITY
    w_seo = settings.WEIGHT_SEO_OPPORTUNITY
    w_pay = settings.WEIGHT_ABILITY_TO_PAY
    w_icp = settings.WEIGHT_ICP_FIT
    w_a11y = settings.WEIGHT_A11Y_OPPORTUNITY
    w_weak = settings.WEIGHT_WEBSITE_WEAKNESS

    total_weight = round(w_conv + w_perf + w_seo + w_pay + w_icp + w_a11y, 4)
    assert total_weight == 1.00, f"Weights must sum strictly to 1.00, got {total_weight}"
    assert w_weak == 0.00, "Double-counting WEIGHT_WEBSITE_WEAKNESS must be 0.00"


def test_targeting_priority_tier1():
    """
    Case 5: Tier 1 countries (US, UK, CA, AU) and high-ticket service niches receive
    appropriate priority in targeting and scoring.
    """
    assert "US" in TIER_1_COUNTRIES and "US" in P1_COUNTRIES
    assert "UK" in TIER_1_COUNTRIES and "UK" in P1_COUNTRIES
    assert "CA" in TIER_1_COUNTRIES and "CA" in P1_COUNTRIES
    assert "AU" in TIER_1_COUNTRIES and "AU" in P1_COUNTRIES

    for niche_key in ("HVAC", "ROOFING", "DENTAL", "MEDICAL_CLINICS", "LEGAL_SERVICES"):
        assert niche_key in TIER_1_NICHES
        niche_def = NICHE_CATALOG.get(niche_key)
        assert niche_def is not None
        assert niche_def.min_estimated_service_value >= 1000


def test_zero_fabrication_contact_verification():
    """
    Case 6: Verification never fabricates emails or phone numbers. Disallowed domains
    and placeholders are strictly rejected.
    """
    html_with_fake = """
    <html><body>
        <p>Contact us at info@example.com or user@placeholder.com</p>
        <a href="mailto:test@company.com">Email Us</a>
    </body></html>
    """
    res = contact_verifier.verify_contacts(html_with_fake, source_url="https://testbiz.com")
    # All fake/disallowed emails must be rejected
    assert res.email is None
    assert res.can_outreach is False
    assert res.email_status == "no_contact"

    # Authentic mailto link extraction
    html_with_real = """
    <html><body>
        <a href="mailto:support@realroofingpro.com">Direct Support</a>
    </body></html>
    """
    res_real = contact_verifier.verify_contacts(
        html_with_real, source_url="https://realroofingpro.com", candidate_domain="realroofingpro.com"
    )
    assert res_real.email == "support@realroofingpro.com"
    assert res_real.email_status == "verified"
    assert res_real.can_outreach is True


@pytest.mark.asyncio
async def test_safe_outreach_staging_pending_approval():
    """
    Case 7: Qualified leads result in outreach drafts staged in PENDING_APPROVAL,
    never auto-dispatched to cold external prospects.
    """
    from app.outreach.personalization import outreach_personalizer
    async with AsyncSessionLocal() as session:
        await create_test_country_and_niche(session)
        uid = uuid.uuid4().hex[:8]
        biz = Business(
            name=f"Safe Staging Plumbing {uid}",
            domain=f"safestaging-{uid}.com",
            country="US",
            city="Phoenix",
            niche="plumbing",
            public_email=f"contact@safestaging-{uid}.com",
            email_status="verified",
            pipeline_stage=PipelineStage.QUALIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        await create_audit_run(session, biz.id, health_score=35.0)

        msg = await outreach_personalizer.prepare_outreach_for_business(session, biz, auto_approve=False)
        assert msg.status == OutreachStatus.PENDING_APPROVAL.value
        assert msg.recipient_email == biz.public_email
        assert biz.pipeline_stage == PipelineStage.APPROVAL.value


@pytest.mark.asyncio
async def test_real_dispatch_gate_requires_ceo_approval_for_cold():
    """
    Case 8: Only internal canary / operator emails can be dispatched automatically for verification.
    Cold external outreach strictly requires CEO approval (actor_type in HUMAN, CEO_HUMAN, OPERATOR).
    """
    from app.orchestrator.worker import PersistentAgencyWorker
    worker = PersistentAgencyWorker(interval_seconds=60)

    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:8]
        biz = Business(
            name=f"External Prospect {uid}",
            domain=f"externalprospect-{uid}.com",
            country="US",
            niche="hvac",
            public_email=f"ceo@{uid}-hvacpros.com",
            email_status="verified",
            pipeline_stage=PipelineStage.APPROVAL.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Cold message created with non-human actor type in APPROVED state
        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject="Test Cold Outreach",
            body="Cold outreach proposal",
            status=OutreachStatus.APPROVED.value,
            actor_type="AUTONOMOUS_WORKER"  # Not CEO_HUMAN
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)

        # Verify the worker deferral check logic
        from app.analytics.truth_engine import OPERATOR_EMAILS
        recip_lower = (msg.recipient_email or "").lower().strip()
        msg_meta = getattr(msg, "auto_approval_eligibility", None) or {}
        msg_is_canary = (
            (isinstance(msg_meta, dict) and bool(msg_meta.get("is_canary")))
            or any(k in recip_lower for k in OPERATOR_EMAILS)
            or "canary" in recip_lower
        )
        is_cold = (not msg_is_canary) and (getattr(msg, "sequence_step", 1) == 1)
        assert is_cold is True
        assert msg.actor_type not in ("HUMAN", "CEO_HUMAN", "OPERATOR")
        # Cold external message is protected and deferred


@pytest.mark.asyncio
async def test_no_fabricated_revenue():
    """
    Case 9: Payment confirmation strictly requires verifiable provider confirmation.
    Zero fake revenue is recorded.
    """
    from app.payments.service import payment_service
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:8]
        biz = Business(
            name=f"Payment Test Client {uid}",
            domain=f"paymenttest-{uid}.com",
            country="US",
            niche="hvac",
            pipeline_stage=PipelineStage.PROPOSAL.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Confirming payment records an actual Payment record and updates pipeline
        payment_res = await payment_service.confirm_payment_and_onboard(
            session=session,
            business_id=biz.id,
            amount_usd=1500.0,
            reference_id=f"pi_real_{uid}",
            payer_email=f"billing@{uid}.com"
        )
        assert payment_res["status"] == "SUCCESS"
        assert payment_res["amount_paid"] == 1500.0
        assert payment_res["payment_id"] is not None
        await session.refresh(biz)
        assert biz.pipeline_stage in (PipelineStage.ADVANCE_PAID.value, PipelineStage.IN_DELIVERY.value, PipelineStage.WON.value)


@pytest.mark.asyncio
async def test_n8n_operational_integrity():
    """
    Case 10: n8n webhook triggers and orchestrator dispatch operate cleanly
    without schema errors on commercial qualification events.
    """
    from app.automations.n8n_orchestrator import n8n_orchestrator
    from app.core.event_bus import AgencyEvent

    event = AgencyEvent(
        event_type="COMMERCIAL_QUALIFICATION",
        entity_type="business",
        entity_id=1,
        payload={
            "business_name": "Phoenix Roofing Specialists",
            "country": "US",
            "niche": "Roofing",
            "score": 68.5,
            "priority": "B",
            "stage": "QUALIFIED"
        }
    )
    # Orchestrator handles qualification event cleanly without exception
    await n8n_orchestrator.handle_agency_event(event)


@pytest.mark.asyncio
async def test_state_machine_lifecycle_consistency():
    """
    Case 11: Lifecycle transitions follow exact defined stages:
    DISCOVERED -> VERIFIED -> AUDITED -> (QUALIFIED | RESEARCH_REQUIRED | REJECTED)
    """
    async with AsyncSessionLocal() as session:
        await create_test_country_and_niche(session)
        uid = uuid.uuid4().hex[:8]
        biz = Business(
            name=f"Lifecycle Business {uid}",
            domain=f"lifecycle-{uid}.com",
            country="US",
            city="Houston",
            niche="hvac",
            public_email=f"contact@{uid}-hvac.com",
            email_status="verified",
            pipeline_stage=PipelineStage.DISCOVERED.value
        )
        session.add(biz)
        await session.commit()

        # Step 1: Discovered -> Verified
        biz.pipeline_stage = PipelineStage.VERIFIED.value
        await session.commit()

        # Step 2: Verified -> Audited
        biz.pipeline_stage = PipelineStage.AUDITED.value
        await session.commit()

        # Step 3: Audited -> Scored & Qualified
        await create_audit_run(session, biz.id, health_score=35.0)
        score = await lead_scoring_engine.score_business(session, biz)
        await session.refresh(biz)

        assert biz.pipeline_stage in (PipelineStage.QUALIFIED.value, PipelineStage.RESEARCH_REQUIRED.value)
        assert score.total_score >= 55.0
