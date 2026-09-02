import pytest
from bs4 import BeautifulSoup
from sqlalchemy import select
from app.auditing.crawler import CrawlResult
from app.auditing.performance import performance_auditor
from app.auditing.seo import seo_auditor
from app.auditing.accessibility import accessibility_auditor
from app.auditing.ux_conversion import ux_conversion_auditor
from app.auditing.engine import website_audit_engine
from app.database.models import Business, AuditFinding, AuditSeverity

BAD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <!-- No title, no meta description, no viewport -->
</head>
<body>
    <img src="test.bmp"> <!-- missing alt, legacy format -->
    <form>
        <input type="text"> <!-- missing label -->
        <button></button> <!-- empty button -->
    </form>
</body>
</html>
"""

def test_performance_auditor_detects_viewport_and_images():
    soup = BeautifulSoup(BAD_HTML, "html.parser")
    crawl = CrawlResult("https://testsite.com", 200, 1400.0, {}, BAD_HTML, soup)
    score, findings, metrics = performance_auditor.audit(crawl)
    assert score < 70.0
    finding_names = [f["finding"] for f in findings]
    assert "Missing Mobile Viewport Configuration" in finding_names
    assert "Excessive Server Response Time / TTFB" in finding_names

def test_seo_auditor_detects_missing_title_meta_schema():
    soup = BeautifulSoup(BAD_HTML, "html.parser")
    crawl = CrawlResult("https://testsite.com", 200, 300.0, {}, BAD_HTML, soup)
    score, findings, metrics = seo_auditor.audit(crawl)
    assert score < 60.0
    finding_names = [f["finding"] for f in findings]
    assert "Missing Page Title Tag" in finding_names
    assert "Missing Meta Description" in finding_names
    assert "Missing LocalBusiness Schema Markup" in finding_names

def test_accessibility_auditor_detects_wcag_violations():
    soup = BeautifulSoup(BAD_HTML, "html.parser")
    crawl = CrawlResult("https://testsite.com", 200, 300.0, {}, BAD_HTML, soup)
    score, findings, metrics = accessibility_auditor.audit(crawl)
    finding_names = [f["finding"] for f in findings]
    assert "Images Missing Accessible Alt Text" in finding_names
    assert "Form Fields Lacking Accessible Labels" in finding_names
    assert "Empty Interactive Buttons" in finding_names

@pytest.mark.asyncio
async def test_master_audit_engine(db_session):
    biz = Business(
        name="Test Plumbing Co",
        domain="testplumbing.com",
        website_url="https://testplumbing.com",
        country="US",
        niche="plumbing-services",
        public_email="info@testplumbing.com"
    )
    db_session.add(biz)
    await db_session.commit()

    audit = await website_audit_engine.audit_business(db_session, biz)
    assert audit.overall_health_score > 0
    
    findings_q = select(AuditFinding).where(AuditFinding.audit_id == audit.id)
    findings = (await db_session.execute(findings_q)).scalars().all()
    assert len(findings) > 5
    assert biz.pipeline_stage == "AUDITED"
