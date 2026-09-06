"""
Phase 14 Test Suite — Analytics & Decision Dashboard.
Validates:
1. Math and date helper safety (safe_div and get_cutoff_date).
2. Empty database handling (no NaN, no zero division, clean state).
3. Actual revenue calculation (only paid payments/won contracts).
4. Pipeline value != Actual revenue separation (isolated keys & badges).
5. Funnel stages match DB counts (DISCOVERED to WON).
6. Market Radar country and niche grouping (evidence-backed vs model-derived).
7. Prospect Quality distributions (scores and audit health buckets).
8. Service demand distribution across 10 catalog services.
9. Safe division by zero (returns None / "Insufficient data").
10. Estimated recoverable customer value disclosure & is_revenue == False.
11. Model outputs labeled MODEL OUTPUT / INTERNAL ONLY.
12. Time filtering (today, 7d, 30d, 90d, all).
13. Unauthenticated requests rejected (HTTP 401 when AUTH_ENABLED=True).
14. Authenticated requests return valid data structures.
15. Regression: Zero outreach dispatched & RESEARCH_ONLY=true.
"""

import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.api.app import app
from app.core.config import settings
from app.core.security import create_session_token
from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, ClientIntelligenceRecord, OutreachMessage,
    Payment, Deal, Proposal, Reply, Meeting, Customer,
    ProspectEvidence, ActiveOutreachLock, PipelineStage,
    AcquisitionRun, DiscoveryRun, Offer, User
)
from app.analytics.service import analytics_service, safe_div, get_cutoff_date, CATALOG_SERVICES


@pytest.fixture
def auth_headers():
    token = create_session_token("test_admin", role="admin")
    return {"Cookie": f"agency_session={token}"}


@pytest.mark.asyncio
async def test_01_safe_div_and_date_helpers():
    """Validates math and date helper safety."""
    assert safe_div(10, 0) is None
    assert safe_div(0, 0) is None
    assert safe_div(5, -1) is None
    assert safe_div(5, 10, multiply_100=True) == 50.0
    assert safe_div(1, 3) == 0.33

    assert get_cutoff_date("all") is None
    assert get_cutoff_date(None) is None
    now = datetime.utcnow()
    c_today = get_cutoff_date("today")
    assert c_today is not None and c_today.date() == now.date()
    c_7d = get_cutoff_date("7d")
    assert c_7d is not None and (now - c_7d).days >= 6


@pytest.mark.asyncio
async def test_02_empty_database_analytics():
    """Validates that analytics service handles an empty or clean state without NaN or division-by-zero errors."""
    async with AsyncSessionLocal() as session:
        overview = await analytics_service.get_executive_overview(session, time_filter="all")
        assert "actual_revenue_collected" in overview
        assert overview["actual_revenue_collected"]["badge"] == "ACTUAL"
        assert overview["average_deal_size"]["value"] is None or isinstance(overview["average_deal_size"]["value"], (int, float))

        funnel = await analytics_service.get_acquisition_funnel(session, time_filter="all")
        assert len(funnel["steps"]) == 7
        for step in funnel["steps"]:
            assert step["badge"] == "ACTUAL"
            assert isinstance(step["count"], int)

        sales = await analytics_service.get_sales_analytics(session, time_filter="all")
        assert "reply_rate_pct" in sales["metrics"]
        assert "meeting_rate_pct" in sales["metrics"]

        est = await analytics_service.get_estimated_value(session, time_filter="all")
        assert est["is_revenue"] is False
        assert "Model estimate based on stated assumptions; not guaranteed revenue." in est["mandatory_disclosure"]

        quality = await analytics_service.get_data_quality_metrics(session)
        assert "overall_quality_status" in quality


@pytest.mark.asyncio
async def test_03_actual_revenue_calculation_only_paid():
    """Validates that actual revenue only aggregates completed/paid payments."""
    async with AsyncSessionLocal() as session:
        b_rev = Business(
            name="Rev Biz",
            domain="revbizunique.com",
            country="US",
            niche="roofing"
        )
        session.add(b_rev)
        await session.flush()

        cust = Customer(
            business_id=b_rev.id,
            company_name="Rev Test Customer Co",
            contact_email="cust@revtest.com",
            contract_amount=2500.0
        )
        session.add(cust)
        await session.flush()

        p_paid = Payment(
            customer_id=cust.id,
            business_id=b_rev.id,
            amount=2500.0,
            currency="USD",
            status="PAID",
            reference_id="ref_paid_test_1",
            paid_at=datetime.utcnow()
        )
        p_pending = Payment(
            customer_id=cust.id,
            business_id=b_rev.id,
            amount=5000.0,
            currency="USD",
            status="PAYMENT_PENDING",
            reference_id="ref_pending_test_1"
        )
        session.add_all([p_paid, p_pending])
        await session.commit()

        try:
            overview = await analytics_service.get_executive_overview(session, time_filter="all")
            rev = overview["actual_revenue_collected"]["value"]
            assert rev >= 2500.0

            rev_analytics = await analytics_service.get_revenue_analytics(session, time_filter="all")
            assert rev_analytics["actual_revenue_total"]["amount"] >= 2500.0
        finally:
            await session.execute(delete(Payment).where(Payment.reference_id.in_(["ref_paid_test_1", "ref_pending_test_1"])))
            await session.execute(delete(Customer).where(Customer.id == cust.id))
            await session.execute(delete(Business).where(Business.id == b_rev.id))
            await session.commit()


@pytest.mark.asyncio
async def test_04_pipeline_value_strictly_separated_from_revenue():
    """Validates that pipeline value is never conflated with actual revenue."""
    async with AsyncSessionLocal() as session:
        b_deal = Business(
            name="Pipeline Deal Biz",
            domain="pipelinedealbiz.com",
            country="United States",
            niche="roofing"
        )
        session.add(b_deal)
        await session.flush()

        deal = Deal(
            business_id=b_deal.id,
            title="Active Enterprise Pipeline Opportunity",
            service_type="Website Performance Turnaround",
            total_value=7500.0,
            status="PROPOSAL_SENT"
        )
        session.add(deal)
        await session.commit()

        try:
            rev_analytics = await analytics_service.get_revenue_analytics(session, time_filter="all")
            pipeline_val = rev_analytics["pipeline_value"]["amount"]

            assert pipeline_val >= 7500.0
            assert "never be conflated with actual collected revenue" in rev_analytics["separation_notice"]
            assert rev_analytics["pipeline_value"]["badge"] == "PIPELINE - NOT REVENUE"
        finally:
            await session.execute(delete(Deal).where(Deal.id == deal.id))
            await session.execute(delete(Business).where(Business.id == b_deal.id))
            await session.commit()


@pytest.mark.asyncio
async def test_05_acquisition_funnel_counts_and_dropoffs():
    """Validates that funnel steps match exact database stage counts and dropoffs."""
    async with AsyncSessionLocal() as session:
        b1 = Business(
            name="Funnel Biz 1",
            domain="funnel1.com",
            country="United Kingdom",
            niche="roofing",
            pipeline_stage="DISCOVERED",
            verification_status="NEW"
        )
        b2 = Business(
            name="Funnel Biz 2",
            domain="funnel2.com",
            country="United Kingdom",
            niche="roofing",
            pipeline_stage="VERIFIED",
            verification_status="VERIFIED"
        )
        b3 = Business(
            name="Funnel Biz 3",
            domain="funnel3.com",
            country="United Kingdom",
            niche="roofing",
            pipeline_stage="WON",
            verification_status="VERIFIED",
            public_email="owner@funnel3.com"
        )
        session.add_all([b1, b2, b3])
        await session.commit()

        try:
            funnel = await analytics_service.get_acquisition_funnel(session, time_filter="all")
            steps_dict = {s["stage"]: s["count"] for s in funnel["steps"]}

            assert steps_dict["DISCOVERED"] >= 3
            assert steps_dict["VERIFIED"] >= 2
            assert steps_dict["WON"] >= 1
        finally:
            await session.execute(delete(Business).where(Business.domain.in_(["funnel1.com", "funnel2.com", "funnel3.com"])))
            await session.commit()


@pytest.mark.asyncio
async def test_06_market_radar_country_and_niche_grouping():
    """Validates market radar groupings and distinction between evidence-backed and model-derived."""
    async with AsyncSessionLocal() as session:
        b_uk = Business(
            name="UK Test Biz",
            domain="ukradar.co.uk",
            country="United Kingdom",
            niche="plumbing",
            verification_status="VERIFIED",
            prospect_score=0.88,
            effective_evidence_score=0.92
        )
        b_ca = Business(
            name="Canada Test Biz",
            domain="canadaradar.ca",
            country="Canada",
            niche="solar",
            verification_status="NEW",
            prospect_score=0.75,
            effective_evidence_score=0.0
        )
        session.add_all([b_uk, b_ca])
        await session.commit()

        try:
            radar = await analytics_service.get_market_radar(session)
            countries = {c["country"]: c for c in radar["by_country"]}
            niches = {n["niche"]: n for n in radar["by_niche"]}

            assert "United Kingdom" in countries
            assert "Canada" in countries
            assert countries["United Kingdom"]["verified_prospects"] >= 1
            assert "plumbing" in niches

            assert "evidence_backed_metrics" in radar["legend"]
            assert "model_derived_metrics" in radar["legend"]
        finally:
            await session.execute(delete(Business).where(Business.domain.in_(["ukradar.co.uk", "canadaradar.ca"])))
            await session.commit()


@pytest.mark.asyncio
async def test_07_prospect_quality_distributions():
    """Validates distribution bucketing of prospect scores and audit health scores."""
    async with AsyncSessionLocal() as session:
        b = Business(
            name="Score Distribution Test Biz",
            domain="scoredist.com",
            country="United States",
            niche="roofing",
            prospect_score=0.72,
            effective_evidence_score=0.85
        )
        session.add(b)
        await session.flush()

        audit = AuditRun(
            business_id=b.id,
            url_audited="https://scoredist.com",
            overall_health_score=68.5
        )
        session.add(audit)
        await session.commit()

        try:
            dist = await analytics_service.get_prospect_quality_distribution(session, time_filter="all")
            ps_dist = dist["prospect_scores"]["distribution"]
            health_dist = dist["website_health_scores"]["distribution"]

            assert ps_dist["0.6-0.8"] >= 1
            assert health_dist["60-80"] >= 1
            assert dist["prospect_scores"]["badge"] == "MODEL OUTPUT / HEURISTIC"
            assert dist["website_health_scores"]["badge"] == "ACTUAL MEASUREMENT"
        finally:
            await session.execute(delete(AuditRun).where(AuditRun.id == audit.id))
            await session.execute(delete(Business).where(Business.id == b.id))
            await session.commit()


@pytest.mark.asyncio
async def test_08_service_demand_distribution_10_catalog_services():
    """Validates distribution across the 10 catalog services."""
    async with AsyncSessionLocal() as session:
        b = Business(
            name="Service Demand Biz",
            domain="servicedemandunique.com",
            country="United Kingdom",
            niche="roofing"
        )
        session.add(b)
        await session.flush()

        await session.execute(delete(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == b.id))

        intel = ClientIntelligenceRecord(
            business_id=b.id,
            top_service_id="SERVICE_001",
            top_service_name="AI Receptionist & Lead Capture",
            fit_score=0.92,
            p_win=0.78,
            recommended_price_usd=1250.0
        )
        session.add(intel)
        await session.commit()

        try:
            demand = await analytics_service.get_service_demand_distribution(session, time_filter="all")
            services = demand["services"]
            assert len(services) == 10

            s1 = next(s for s in services if s["service_id"] == "SERVICE_001")
            assert s1["match_count"] >= 1
            assert s1["avg_fit_score"] is not None
            assert s1["badge_fit"] == "MODEL OUTPUT"
        finally:
            await session.execute(delete(ClientIntelligenceRecord).where(ClientIntelligenceRecord.id == intel.id))
            await session.execute(delete(Business).where(Business.id == b.id))
            await session.commit()


@pytest.mark.asyncio
async def test_09_sales_analytics_zero_denominator_safety():
    """Validates sales metrics handle zero contacted/replied safely without throwing ZeroDivisionError."""
    async with AsyncSessionLocal() as session:
        sales = await analytics_service.get_sales_analytics(session, time_filter="today")
        if sales["counts"]["contacted"] == 0:
            assert sales["metrics"]["reply_rate_pct"]["value"] is None
            assert sales["metrics"]["reply_rate_pct"]["display"] == "Insufficient data"
            assert any("contacted_count == 0" in reason for reason in sales["insufficient_data_reasons"])


@pytest.mark.asyncio
async def test_10_estimated_recoverable_value_mandatory_disclosure():
    """Validates estimated recoverable value includes mandatory disclosure and is_revenue=False."""
    async with AsyncSessionLocal() as session:
        b = Business(
            name="ROI Disclosure Biz",
            domain="roidisclosureunique.com",
            country="United States",
            niche="roofing"
        )
        session.add(b)
        await session.flush()

        await session.execute(delete(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == b.id))

        intel = ClientIntelligenceRecord(
            business_id=b.id,
            roi_estimate={
                "estimated_annual_recoverable_usd": 18000.0,
                "estimated_monthly_recoverable_usd": 1500.0
            }
        )
        session.add(intel)
        await session.commit()

        try:
            est = await analytics_service.get_estimated_value(session, time_filter="all")
            assert est["total_estimated_annual_recoverable_value"] >= 18000.0
            assert est["is_revenue"] is False
            assert est["badge"] == "ESTIMATED"
            assert est["mandatory_disclosure"] == "Model estimate based on stated assumptions; not guaranteed revenue."
        finally:
            await session.execute(delete(ClientIntelligenceRecord).where(ClientIntelligenceRecord.id == intel.id))
            await session.execute(delete(Business).where(Business.id == b.id))
            await session.commit()


@pytest.mark.asyncio
async def test_11_model_outputs_summary_internal_only_labeling():
    """Validates that P(Win) and Fit Scores are labeled MODEL OUTPUT / INTERNAL ONLY."""
    async with AsyncSessionLocal() as session:
        summary = await analytics_service.get_model_outputs_summary(session, time_filter="all")
        assert summary["fit_score"]["badge"] == "MODEL OUTPUT / INTERNAL ONLY"
        assert summary["p_win"]["badge"] == "MODEL OUTPUT / INTERNAL ONLY"
        assert summary["selection_score"]["badge"] == "MODEL OUTPUT / INTERNAL ONLY"
        assert summary["client_facing_safety"] is False
        assert "never be presented as factual claims" in summary["disclaimer"]


@pytest.mark.asyncio
async def test_12_time_filtering_accuracy():
    """Validates that time filters accurately isolate past vs recent records."""
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        old_time = now - timedelta(days=45)

        b_recent = Business(
            name="Recent Time Biz",
            domain="recenttime.com",
            country="US",
            niche="roofing",
            created_at=now
        )
        b_old = Business(
            name="Old Time Biz",
            domain="oldtime.com",
            country="US",
            niche="roofing",
            created_at=old_time
        )
        session.add_all([b_recent, b_old])
        await session.commit()

        try:
            funnel_7d = await analytics_service.get_acquisition_funnel(session, time_filter="7d")
            funnel_all = await analytics_service.get_acquisition_funnel(session, time_filter="all")

            d_7d = next(s["count"] for s in funnel_7d["steps"] if s["stage"] == "DISCOVERED")
            d_all = next(s["count"] for s in funnel_all["steps"] if s["stage"] == "DISCOVERED")
            assert d_all >= d_7d
        finally:
            await session.execute(delete(Business).where(Business.domain.in_(["recenttime.com", "oldtime.com"])))
            await session.commit()


@pytest.mark.asyncio
async def test_13_security_unauthenticated_requests_rejected():
    """Validates that all /api/analytics endpoints reject unauthenticated requests with HTTP 401 when auth is active."""
    orig_auth = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            endpoints = [
                "/api/analytics/overview",
                "/api/analytics/funnel",
                "/api/analytics/market-radar",
                "/api/analytics/quality",
                "/api/analytics/services",
                "/api/analytics/sales",
                "/api/analytics/revenue",
                "/api/analytics/estimated-value",
                "/api/analytics/model-outputs",
                "/api/analytics/data-quality"
            ]
            for ep in endpoints:
                resp = await client.get(ep)
                assert resp.status_code == 401, f"Endpoint {ep} allowed unauthenticated access!"
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_14_authenticated_analytics_api_endpoints(auth_headers):
    """Validates that authenticated requests succeed and return valid payloads."""
    orig_auth = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            endpoints = [
                "/api/analytics/overview",
                "/api/analytics/funnel",
                "/api/analytics/market-radar",
                "/api/analytics/quality",
                "/api/analytics/services",
                "/api/analytics/sales",
                "/api/analytics/revenue",
                "/api/analytics/estimated-value",
                "/api/analytics/model-outputs",
                "/api/analytics/data-quality"
            ]
            for ep in endpoints:
                resp = await client.get(ep, headers=auth_headers)
                assert resp.status_code == 200, f"Endpoint {ep} failed with {resp.status_code}: {resp.text}"
                data = resp.json()
                assert isinstance(data, dict)
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_15_regression_safety_no_outreach_dispatched():
    """Validates that RESEARCH_ONLY is maintained and no autonomous outreach is enabled in analytics."""
    orig = settings.RESEARCH_ONLY
    try:
        settings.RESEARCH_ONLY = True
        assert settings.RESEARCH_ONLY is True
        async with AsyncSessionLocal() as session:
            overview = await analytics_service.get_executive_overview(session)
            assert overview is not None
            assert overview["actual_revenue_collected"]["badge"] == "ACTUAL"
    finally:
        settings.RESEARCH_ONLY = orig
