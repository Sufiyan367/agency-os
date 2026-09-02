from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import Business, AuditRun, AuditFinding, PipelineStage, PipelineEvent
from app.auditing.crawler import website_crawler
from app.auditing.performance import performance_auditor
from app.auditing.seo import seo_auditor
from app.auditing.accessibility import accessibility_auditor
from app.auditing.ux_conversion import ux_conversion_auditor
from app.auditing.security import security_auditor
from app.auditing.content import content_auditor
from app.core.logging import logger

class WebsiteAuditEngine:
    """
    Master audit orchestrator aggregating multi-dimensional website audits
    into structured database models and transparent business findings.
    """
    async def audit_business(self, session: AsyncSession, business: Business) -> AuditRun:
        logger.info(f"Auditing website for business {business.name} ({business.website_url})...")
        crawl_res = await website_crawler.fetch(business.website_url)

        # Run individual audit suites
        perf_score, perf_findings, perf_metrics = performance_auditor.audit(crawl_res)
        seo_score, seo_findings, seo_metrics = seo_auditor.audit(crawl_res)
        a11y_score, a11y_findings, a11y_metrics = accessibility_auditor.audit(crawl_res)
        ux_score, ux_findings, ux_metrics = ux_conversion_auditor.audit(crawl_res)
        sec_score, sec_findings, sec_metrics = security_auditor.audit(crawl_res)
        cont_score, cont_findings, cont_metrics = content_auditor.audit(crawl_res)

        # Calculate weighted overall health score (0-100)
        overall_health = round(
            (perf_score * 0.20) +
            (seo_score * 0.25) +
            (a11y_score * 0.15) +
            (ux_score * 0.20) +
            (sec_score * 0.10) +
            (cont_score * 0.10),
            1
        )

        all_findings = (
            perf_findings + seo_findings + a11y_findings +
            ux_findings + sec_findings + cont_findings
        )

        # Sort findings by severity priority
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        all_findings.sort(key=lambda f: severity_order.get(f["severity"], 5))

        # Formulate executive summary
        critical_count = sum(1 for f in all_findings if f["severity"] == "CRITICAL")
        high_count = sum(1 for f in all_findings if f["severity"] == "HIGH")
        
        summary = (
            f"Audit completed with overall site health of {overall_health}/100. "
            f"Identified {len(all_findings)} actionable items ({critical_count} critical, {high_count} high severity). "
            f"Primary remediation areas: "
            f"{'SEO & Schema, ' if seo_score < 70 else ''}"
            f"{'Mobile UX & Conversion, ' if ux_score < 70 else ''}"
            f"{'Core Web Vitals Speed, ' if perf_score < 70 else ''}"
            f"{'Accessibility Compliance' if a11y_score < 70 else ''}."
        )

        # Create and persist AuditRun
        audit_run = AuditRun(
            business_id=business.id,
            url_audited=business.website_url,
            audited_at=datetime.utcnow(),
            performance_score=perf_score,
            seo_score=seo_score,
            a11y_score=a11y_score,
            ux_conversion_score=ux_score,
            security_score=sec_score,
            content_score=cont_score,
            overall_health_score=overall_health,
            summary=summary,
            tech_stack=sec_metrics.get("tech_stack", ["Custom HTML"]),
            metrics={
                "performance": perf_metrics,
                "seo": seo_metrics,
                "accessibility": a11y_metrics,
                "ux_conversion": ux_metrics,
                "security": sec_metrics,
                "content": cont_metrics
            }
        )
        session.add(audit_run)
        await session.flush()

        # Add AuditFinding records
        for f in all_findings:
            finding_record = AuditFinding(
                audit_id=audit_run.id,
                category=f["category"],
                finding=f["finding"],
                severity=f["severity"],
                evidence=f["evidence"],
                url=business.website_url,
                recommended_fix=f["recommended_fix"],
                estimated_business_impact=f["estimated_business_impact"],
                confidence=f.get("confidence", 0.90)
            )
            session.add(finding_record)

        # Update business pipeline stage to AUDITED
        business.pipeline_stage = PipelineStage.AUDITED.value
        event = PipelineEvent(
            business_id=business.id,
            from_stage=PipelineStage.VERIFIED.value,
            to_stage=PipelineStage.AUDITED.value,
            deal_value=0.0,
            note=f"Audit completed. Overall Health: {overall_health}/100. Found {len(all_findings)} issues."
        )
        session.add(event)
        await session.commit()

        logger.info(f"Audit completed for {business.name}. Health: {overall_health}/100, Findings: {len(all_findings)}")
        return audit_run

website_audit_engine = WebsiteAuditEngine()
