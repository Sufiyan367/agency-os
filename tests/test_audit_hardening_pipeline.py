import pytest
from bs4 import BeautifulSoup
from unittest.mock import MagicMock, AsyncMock, patch

from app.lead_generation.adapters.real_web_discovery import _is_phone_consistent_with_country
from app.outreach.composer.entity_resolver import EntityResolver
from app.outreach.composer.models import CanonicalProspect, ResearchFact, SenderIdentity
from app.outreach.composer.solution_catalog import SolutionMatch
from app.outreach.composer.composer import GeneralizedOutreachComposer
from app.outreach.composer.research_repository import ResearchRepository
from app.auditing.crawler import CrawlResult
from app.auditing.engine import website_audit_engine
from app.scoring.engine import lead_scoring_engine
from app.database.models import Business, AuditRun, AuditFinding, PipelineStage, Country, Niche
from app.acquisition.targeting_catalog import get_country, validate_target_combination, DISABLED_MARKETS


def test_country_phone_consistency():
    # US phone with UK business should be False
    assert not _is_phone_consistent_with_country("+1 415 555 2671", "UK")
    
    # UK phone with UK business should be True
    assert _is_phone_consistent_with_country("+44 151 709 1234", "UK")
    
    # US phone with US business should be True
    assert _is_phone_consistent_with_country("+1 415 555 2671", "US")

    # Entity resolver validation on mismatched phone
    p_mismatch = CanonicalProspect(
        prospect_id=1,
        company_name="London HVAC Ltd",
        canonical_company_domain="londonhvac.co.uk",
        website="https://londonhvac.co.uk",
        recipient_email="info@londonhvac.co.uk",
        phone="+1 415 555 2671",
        country="UK"
    )
    res = EntityResolver.resolve_and_validate(p_mismatch)
    assert not res.is_valid
    assert any("North American phone number" in err for err in res.errors)

    p_valid = CanonicalProspect(
        prospect_id=2,
        company_name="London HVAC Ltd",
        canonical_company_domain="londonhvac.co.uk",
        website="https://londonhvac.co.uk",
        recipient_email="info@londonhvac.co.uk",
        phone="+44 20 7946 0912",
        country="UK"
    )
    res_valid = EntityResolver.resolve_and_validate(p_valid)
    assert res_valid.is_valid


@pytest.mark.asyncio
async def test_audit_unreachable_site_marks_insufficient():
    biz = Business(
        id=999,
        name="Dead Site Ltd",
        website_url="https://this-domain-definitely-does-not-exist-123456789.org",
        pipeline_stage=PipelineStage.DISCOVERED.value
    )
    
    mock_crawl = CrawlResult(
        url=biz.website_url,
        status_code=500,
        load_time_ms=0.0,
        headers={},
        html_content="",
        soup=BeautifulSoup("", "html.parser"),
        is_mock=False,
        error_msg="DNS resolution failed",
        is_successful=False
    )
    
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    
    with patch("app.auditing.engine.website_crawler.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_crawl
        audit_run = await website_audit_engine.audit_business(mock_session, biz)
        
        assert audit_run.overall_health_score == 0.0
        assert "RESEARCH_INSUFFICIENT" in audit_run.summary
        assert biz.pipeline_stage == PipelineStage.REJECTED.value
        assert any("RESEARCH_INSUFFICIENT" in f.finding for f in audit_run.findings)


@pytest.mark.asyncio
async def test_scoring_rejects_low_score():
    biz = Business(
        id=998,
        name="Low Score Biz",
        country="US",
        niche="hvac",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    audit = AuditRun(
        id=998,
        business_id=998,
        overall_health_score=0.0,
        performance_score=0.0,
        seo_score=0.0,
        a11y_score=0.0,
        ux_conversion_score=0.0,
        summary="RESEARCH_INSUFFICIENT: Target web server unreachable",
        metrics={}
    )
    
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    
    # Mock audit run query
    mock_audit_res = MagicMock()
    mock_audit_res.scalars.return_value.first.return_value = audit
    
    # Mock country query
    mock_country_res = MagicMock()
    mock_country_res.scalar_one_or_none.return_value = Country(code="US", name="United States", gdp_per_capita=70000.0)
    
    # Mock niche query
    mock_niche_res = MagicMock()
    mock_niche_res.scalar_one_or_none.return_value = Niche(id=1, slug="hvac", name="HVAC", avg_deal_size=1500.0)
    
    # Mock existing lead score query
    mock_score_res = MagicMock()
    mock_score_res.scalar_one_or_none.return_value = None
    
    mock_session.execute = AsyncMock(side_effect=[mock_audit_res, mock_country_res, mock_niche_res, mock_score_res])
    
    lead_score = await lead_scoring_engine.score_business(mock_session, biz)
    assert lead_score.total_score == 0.0
    assert biz.pipeline_stage == PipelineStage.REJECTED.value
    assert "Disqualified" in lead_score.rationale


def test_composer_prioritizes_concrete_findings():
    prospect = CanonicalProspect(
        prospect_id=3,
        company_name="Apex Heating Ltd",
        canonical_company_domain="apexheating.co.uk",
        website="https://apexheating.co.uk",
        recipient_email="info@apexheating.co.uk",
        country="UK"
    )
    
    facts = [
        ResearchFact(
            prospect_id=3,
            fact="Mobile UX conversion score measured at 90/100",
            category="conversion",
            source="audit_scores"
        ),
        ResearchFact(
            prospect_id=3,
            fact="Missing click-to-call phone action",
            category="conversion",
            source="audit_findings"
        )
    ]
    
    solution = SolutionMatch(
        solution_key="conversion_optimization",
        title="Mobile Conversion Optimization",
        problem_statement="prospective customers encountering mobile friction",
        solution_statement="a streamlined mobile inquiry flow",
        expected_outcome="capture visitors who currently drop off",
        confidence=0.9
    )
    
    sender = SenderIdentity(
        sender_name="Alex Mercer",
        sender_email="alex@agencyos.com",
        sender_company="Agency OS"
    )
    
    composer = GeneralizedOutreachComposer()
    variants = composer.compose_variants(prospect, facts, solution, sender)
    assert len(variants) > 0
    
    # Body should mention the concrete finding ("missing click-to-call phone action"), NOT "90/100" as a flaw
    for v in variants:
        assert "90/100" not in v.body
        assert "missing click-to-call" in v.body.lower() or "call" in v.body.lower()


def test_dynamic_catalog_expansion():
    # Test valid non-catalog country (e.g., EE - Estonia)
    c_ee = get_country("EE")
    assert c_ee is not None
    assert c_ee.code == "EE"
    assert c_ee.acquisition_enabled is True
    
    # Test disabled country remains blocked
    for code in DISABLED_MARKETS:
        c_dis = get_country(code)
        assert c_dis.acquisition_enabled is False
        with pytest.raises(ValueError) as exc:
            validate_target_combination(code, "Region", "City", "HVAC")
        assert "DISABLED" in str(exc.value)
        
    # Test dynamic registration of novel region and city
    val = validate_target_combination("EE", "Harju County", "Tallinn", "HVAC")
    assert val["valid"] is True
    assert val["region"] == "Harju County"
    assert val["city"] == "Tallinn"


def test_email_sanitization_and_validation():
    from app.core.security import sanitize_scraped_email, validate_email_syntax
    
    # Raw unicode artifact email from MSG #35 should be sanitized cleanly
    raw_bad = "u003einfo@homeandaway.ie"
    cleaned = sanitize_scraped_email(raw_bad)
    assert cleaned == "info@homeandaway.ie"
    
    # Raw unicode artifact should be rejected by validate_email_syntax if not sanitized
    assert not validate_email_syntax(raw_bad)
    assert not validate_email_syntax("\\u003einfo@homeandaway.ie")
    assert not validate_email_syntax("&gt;info@homeandaway.ie")
    assert not validate_email_syntax("<info@homeandaway.ie>")
    
    # Sanitizer handles brackets, quotes, html entities
    assert sanitize_scraped_email("<contact@domain.co.uk>") == "contact@domain.co.uk"
    assert sanitize_scraped_email("&gt;sales@enterprise.com") == "sales@enterprise.com"
    assert sanitize_scraped_email("\"support@company.org\"") == "support@company.org"

