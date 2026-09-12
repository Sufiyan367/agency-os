import pytest
import uuid
from datetime import datetime
from sqlalchemy import select, func
from bs4 import BeautifulSoup

from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, AuditFinding, Offer, OutreachMessage,
    OutreachStatus, PipelineStage, PipelineEvent, ClientIntelligenceRecord,
    ProspectEvidence, LeadScore, Country, Niche
)
from app.auditing.crawler import CrawlResult
from app.auditing.content import content_auditor
from app.outreach.personalization import outreach_personalizer
from app.outreach.queue import outreach_approval_queue
from app.campaigns.sender_registry import sender_registry
from app.campaigns.config import campaign_config_loader


@pytest.mark.asyncio
async def test_state_consistency_pending_approval_clears_approved_at():
    """
    Issue 1: When an outreach message is staged in PENDING_APPROVAL,
    approved_at must be None. When reset_to_pending is called, approved_at
    must be cleared and pipeline stage remains APPROVAL awaiting review.
    """
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:8]
        biz = Business(
            name=f"Consistency Test Auto {uid}",
            domain=f"testauto-{uid}.ae",
            country="AE",
            city="Dubai",
            niche="Automotive Repair",
            public_email=f"service@{uid}.ae",
            pipeline_stage=PipelineStage.QUALIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # 1. Create message directly in APPROVED status (simulating a prior approval)
        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject="Test Subject",
            body="Test Body",
            status=OutreachStatus.APPROVED.value,
            approved_at=datetime.utcnow()
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        assert msg.approved_at is not None

        # 2. Reset message to PENDING_APPROVAL using OutreachApprovalQueue
        reset_msg = await outreach_approval_queue.reset_to_pending(
            session=session,
            message_id=msg.id,
            reason="Canary readiness review"
        )
        assert reset_msg.status == OutreachStatus.PENDING_APPROVAL.value
        assert reset_msg.approved_at is None

        # 3. Verify in database
        q = select(OutreachMessage).where(OutreachMessage.id == msg.id)
        db_msg = (await session.execute(q)).scalar_one()
        assert db_msg.status == OutreachStatus.PENDING_APPROVAL.value
        assert db_msg.approved_at is None


@pytest.mark.asyncio
async def test_content_auditor_no_geographic_or_niche_leaks():
    """
    Issue 4: Content auditor must NEVER output hardcoded US/niche template strings
    such as '/service-areas/north-austin' or '/commercial-roofing' for Middle East prospects.
    """
    html_without_locations = """
    <!DOCTYPE html>
    <html>
    <head><title>Orange Auto Repair Dubai</title></head>
    <body>
        <h1>Premium Car Service in Al Quoz, Dubai</h1>
        <p>Expert brake, tire, and AC services in Dubai, UAE.</p>
        <a href="/contact">Contact Us</a>
        <a href="/about">About Us</a>
    </body>
    </html>
    """
    soup = BeautifulSoup(html_without_locations, "html.parser")
    crawl = CrawlResult(
        url="https://orangeauto.ae",
        status_code=200,
        load_time_ms=120.0,
        headers={},
        html_content=html_without_locations,
        soup=soup
    )
    score, findings, metrics = content_auditor.audit(crawl)

    for f in findings:
        evidence_text = f.get("evidence", "")
        fix_text = f.get("recommended_fix", "")

        # Strictly assert no North Austin or roofing leaks
        assert "north-austin" not in evidence_text.lower()
        assert "austin" not in evidence_text.lower()
        assert "commercial-roofing" not in fix_text.lower()

    # Specifically check the geographic service area finding if triggered
    geo_findings = [f for f in findings if f.get("finding") == "Missing City / Geographic Service Area Pages"]
    if geo_findings:
        gf = geo_findings[0]
        assert "No dedicated geographic or regional service area pages detected" in gf["evidence"]
        assert "Develop targeted service area pages" in gf["recommended_fix"]


@pytest.mark.asyncio
async def test_empirical_evidence_safeguards_hypothesis_language():
    """
    Issue 2 & 5: When empirical evidence is 0, outreach copy must use
    hypothesis/observation framing rather than asserting operational failure
    or lost revenue as established fact.
    """
    uid = uuid.uuid4().hex[:8]
    biz = Business(
        name=f"Hypothesis Auto {uid}",
        domain=f"hypo-{uid}.ae",
        country="AE",
        city="Dubai",
        niche="Automotive Repair",
        public_email=f"contact@{uid}.ae",
        pipeline_stage=PipelineStage.QUALIFIED.value,
        evidence_count=0
    )
    audit = AuditRun(
        business_id=biz.id or 1,
        url_audited=f"https://hypo-{uid}.ae",
        overall_health_score=85.0
    )
    findings = [
        AuditFinding(
            category="UX & Conversion",
            finding="Potential After-Hours / Peak Missed-Call Opportunity",
            evidence="Published phone line observed as primary contact without 24/7 automated answering.",
            recommended_fix="Implement an autonomous AI Receptionist to answer, qualify, and book incoming calls.",
            estimated_business_impact="Uncaptured inbound inquiries during busy periods.",
            confidence=0.85
        )
    ]
    offer = Offer(
        business_id=biz.id or 1,
        title="Autonomous AI Receptionist & After-Hours Call Recovery",
        service_type="AI Voice & Inbound Lead Recovery",
        suggested_price_min=500.0,
        suggested_price_max=1500.0,
        recommended_price=1000.0,
        estimated_delivery_days=7
    )

    # 1. Generate variants with has_empirical_evidence=False
    variants = outreach_personalizer.generate_message_variants(
        business=biz,
        audit=audit,
        findings=findings,
        offer=offer,
        has_empirical_evidence=False
    )

    for v in variants:
        body = v["body"]
        # Must NOT assert factual loss of revenue or unverified internal metrics
        assert "15–30%" not in body
        assert "15-30%" not in body
        assert "lost commercial pipeline" not in body
        assert "depressing your inbound contact rate" not in body

        # Must use conditional / hypothesis phrasing
        assert (
            "potential missed-call opportunities" in body.lower() or
            "potential friction" in body.lower() or
            "potential opportunities" in body.lower() or
            "can lead high-intent clients to call competing providers" in body.lower()
        )


@pytest.mark.asyncio
async def test_no_unsupported_roi_claims():
    """
    Issue 3: Ensure neither the backend client intelligence nor pricing engine
    injects unsupported 15–30% quantitative claims when data is insufficient.
    """
    from app.client_intelligence.pricing import PricingEngine
    from app.client_intelligence.models import (
        BusinessProfile, BusinessSizeEstimate, BusinessSegment, InferredField,
        ServiceMatch, ROIEstimate
    )

    pricing_engine = PricingEngine()
    empty_roi = ROIEstimate(status="INSUFFICIENT_DATA", confidence=0.0)
    profile = BusinessProfile(
        business_name="Test Garage",
        domain="testgarage.ae",
        industry=InferredField(value="Automotive Repair"),
        location=InferredField(value="Dubai"),
        services=InferredField(value=["Mechanic", "Brakes"]),
        website_quality=InferredField(value=85.0),
        contact_channels=InferredField(value=["phone", "email"]),
        booking_workflow=InferredField(value="static_form"),
        visible_tooling=InferredField(value=[]),
        review_signals=InferredField(value={"rating": 4.5}),
        operational_maturity=InferredField(value="developing")
    )
    size_est = BusinessSizeEstimate(segment=BusinessSegment.SMALL)
    matched_svc = ServiceMatch(service_id="SERVICE_001", service_name="AI Lead Qualification", fit_score=0.85)

    pricing = pricing_engine.recommend_pricing(
        profile=profile,
        size_estimate=size_est,
        matched_service=matched_svc,
        roi_estimate=empty_roi
    )
    assert pricing.recommended_price_usd >= 500.0

    # Ensure no reasoning string contains speculative 15–30% claims
    for r in pricing.reasoning:
        assert "15–30%" not in r
        assert "15-30%" not in r


@pytest.mark.asyncio
async def test_commercial_score_vs_match_fit_distinction():
    """
    Issue 6: Clarifies why Commercial Lead Score (20.3/100 LOW) can coexist
    with MATCH FIT: OPTIMAL (0.98). Lead score measures macro firmographic
    distress/priority; Match Fit measures micro service solution suitability.
    """
    from app.client_intelligence.matcher import ServiceMatcher
    from app.client_intelligence.models import (
        BusinessProfile, BusinessSizeEstimate, BusinessSegment, InferredField,
        DetectedPainPoint, OperationalWasteEstimate, PainCategory
    )
    from app.scoring.engine import LeadScoringEngine

    matcher = ServiceMatcher()
    profile = BusinessProfile(
        business_name="Orange Auto Dubai",
        domain="orangeauto.ae",
        industry=InferredField(value="Automotive Repair"),
        location=InferredField(value="Dubai"),
        services=InferredField(value=["Car Repair", "Brakes"]),
        website_quality=InferredField(value=87.0),
        contact_channels=InferredField(value=["phone", "email"]),
        booking_workflow=InferredField(value="static_form"),
        visible_tooling=InferredField(value=[]),
        review_signals=InferredField(value={"rating": 4.6}),
        operational_maturity=InferredField(value="developing")
    )
    pains = [
        DetectedPainPoint(
            category=PainCategory.APPOINTMENT_SCHEDULING,
            severity=0.65,
            evidence=["Booking workflow relies on telephone and static form without interactive calendar."],
            confidence=0.85,
            estimated_frequency="Daily",
            estimated_business_impact="Friction during booking causes high drop-off.",
            automation_feasible=True
        ),
        DetectedPainPoint(
            category=PainCategory.FOLLOW_UP,
            severity=0.70,
            evidence=["No automated nurture sequence or scheduled follow-up mechanism identified."],
            confidence=0.75,
            estimated_frequency="Daily",
            estimated_business_impact="Lack of systematic multi-touch follow-up leaves potential leads uncontacted.",
            automation_feasible=True
        )
    ]
    size_est = BusinessSizeEstimate(segment=BusinessSegment.SMALL)
    waste = OperationalWasteEstimate(
        estimated_manual_hours_weekly_low=7.5,
        estimated_manual_hours_weekly_high=15.5
    )
    matches = matcher.match_services(
        profile=profile,
        size_estimate=size_est,
        pain_points=pains,
        waste_estimate=waste
    )

    top_match = matches[0]
    assert top_match.fit_score >= 0.70
    fit_label = "OPTIMAL" if top_match.fit_score >= 0.85 else ("STRONG" if top_match.fit_score >= 0.70 else "MODERATE")
    assert fit_label in ["OPTIMAL", "STRONG"]

    # Macro LeadScoringEngine evaluates general website weakness & firmographic distress.
    scorer = LeadScoringEngine()
    test_biz = Business(
        name="Orange Auto Dubai",
        domain="orangeauto.ae",
        public_email="info@orangeauto.ae",
        email_status="verified"
    )
    test_audit = AuditRun(
        business_id=1,
        url_audited="https://orangeauto.ae",
        overall_health_score=87.0,
        seo_score=90.0,
        performance_score=65.0,
        a11y_score=85.0,
        ux_conversion_score=80.0
    )
    test_country = Country(code="AE", name="United Arab Emirates", gdp_per_capita=44000.0)
    test_niche = Niche(name="Automotive Repair", slug="automotive", avg_deal_size=800.0)
    comp_score, priority, breakdown, rationale = scorer.calculate_score(
        business=test_biz,
        audit=test_audit,
        country=test_country,
        niche=test_niche
    )
    assert comp_score < 50.0
    assert priority in ["LOW", "C"]


@pytest.mark.asyncio
async def test_orange_auto_canary_remains_pending_approval():
    """
    Safety & Invariants: Orange Auto Canary (#12, Business 30) must remain
    strictly in PENDING_APPROVAL with approved_at is None and daily capacity = 1.
    """
    async with AsyncSessionLocal() as session:
        # Check Orange Auto message in database (Business 30, Message 12)
        q = select(OutreachMessage).where(
            OutreachMessage.id == 12,
            OutreachMessage.business_id == 30
        )
        msg = (await session.execute(q)).scalar_one_or_none()
        if msg:
            assert msg.status == OutreachStatus.PENDING_APPROVAL.value
            assert msg.approved_at is None

        # Confirm Stage-1 Canary daily outbound limit is strictly 1
        rollout = campaign_config_loader.get_rollout_config()
        level_1 = next((l for l in rollout.levels if l.level == 1), None)
        assert level_1 is not None and level_1.daily_max_real_emails == 1
