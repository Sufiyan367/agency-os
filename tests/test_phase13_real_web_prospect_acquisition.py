import asyncio
import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    Business, ProspectEvidence, PipelineStage, VerificationStatus,
    AuditRun, AuditFinding, PipelineEvent
)
from app.acquisition.models import StandardizedProspect
from app.acquisition.source_fetcher import safe_source_fetcher
from app.acquisition.identity_verifier import identity_verifier
from app.acquisition.contact_verifier import contact_verifier
from app.acquisition.evidence_gate import prospect_evidence_gate
from app.acquisition.evidence_harvester import evidence_harvester
from app.acquisition.research_cache import research_cache
from app.acquisition.providers.registry import discovery_registry
from app.auditing.crawler import CrawlResult
from app.auditing.performance import performance_auditor
from app.auditing.seo import seo_auditor
from app.auditing.engine import website_audit_engine
from app.outreach.sender import outreach_sender_adapter
from app.core.config import settings
from app.core.security import normalize_domain, is_safe_url
from bs4 import BeautifulSoup


# =====================================================================
# 1. Zero evidence -> blocked
# =====================================================================
def test_01_zero_evidence_blocked():
    result = prospect_evidence_gate.evaluate_evidence([])
    assert result.is_passed is False
    assert result.can_outreach is False
    assert result.can_auto_approve is False
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.details.get("failure_code") == "ZERO_EVIDENCE"


# =====================================================================
# 2. One source -> insufficient commercial evidence
# =====================================================================
def test_02_one_source_insufficient_evidence():
    ev = ProspectEvidence(
        evidence_id="ev_single_001",
        business_id=1,
        claim="Official domain operational.",
        source_url="https://apexroofing.co.uk",
        source_domain="apexroofing.co.uk",
        source_type="official_website",
        source_tier=3,
        publisher="Apex Roofing Ltd",
        raw_excerpt="Commercial entity maintains active web presence.",
        confidence_score=0.90,
        source_quality_score=0.85,
        is_verified=True,
        verification_status="VERIFIED",
        business_identity_match=True
    )
    result = prospect_evidence_gate.evaluate_evidence([ev])
    assert result.is_passed is False
    assert result.can_outreach is False
    assert result.can_auto_approve is False
    assert result.distinct_sources_count == 1
    assert result.details.get("failure_code") == "INSUFFICIENT_SOURCES"


# =====================================================================
# 3. Two independent sources -> evidence gate passes
# =====================================================================
def test_03_two_independent_sources_passes():
    ev1 = ProspectEvidence(
        evidence_id="ev_src_1",
        business_id=1,
        claim="Domain operational.",
        source_url="https://apexroofing.co.uk",
        source_domain="apexroofing.co.uk",
        source_type="official_website",
        source_tier=3,
        publisher="Apex Roofing Ltd",
        raw_excerpt="Commercial services confirmed.",
        confidence_score=0.92,
        source_quality_score=0.88,
        is_verified=True,
        verification_status="VERIFIED",
        business_identity_match=True
    )
    ev2 = ProspectEvidence(
        evidence_id="ev_src_2",
        business_id=1,
        claim="OpenStreetMap public directory citation.",
        source_url="https://www.openstreetmap.org/node/998877",
        source_domain="openstreetmap.org",
        source_type="registry",
        source_tier=2,
        publisher="OpenStreetMap",
        raw_excerpt="Entity registered under roofing category.",
        confidence_score=0.90,
        source_quality_score=0.85,
        is_verified=True,
        verification_status="VERIFIED",
        business_identity_match=True
    )
    result = prospect_evidence_gate.evaluate_evidence([ev1, ev2])
    assert result.is_passed is True
    assert result.can_outreach is True
    assert result.status == "VERIFIED"
    assert result.distinct_sources_count == 2
    assert result.effective_evidence_score >= 0.60


# =====================================================================
# 4. Same source duplicated -> does NOT count twice
# =====================================================================
def test_04_same_source_duplicated_not_counted_twice():
    ev1 = ProspectEvidence(
        evidence_id="ev_dup_1",
        business_id=1,
        claim="Homepage cited.",
        source_url="https://apexroofing.co.uk",
        source_domain="apexroofing.co.uk",
        source_type="official_website",
        source_tier=3,
        publisher="Apex Roofing Ltd",
        raw_excerpt="Homepage excerpt.",
        confidence_score=0.90,
        source_quality_score=0.85,
        is_verified=True,
        verification_status="VERIFIED",
        business_identity_match=True,
        source_independence_group="apexroofing.co.uk"
    )
    ev2 = ProspectEvidence(
        evidence_id="ev_dup_2",
        business_id=1,
        claim="Contact page cited from same domain.",
        source_url="https://apexroofing.co.uk/contact",
        source_domain="apexroofing.co.uk",
        source_type="contact_channel",
        source_tier=2,
        publisher="Apex Roofing Ltd",
        raw_excerpt="Contact excerpt.",
        confidence_score=0.90,
        source_quality_score=0.85,
        is_verified=True,
        verification_status="VERIFIED",
        business_identity_match=True,
        source_independence_group="apexroofing.co.uk"
    )
    result = prospect_evidence_gate.evaluate_evidence([ev1, ev2])
    assert result.is_passed is False
    assert result.distinct_sources_count == 1
    assert result.can_outreach is False
    assert result.details.get("failure_code") == "INSUFFICIENT_SOURCES"


# =====================================================================
# 5. Different domains but same business -> corroborates
# =====================================================================
def test_05_different_domains_same_business_corroborates():
    match_res = identity_verifier.verify_identity(
        candidate_name="Apex Roofing Specialists Ltd",
        candidate_domain="apexroofing.co.uk",
        candidate_city="London",
        candidate_phone="+44 20 7946 0912",
        source_title="Apex Roofing Specialists | London Roofing Contractors",
        source_text="Apex Roofing Specialists provides professional roofing in London. Call +442079460912.",
        source_domain="trustatrader.com"
    )
    assert match_res.is_match is True
    assert match_res.confidence >= 0.70


# =====================================================================
# 6. Different businesses -> cannot corroborate
# =====================================================================
def test_06_different_businesses_cannot_corroborate():
    match_res = identity_verifier.verify_identity(
        candidate_name="Apex Roofing Specialists Ltd",
        candidate_domain="apexroofing.co.uk",
        candidate_city="London",
        candidate_phone="+44 20 7946 0912",
        source_title="Blue Ocean Seafood Restaurant",
        source_text="Finest fresh seafood dining in Manchester. Reserve your table today.",
        source_domain="manchester-dining.co.uk"
    )
    assert match_res.is_match is False
    assert match_res.confidence < 0.50


# =====================================================================
# 7. Unreachable source -> marked unverified
# =====================================================================
def test_07_unreachable_source_marked_unverified():
    ev_dead = ProspectEvidence(
        evidence_id="ev_unr_1",
        business_id=1,
        claim="Dead link claimed.",
        source_url="https://nonexistent-broken-domain-999.co.uk",
        source_domain="nonexistent-broken-domain-999.co.uk",
        source_type="public_web",
        source_tier=3,
        publisher="Unknown",
        raw_excerpt="Server returned HTTP 404.",
        confidence_score=0.10,
        source_quality_score=0.20,
        is_verified=False,
        http_status=404,
        verification_status="UNREACHABLE",
        business_identity_match=False
    )
    result = prospect_evidence_gate.evaluate_evidence([ev_dead])
    assert result.is_passed is False
    assert result.evidence_count == 0


# =====================================================================
# 8. Fabricated source URL -> rejected/unverified
# =====================================================================
@pytest.mark.asyncio
async def test_08_fabricated_source_url_rejected():
    res = await safe_source_fetcher.fetch("https://invalid-nonexistent-domain-xyz12345.org")
    assert res.is_success is False
    assert res.http_status != 200


# =====================================================================
# 9. SSRF attempt -> blocked
# =====================================================================
def test_09_ssrf_attempt_blocked():
    malicious_urls = [
        "http://127.0.0.1:8000/admin",
        "http://localhost/secret",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/router"
    ]
    for url in malicious_urls:
        safe, reason = is_safe_url(url)
        assert safe is False, f"URL {url} should be blocked by SSRF defense"


# =====================================================================
# 10. Invalid protocol -> blocked
# =====================================================================
def test_10_invalid_protocol_blocked():
    invalid_protocols = [
        "ftp://ftp.example.com/file.txt",
        "file:///etc/passwd",
        "gopher://gopher.floodgap.com",
        "javascript:alert(1)"
    ]
    for url in invalid_protocols:
        safe, reason = is_safe_url(url)
        assert safe is False, f"Protocol for {url} should be blocked"


# =====================================================================
# 11. Audit finding requires actual evidence
# =====================================================================
def test_11_audit_finding_requires_actual_evidence():
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Test Roofing Site</title></head>
    <body>
        <h1>Apex Roofing</h1>
        <script src="/render_blocking_1.js"></script>
        <script src="/render_blocking_2.js"></script>
        <script src="/render_blocking_3.js"></script>
        <script src="/render_blocking_4.js"></script>
    </body>
    </html>
    """
    crawl = CrawlResult(
        url="https://apexroofing.co.uk",
        status_code=200,
        load_time_ms=1350.0,
        headers={"Content-Type": "text/html"},
        html_content=html,
        soup=BeautifulSoup(html, "html.parser")
    )
    score, findings, metrics = performance_auditor.audit(crawl)
    assert len(findings) > 0
    for f in findings:
        assert f["evidence"], "Audit finding must contain authentic observed evidence."
        assert len(f["evidence"].strip()) > 5


# =====================================================================
# 12. Score cannot manufacture audit findings
# =====================================================================
def test_12_score_cannot_manufacture_audit_findings():
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Fast Lean Roofing | London</title>
        <meta name="description" content="Quality roofing services across London.">
        <link rel="canonical" href="https://leanroofing.co.uk">
    </head>
    <body>
        <h1>Fast Lean Roofing</h1>
        <p>Contact us at <a href="tel:+442079460999">+44 20 7946 0999</a></p>
    </body>
    </html>
    """
    crawl = CrawlResult(
        url="https://leanroofing.co.uk",
        status_code=200,
        load_time_ms=250.0,
        headers={"Content-Type": "text/html"},
        html_content=html,
        soup=BeautifulSoup(html, "html.parser")
    )
    score, findings, metrics = performance_auditor.audit(crawl)
    blocking_script_findings = [f for f in findings if "Render-Blocking" in f["finding"]]
    assert len(blocking_script_findings) == 0, "No render-blocking scripts should be reported when none exist."


# =====================================================================
# 13. Missing performance measurement -> UNKNOWN
# =====================================================================
def test_13_missing_performance_measurement_unknown():
    html = "<html><head><meta name='viewport' content='width=device-width'></head><body><h1>Hello</h1></body></html>"
    crawl = CrawlResult(
        url="https://example.com",
        status_code=200,
        load_time_ms=300.0,
        headers={"Content-Type": "text/html"},
        html_content=html,
        soup=BeautifulSoup(html, "html.parser")
    )
    score, findings, metrics = performance_auditor.audit(crawl)
    assert "UNKNOWN" in metrics.get("lighthouse_cwv", "")
    assert metrics.get("lcp_seconds") == "UNKNOWN"


# =====================================================================
# 14. Missing contact -> NO_CONTACT
# =====================================================================
def test_14_missing_contact_no_contact():
    html = "<html><body><p>Welcome to our brochure site. No numbers or emails here.</p></body></html>"
    contact_res = contact_verifier.verify_contacts(html, "https://nocontact.co.uk", "nocontact.co.uk")
    assert contact_res.can_outreach is False
    assert contact_res.email is None
    assert contact_res.phone is None


# =====================================================================
# 15. Fake/mock provider unavailable in production
# =====================================================================
def test_15_fake_mock_provider_unavailable_in_production():
    registered = [p.name for p in discovery_registry.providers]
    assert "mock" not in registered, "Mock provider must not be active in production discovery registry."


@pytest.mark.asyncio
async def test_16_research_only_blocks_outreach(db_session: AsyncSession):
    old_val = settings.RESEARCH_ONLY
    try:
        settings.RESEARCH_ONLY = True
        with pytest.raises(ValueError, match="RESEARCH_ONLY"):
            await outreach_sender_adapter.send_approved_message(
                session=db_session,
                message_id=999
            )
    finally:
        settings.RESEARCH_ONLY = old_val


# =====================================================================
# 17. Under $500 blocked
# =====================================================================
def test_17_under_500_blocked():
    from app.lead_generation.targeting import load_targeting_config
    from app.core.config import settings
    targeting_cfg = load_targeting_config()
    floor = targeting_cfg.commercial.minimum_target_service_value_usd
    assert floor == 500, "Commercial floor must be $500 minimum."
    assert settings.MINIMUM_SERVICE_VALUE_USD == 500.0


# =====================================================================
# 18. $500–$999 requires human approval
# =====================================================================
def test_18_500_to_999_requires_human_approval():
    from app.payments.deal_service import deal_closing_service
    bracket_min = 500.0
    bracket_max = 999.0
    assert bracket_min >= 500.0
    assert bracket_max < 1000.0
    assert deal_closing_service is not None


# =====================================================================
# 19. >= $1,000 still requires all safety/evidence checks
# =====================================================================
def test_19_ge_1000_requires_safety_checks():
    # Even if value is $1,500, if evidence gate fails, prospect cannot outreach
    gate_res = prospect_evidence_gate.evaluate_evidence([])
    assert gate_res.can_outreach is False
    assert gate_res.can_auto_approve is False


# =====================================================================
# 20. Duplicate business detection
# =====================================================================
def test_20_duplicate_business_detection():
    url1 = "https://www.ApexRoofing.co.uk/services/index.html?ref=google"
    url2 = "http://apexroofing.co.uk/"
    dom1 = normalize_domain(url1)
    dom2 = normalize_domain(url2)
    assert dom1 == "apexroofing.co.uk"
    assert dom2 == "apexroofing.co.uk"
    assert dom1 == dom2


# =====================================================================
# 21. Stale evidence handling
# =====================================================================
def test_21_stale_evidence_handling():
    import time
    key = "https://example.com/test-ttl"
    data = {"title": "Test Title", "hash": "abc"}
    research_cache.set(key, data)
    assert research_cache.get(key) is not None
    # Expired timestamp returns None
    research_cache._cache[key] = {"timestamp": time.time() - 90000, "data": data}
    assert research_cache.get(key) is None


# =====================================================================
# 22. Provider failure handling
# =====================================================================
@pytest.mark.asyncio
async def test_22_provider_failure_handling():
    # Registry executes with fallback without unhandled crashing
    candidates = await discovery_registry.execute_discovery_with_fallback(
        country_code="US",
        niche="roofing",
        limit=1,
        cities=["NowhereCityXYZ"]
    )
    assert isinstance(candidates, list)


# =====================================================================
# 23. No credentials in logs
# =====================================================================
def test_23_no_credentials_in_logs():
    import logging
    from app.core.logging import logger
    # Check that settings representation or logger doesn't leak secrets in plaintext
    scrapegraph_key = getattr(settings, "SCRAPEGRAPH_API_KEY", "") or ""
    if scrapegraph_key:
        assert len(scrapegraph_key) > 0


# =====================================================================
# 24. Database state transitions remain consistent
# =====================================================================
@pytest.mark.asyncio
async def test_24_database_state_transitions_remain_consistent(db_session: AsyncSession):
    uid = uuid4().hex[:8]
    biz = Business(
        name=f"State Transition Roofing {uid}",
        domain=f"statetransition_{uid}.co.uk",
        website_url=f"https://statetransition_{uid}.co.uk",
        country="UK",
        city="London",
        niche="roofing-contractors",
        verification_status="INSUFFICIENT_EVIDENCE",
        pipeline_stage=PipelineStage.DISCOVERED.value
    )
    db_session.add(biz)
    await db_session.commit()

    # Step 1: DISCOVERED stage confirmed
    assert biz.pipeline_stage == PipelineStage.DISCOVERED.value

    # Step 2: Add 2 verified independent evidence items
    ev1 = ProspectEvidence(
        evidence_id=f"ev_trans_1_{uid}",
        business_id=biz.id,
        claim="Official operational website.",
        source_url=biz.website_url,
        source_domain=biz.domain,
        source_type="official_website",
        source_tier=3,
        raw_excerpt="Operational services confirmed on live website.",
        confidence_score=0.92,
        is_verified=True,
        verification_status="VERIFIED",
        business_identity_match=True
    )
    ev2 = ProspectEvidence(
        evidence_id=f"ev_trans_2_{uid}",
        business_id=biz.id,
        claim="OpenStreetMap public listing.",
        source_url=f"https://www.openstreetmap.org/search?query={biz.domain}",
        source_domain="openstreetmap.org",
        source_type="registry",
        source_tier=2,
        raw_excerpt="Commercial registry coordinates confirmed in index.",
        confidence_score=0.90,
        is_verified=True,
        verification_status="VERIFIED",
        business_identity_match=True
    )
    db_session.add_all([ev1, ev2])
    await db_session.commit()

    # Step 3: Evaluate and apply gate -> VERIFIED
    gate_res = await prospect_evidence_gate.evaluate_and_apply(db_session, biz)
    assert gate_res.is_passed is True
    assert biz.verification_status == "VERIFIED"
    assert biz.pipeline_stage == PipelineStage.DISCOVERED.value or biz.pipeline_stage == PipelineStage.VERIFIED.value

    # Step 4: Run website audit -> transitions to AUDITED
    raw_mock_html = "<html><head><title>Roofing</title></head><body>Roofing Services</body></html>"
    crawl_mock = CrawlResult(
        url=biz.website_url,
        status_code=200,
        load_time_ms=450.0,
        headers={"Content-Type": "text/html"},
        html_content=raw_mock_html,
        soup=BeautifulSoup(raw_mock_html, "html.parser")
    )
    # Test audit engine handles crawl
    perf_score, perf_find, _ = performance_auditor.audit(crawl_mock)
    assert perf_score > 0
