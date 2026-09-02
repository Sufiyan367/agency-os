from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import Business, AuditRun, AuditFinding, Offer, Customer, Project

class DeliveryReportGenerator:
    """
    Generates professional Technical Website Audit & Remediation Reports
    in Markdown and HTML for client delivery.
    """

    async def generate_audit_report_markdown(self, session: AsyncSession, business_id: int) -> str:
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business {business_id} not found.")

        audit_q = select(AuditRun).where(AuditRun.business_id == business_id).order_by(AuditRun.audited_at.desc())
        audit = (await session.execute(audit_q)).scalars().first()
        if not audit:
            raise ValueError(f"Audit not found for business {business_id}.")

        findings_q = select(AuditFinding).where(AuditFinding.audit_id == audit.id)
        findings = list((await session.execute(findings_q)).scalars().all())

        offer_q = select(Offer).where(Offer.business_id == business_id)
        offer = (await session.execute(offer_q)).scalars().first()

        lines = [
            f"# Website Diagnostic & Engineering Remediation Report",
            f"**Target Company:** {biz.name}",
            f"**Domain:** [{biz.domain}]({biz.website_url})",
            f"**Location:** {biz.city or 'N/A'}, {biz.country}",
            f"**Date Generated:** {datetime.utcnow().strftime('%B %d, %Y')}",
            f"**Overall Health Score:** {audit.overall_health_score}/100",
            f"",
            f"---",
            f"",
            f"## 1. Executive Summary",
            audit.summary,
            f"",
            f"## 2. Category Performance Scorecard",
            f"| Diagnostic Vector | Score (0-100) | Status |",
            f"| :--- | :--- | :--- |",
            f"| **Performance & Speed** | {audit.performance_score}/100 | {'Optimal' if audit.performance_score >= 80 else 'Requires Action'} |",
            f"| **Technical & Local SEO** | {audit.seo_score}/100 | {'Optimal' if audit.seo_score >= 80 else 'Requires Action'} |",
            f"| **Accessibility (WCAG)** | {audit.a11y_score}/100 | {'Optimal' if audit.a11y_score >= 80 else 'Requires Action'} |",
            f"| **UX & Conversion CRO** | {audit.ux_conversion_score}/100 | {'Optimal' if audit.ux_conversion_score >= 80 else 'Requires Action'} |",
            f"| **Security & Headers** | {audit.security_score}/100 | {'Optimal' if audit.security_score >= 80 else 'Requires Action'} |",
            f"| **Content Depth & Schema** | {audit.content_score}/100 | {'Optimal' if audit.content_score >= 80 else 'Requires Action'} |",
            f"",
            f"## 3. Detailed Audit Findings & Remediation Steps",
        ]

        for i, f in enumerate(findings, 1):
            lines.extend([
                f"### {i}. [{f.severity}] {f.category}: {f.finding}",
                f"- **Observable Evidence:** {f.evidence}",
                f"- **Business Impact:** {f.estimated_business_impact}",
                f"- **Recommended Technical Fix:** {f.recommended_fix}",
                f"- **Confidence:** {f.confidence * 100:.0f}%",
                f""
            ])

        if offer:
            lines.extend([
                f"---",
                f"## 4. Remediation Scope of Work & Deliverables",
                f"**Package:** {offer.title}",
                f"**Estimated Delivery Timeframe:** {offer.estimated_delivery_days} business days",
                f"**Commercial Investment:** ${offer.recommended_price:.0f} USD",
                f"",
                f"### Core Deliverables:",
            ])
            for d in offer.deliverables:
                lines.append(f"- [x] {d}")

        return "\n".join(lines)

delivery_report_generator = DeliveryReportGenerator()
