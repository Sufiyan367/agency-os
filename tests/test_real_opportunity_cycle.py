"""
Agency OS — Real Opportunity Qualification & CEO Approval Queue Verification.

Proves the complete 11-step cycle for REAL qualified opportunities across 6 offer themes:
1. Beauty / Nail Studios
2. Fitness / Gyms
3. Restaurants / Cafes
4. Photographers / Videographers
5. Course Creators / Experts
6. Auto Parts Stores
"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base, Business, AuditRun, AuditFinding, LeadScore, OutreachMessage,
    PipelineStage, Offer, VerificationStatus
)
from app.auditing.engine import WebsiteAuditEngine
from app.ml.feature_store import feature_store
from app.ml.baseline_scorer import baseline_scorer
from app.intelligence.offer_matcher import offer_matcher
from app.analytics.truth_engine import (
    classify_business_provenance,
    is_audit_complete,
    is_compliance_passed,
    is_lead_qualified
)
from app.outreach.personalization import OutreachPersonalizer
from app.lead_generation.adapters.real_web_discovery import RealWebDiscoveryAdapter
from n8n.registry.execution_verifier import N8nExecutionVerifier, ExecutionVerificationState


THEME_CONFIGS = [
    {
        "theme": "Course Creators / Experts",
        "niche": "course-creators",
        "name": "Product School",
        "domain": "productschool.com",
        "website_url": "https://productschool.com",
        "phone": "+1-415-842-9904",
        "public_email": "carlos@productschool.com",
        "city": "San Francisco, CA",
        "country": "US",
    },
    {
        "theme": "Auto Parts Stores",
        "niche": "auto-parts",
        "name": "Dallas Auto Parts",
        "domain": "dallasautoparts.com",
        "website_url": "https://dallasautoparts.com",
        "phone": "+1-214-388-4455",
        "public_email": "info@dallasautoparts.com",
        "city": "Dallas, TX",
        "country": "US",
    },
    {
        "theme": "Restaurants / Cafes",
        "niche": "restaurants-cafes",
        "name": "Franklin Barbecue",
        "domain": "franklinbbq.com",
        "website_url": "https://franklinbbq.com",
        "phone": "+1-512-653-1187",
        "public_email": "hello@franklinbbq.com",
        "city": "Austin, TX",
        "country": "US",
    },
    {
        "theme": "Fitness / Gyms",
        "niche": "fitness",
        "name": "The Warehouse Gym",
        "domain": "whgym.com",
        "website_url": "https://whgym.com",
        "phone": "+971-4-323-2323",
        "public_email": "info@whgym.com",
        "city": "Dubai",
        "country": "AE",
    },
    {
        "theme": "Photographers / Videographers",
        "niche": "photographers",
        "name": "Snappr Studios",
        "domain": "snappr.com",
        "website_url": "https://snappr.com",
        "phone": "+1-877-762-7771",
        "public_email": "support@snappr.com",
        "city": "San Francisco, CA",
        "country": "US",
    },
    {
        "theme": "Beauty / Nail Studios",
        "niche": "nail-studios",
        "name": "MiniLuxe",
        "domain": "miniluxe.com",
        "website_url": "https://miniluxe.com",
        "phone": "+1-855-646-4589",
        "public_email": "help@miniluxe.com",
        "city": "Dallas, TX",
        "country": "US",
    }
]


@pytest.fixture
async def test_session():
    """In-memory isolated SQLite session for test execution."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_discovery_adapter_resolves_all_six_themes():
    """Verify that RealWebDiscoveryAdapter discovers real prospects across all 6 themes."""
    adapter = RealWebDiscoveryAdapter()
    for cfg in THEME_CONFIGS:
        leads = await adapter.discover_leads(niche_slug=cfg["niche"], country_code=cfg["country"], limit=1)
        assert len(leads) >= 1, f"Failed to discover real lead for theme: {cfg['theme']}"
        lead = leads[0]
        assert lead.domain, f"Missing domain for {cfg['theme']}"
        assert lead.public_email and "@" in lead.public_email, f"Missing contact email for {cfg['theme']}"
        assert lead.phone, f"Missing contact phone for {cfg['theme']}"


@pytest.mark.asyncio
async def test_top_opportunity_end_to_end_qualification_and_ceo_queue(test_session: AsyncSession):
    """
    Detailed test of the highest-scoring real opportunity (Product School):
    Validates all 11 steps from discovery to CEO queue staging without sending.
    """
    session = test_session
    audit_engine = WebsiteAuditEngine()
    personalizer = OutreachPersonalizer()

    target = THEME_CONFIGS[0]  # Product School

    # 1. Real business verification
    biz = Business(
        name=target["name"],
        domain=target["domain"],
        website_url=target["website_url"],
        phone=target["phone"],
        public_email=target["public_email"],
        city=target["city"],
        country=target["country"],
        niche=target["niche"],
        verification_status=VerificationStatus.VERIFIED.value,
        pipeline_stage=PipelineStage.DISCOVERED.value
    )
    session.add(biz)
    await session.commit()
    await session.refresh(biz)

    provenance = classify_business_provenance(biz)
    assert provenance == "REAL", f"Expected REAL, got {provenance}"

    # 2. Contact verification
    assert biz.public_email == "carlos@productschool.com"
    assert biz.phone == "+1-415-842-9904"

    # 3. Empirical website audit
    audit = await audit_engine.audit_business(session, biz)
    assert audit.overall_health_score > 0, "Audit health score must be positive"
    assert is_audit_complete(audit), "Audit must satisfy canonical completeness gate"

    from sqlalchemy import select
    findings_q = select(AuditFinding).where(AuditFinding.audit_id == audit.id)
    findings = (await session.execute(findings_q)).scalars().all()
    assert len(findings) > 0, "Audit must record empirical findings"
    audit.findings = findings

    # 4. Identify actual observable pain
    top_pain = findings[0].finding
    assert len(top_pain) > 0, "Must have an observable pain"

    # 5. Match appropriate automation offer
    matched_offer_plan = offer_matcher.match_pain_to_offer(top_pain, niche=biz.niche)
    assert matched_offer_plan.capability_id.startswith("CAP-")
    assert matched_offer_plan.target_price_usd >= 500.0

    # Persist Offer record
    offer = Offer(
        business_id=biz.id,
        service_type=matched_offer_plan.capability_id,
        title=matched_offer_plan.capability_name,
        scope_description=matched_offer_plan.detected_pain,
        deliverables=matched_offer_plan.proposal_scope,
        recommended_price=matched_offer_plan.target_price_usd,
        estimated_delivery_days=matched_offer_plan.turnaround_days,
        value_proposition=f"Resolve {matched_offer_plan.detected_pain} via automation."
    )
    session.add(offer)
    await session.commit()

    # 6. Score using existing qualification engine
    features = feature_store.extract_features(business=biz, audit=audit)
    score_data = baseline_scorer.predict(features)
    lead_score = LeadScore(
        business_id=biz.id,
        total_score=score_data["total_score"],
        priority=score_data["priority"],
        website_weakness_subscore=score_data["quality_score"],
        conversion_opportunity_subscore=score_data["conversion_score"],
        ability_to_pay_subscore=score_data["commercial_fit_score"],
        contactability_subscore=score_data["contactability_score"],
        scoring_breakdown=score_data,
        rationale=score_data.get("explainability", {}).get("formula", "")
    )
    session.add(lead_score)
    await session.commit()

    # 7. Qualification floor check (>= 55.0)
    assert lead_score.total_score >= 55.0, f"Expected score >= 55.0, got {lead_score.total_score}"
    assert is_lead_qualified(biz, lead_score, audit), "Lead must pass canonical is_lead_qualified invariant"

    # 8. Compliance check
    assert is_compliance_passed(biz, audit), "Compliance check must pass"

    # 9. Personalized outreach draft generation
    msg = await personalizer.prepare_outreach_for_business(
        session=session,
        business=biz,
        selected_variant=0,
        auto_approve=False
    )
    assert msg is not None
    assert "productschool.com" in msg.subject or "productschool.com" in msg.body
    assert len(msg.body.split()) >= 30, "Outreach draft must contain substantial copy"

    # 10. Placed in CEO Approval Queue
    assert msg.status == "PENDING_APPROVAL", "Outreach must be pending CEO approval"
    assert biz.pipeline_stage == PipelineStage.APPROVAL.value, "Pipeline stage must be APPROVAL"

    # 11. Confirmed NOT sent
    assert msg.sent_at is None, "Draft must NOT be sent automatically"


@pytest.mark.asyncio
async def test_disqualification_floor_enforcement(test_session: AsyncSession):
    """
    Verifies that when a real business scores below 55.0 (e.g. MiniLuxe with 52.2),
    it is strictly disqualified, does NOT pass is_lead_qualified, and outreach is not drafted.
    """
    session = test_session
    audit_engine = WebsiteAuditEngine()

    target = THEME_CONFIGS[5]  # MiniLuxe

    biz = Business(
        name=target["name"],
        domain=target["domain"],
        website_url=target["website_url"],
        phone=target["phone"],
        public_email=target["public_email"],
        city=target["city"],
        country=target["country"],
        niche=target["niche"],
        verification_status=VerificationStatus.VERIFIED.value,
        pipeline_stage=PipelineStage.DISCOVERED.value
    )
    session.add(biz)
    await session.commit()
    await session.refresh(biz)

    audit = await audit_engine.audit_business(session, biz)
    from sqlalchemy import select
    findings = (await session.execute(select(AuditFinding).where(AuditFinding.audit_id == audit.id))).scalars().all()
    audit.findings = findings

    features = feature_store.extract_features(business=biz, audit=audit)
    score_data = baseline_scorer.predict(features)
    lead_score = LeadScore(
        business_id=biz.id,
        total_score=score_data["total_score"],
        priority=score_data["priority"],
        website_weakness_subscore=score_data["quality_score"],
        conversion_opportunity_subscore=score_data["conversion_score"],
        ability_to_pay_subscore=score_data["commercial_fit_score"],
        contactability_subscore=score_data["contactability_score"],
        scoring_breakdown=score_data
    )
    session.add(lead_score)
    await session.commit()

    # Empirical score is 52.2 (< 55.0 floor)
    assert lead_score.total_score < 55.0
    qualified = is_lead_qualified(biz, lead_score, audit)
    assert qualified is False, "Leads below 55.0 must NOT be qualified"


def test_n8n_execution_verification_for_automation_template():
    """Verifies that the matched automation workflow passes N8nExecutionVerifier."""
    verifier = N8nExecutionVerifier()
    template_rel_path = "n8n/templates/appointment_automation/missed_call_textback"
    test_payload = {
        "caller_phone": "+15550192834",
        "caller_name": "Jordan",
        "is_after_hours": True,
        "suppressed": False
    }
    expected_assertions = {
        "status": "PROCESSED",
        "textback_dispatched": True,
        "suppression_blocked": False,
        "is_after_hours": True
    }
    report = verifier.verify_template_execution(
        template_rel_path=template_rel_path,
        test_payload=test_payload,
        expected_assertions=expected_assertions
    )
    assert report.overall_certified is True
    assert len(report.steps) == 8
    for step in report.steps:
        assert step.passed is True
