import pytest
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database.connection import Base
from app.database.models import (
    Business, Contact, AuditRun, AuditFinding, LeadScore,
    Offer, OutreachMessage, PipelineStage, PipelineEvent, Country, Niche
)
from app.api.routes import classify_outreach_record
from app.core.security import sanitize_scraped_email, validate_email_syntax
from app.scoring.engine import lead_scoring_engine
from app.orchestrator.worker import agency_worker


def test_contact_email_sanitization_removes_entity_artifacts():
    dirty_1 = 'u003einfo@homeandaway.ie'
    clean_1 = sanitize_scraped_email(dirty_1)
    assert clean_1 == 'info@homeandaway.ie'
    assert validate_email_syntax(clean_1) is True

    dirty_2 = '&gt;contact@domain.com'
    clean_2 = sanitize_scraped_email(dirty_2)
    assert clean_2 == 'contact@domain.com'

    dirty_3 = '\\u003eowner@company.co.uk'
    clean_3 = sanitize_scraped_email(dirty_3)
    assert clean_3 == 'owner@company.co.uk'

    invalid = 'u003e<not-an-email>'
    assert sanitize_scraped_email(invalid) is None


@pytest.mark.asyncio
async def test_lead_qualification_floor_enforced_in_worker():
    test_engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        country = Country(code='US', name='United States', gdp_per_capita=65000.0)
        niche = Niche(slug='real-estate', name='Real Estate', avg_deal_size=1200.0)
        session.add_all([country, niche])
        await session.flush()

        biz = Business(
            id=100,
            name='Low Score Realty',
            domain='lowscorerealty.com',
            country='US',
            city='Denver',
            niche='real-estate',
            pipeline_stage=PipelineStage.AUDITED.value,
            public_email='info@lowscorerealty.com',
            email_status='verified'
        )
        session.add(biz)
        await session.flush()

        audit = AuditRun(
            id=100,
            business_id=100,
            url_audited='https://lowscorerealty.com',
            overall_health_score=95.0,
            performance_score=95.0,
            seo_score=95.0,
            a11y_score=95.0,
            ux_conversion_score=95.0,
            metrics={'ux_conversion': {'call_opportunity': {'call_driven_score': 10.0}}}
        )
        session.add(audit)
        await session.flush()

        scored = await agency_worker.drain_scoring_backlog(session, limit=5)
        assert scored == 1

        await session.refresh(biz)
        
        q_ls = select(LeadScore).where(LeadScore.business_id == 100)
        ls = (await session.execute(q_ls)).scalar_one()
        assert ls.total_score < 55.0
        
        assert biz.pipeline_stage == PipelineStage.REJECTED.value

        drafted = await agency_worker.drain_drafting_backlog(session, limit=5)
        assert drafted == 0

    await test_engine.dispose()


def test_real_external_deterministic_classification_does_not_mutate():
    biz = Business(
        id=200,
        name='Vanquish Real Estate',
        domain='vanquishrealestate.com',
        country='UK',
        city='London',
        niche='real-estate',
        pipeline_stage='CONTACTED'
    )
    msg = OutreachMessage(
        id=62,
        business_id=200,
        recipient_email='info@vanquishrealestate.com',
        subject='Question regarding vanquishrealestate.com',
        status='SENT',
        provider='titan',
        provider_message_id='titan_msg_62',
        sent_at=datetime(2026, 9, 16, 21, 33, 51)
    )

    verdict_1 = classify_outreach_record(msg, biz)
    assert verdict_1 == 'REAL_EXTERNAL'

    assert msg.id == 62
    assert msg.status == 'SENT'
    assert biz.pipeline_stage == 'CONTACTED'

    verdict_2 = classify_outreach_record(msg, biz)
    assert verdict_2 == 'REAL_EXTERNAL'


def test_niche_slug_normalization_and_icp_bonus():
    country = Country(code='US', name='United States', gdp_per_capita=75000.0)
    biz = Business(
        id=300,
        name='Top Tier Roofing',
        domain='toptierroofing.com',
        country='US',
        city='Miami',
        niche='ROOFING',
        pipeline_stage=PipelineStage.AUDITED.value,
        public_email='info@toptierroofing.com',
        email_status='verified'
    )
    audit = AuditRun(
        id=300,
        business_id=300,
        url_audited='https://toptierroofing.com',
        overall_health_score=70.0,
        performance_score=65.0,
        seo_score=60.0,
        a11y_score=75.0,
        ux_conversion_score=70.0,
        metrics={'ux_conversion': {'call_opportunity': {'call_driven_score': 70.0}}}
    )

    for slug in ['ROOFING', 'roofing', 'roofing-contractors', 'DENTAL', 'dental-practices', 'REAL_ESTATE']:
        niche = Niche(slug=slug, name=slug, avg_deal_size=2500.0)
        score, priority, breakdown, rationale = lead_scoring_engine.calculate_score(biz, audit, country, niche)
        assert breakdown['call_opportunity']['is_call_driven_icp'] is True, f"Failed for niche slug {slug}"
        assert 'High-value call-driven ICP' in rationale, f"ICP driver missing for {slug}"


@pytest.mark.asyncio
async def test_score_business_resolves_niche_casing_and_aliases():
    test_engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        country = Country(code='US', name='United States', gdp_per_capita=75000.0)
        niche = Niche(slug='roofing-contractors', name='Roofing Contractors', avg_deal_size=3500.0)
        session.add_all([country, niche])
        await session.flush()

        biz = Business(
            id=301,
            name='Apex Roofing Solutions',
            domain='apexroofingsolutions.com',
            country='US',
            city='Miami',
            niche='ROOFING',
            pipeline_stage=PipelineStage.DISCOVERED.value,
            public_email='contact@apexroofingsolutions.com',
            email_status='verified'
        )
        session.add(biz)
        await session.flush()

        audit = AuditRun(
            id=301,
            business_id=301,
            url_audited='https://apexroofingsolutions.com',
            overall_health_score=45.0,
            performance_score=40.0,
            seo_score=35.0,
            a11y_score=50.0,
            ux_conversion_score=45.0,
            metrics={'ux_conversion': {'call_opportunity': {'call_driven_score': 75.0}}}
        )
        session.add(audit)
        await session.flush()

        lead_score = await lead_scoring_engine.score_business(session, biz)
        assert lead_score.scoring_breakdown['call_opportunity']['is_call_driven_icp'] is True
        assert lead_score.total_score >= 55.0
        assert biz.pipeline_stage == PipelineStage.QUALIFIED.value

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_real_web_discovery_registry_alias_matching():
    from app.lead_generation.adapters.real_web_discovery import RealWebDiscoveryAdapter
    adapter = RealWebDiscoveryAdapter()
    leads = await adapter.discover_leads(country_code="US", niche_slug="ROOFING", limit=2)
    assert len(leads) > 0
    first = leads[0]
    assert first.country == "US"
    assert first.domain is not None
    assert "deficit_signals" in first.social_profiles


@pytest.mark.asyncio
async def test_audit_engine_unreachable_website_handles_error_without_missing_greenlet():
    from app.auditing.engine import website_audit_engine
    test_engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        biz = Business(
            id=500,
            name='Nonexistent Biz',
            domain='nonexistent-domain-404-xyz.com',
            website_url='https://nonexistent-domain-404-xyz.com',
            country='US',
            city='Denver',
            niche='ROOFING',
            pipeline_stage=PipelineStage.DISCOVERED.value
        )
        session.add(biz)
        await session.flush()

        # Auditing a non-existent domain triggers network failure branch
        audit_run = await website_audit_engine.audit_business(session, biz)
        assert audit_run.overall_health_score == 0.0
        assert biz.pipeline_stage == PipelineStage.REJECTED.value

    await test_engine.dispose()



