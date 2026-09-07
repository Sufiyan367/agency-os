"""
Requirements Engine — Phase 19.
Deterministic extraction of client requirements packets from empirical audit findings,
matched service packages, and commercial business data.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Business, AuditRun, AuditFinding, Offer, LeadScore
from app.core.logging import logger


class RequirementItem(BaseModel):
    id: str
    category: str
    title: str
    description: str
    target_metric: str
    current_value: str
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW


class RequirementsPacket(BaseModel):
    business_id: int
    business_name: str
    domain: str
    city: Optional[str] = None
    country: str
    contact_email: str
    service_title: str
    catalog_price_usd: float
    advance_amount_usd: float
    turnaround_days: int
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    deliverables: List[str]
    requirements: List[RequirementItem]
    architectural_constraints: List[str]
    client_identity_verification: Dict[str, Any]


class RequirementsEngine:
    """
    Synthesizes provider-independent, deterministic requirements packets
    grounded in empirical audit evidence and catalog service specifications.
    """

    @classmethod
    def generate_packet_from_data(
        cls,
        business: Business,
        audit: AuditRun,
        findings: List[AuditFinding],
        offer: Offer,
        lead_score: Optional[LeadScore] = None
    ) -> RequirementsPacket:
        domain = business.domain
        biz_name = business.name or domain
        price = offer.recommended_price
        advance = round(price * 0.40, 2)

        requirements: List[RequirementItem] = []
        deliverables: List[str] = []

        # 1. Process Empirical Audit Deficits into Requirements
        for idx, f in enumerate(findings, 1):
            req_id = f"REQ-{business.id}-{idx:02d}"
            curr_val = f.evidence or "Non-compliant"
            target_metric = cls._determine_target_metric(f.category, f.finding)
            requirements.append(
                RequirementItem(
                    id=req_id,
                    category=f.category,
                    title=f.finding,
                    description=f.recommended_fix or "Remediate identified deficiency.",
                    target_metric=target_metric,
                    current_value=str(curr_val),
                    priority=f.severity or "HIGH"
                )
            )

        # 2. Add Deliverables based on service package
        service_title = offer.title
        if "Speed" in service_title or "Performance" in service_title or "Core Web Vitals" in service_title:
            deliverables.extend([
                "Edge CDN caching configuration and static asset compression",
                "Asynchronous script loader deployment (defer/async migration)",
                "Next-gen WebP/AVIF image format conversion and lazy loading",
                "Core Web Vitals diagnostic verification report with sub-second response proof"
            ])
        elif "Conversion" in service_title or "CRO" in service_title:
            deliverables.extend([
                "High-contrast mobile click-to-call action header deployment",
                "Streamlined 3-field asynchronous lead inquiry form",
                "Above-the-fold hero CTA alignment across all device viewports",
                "Verified conversion pathway tracking configuration"
            ])
        else:
            deliverables.extend([
                "Comprehensive full-stack digital turnaround remediation",
                "Structural semantic SEO optimization (H1 and meta tag configuration)",
                "LocalBusiness schema structured data deployment",
                "Full technical audit sign-off and before-and-after verification report"
            ])

        # 3. Architectural Constraints
        constraints = [
            "Zero downtime deployment — all asset changes verified in staging first",
            "Non-invasive integration — preserves existing DNS, hosting compute, and brand styling",
            "Fully deterministic implementation — no external runtime dependencies",
            "100% compliant with commercial policy and data safety standards"
        ]

        # 4. Identity Verification
        identity = {
            "business_name": biz_name,
            "domain": domain,
            "city": business.city,
            "country": business.country,
            "verified_public_email": business.public_email,
            "verified_at": datetime.utcnow().isoformat()
        }

        return RequirementsPacket(
            business_id=business.id,
            business_name=biz_name,
            domain=domain,
            city=business.city,
            country=business.country,
            contact_email=business.public_email or f"info@{domain}",
            service_title=service_title,
            catalog_price_usd=price,
            advance_amount_usd=advance,
            turnaround_days=offer.estimated_delivery_days or 5,
            deliverables=deliverables,
            requirements=requirements,
            architectural_constraints=constraints,
            client_identity_verification=identity
        )

    @classmethod
    async def build_requirements_packet(
        cls, session: AsyncSession, business_id: int
    ) -> RequirementsPacket:
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business {business_id} not found.")

        audit_q = select(AuditRun).where(AuditRun.business_id == business_id).order_by(AuditRun.audited_at.desc())
        audit = (await session.execute(audit_q)).scalars().first()
        if not audit:
            raise ValueError(f"No audit run found for business {business_id}.")

        findings_q = select(AuditFinding).where(AuditFinding.audit_id == audit.id)
        findings = list((await session.execute(findings_q)).scalars().all())

        offer_q = select(Offer).where(Offer.business_id == business_id).order_by(Offer.created_at.desc())
        offer = (await session.execute(offer_q)).scalars().first()
        if not offer:
            raise ValueError(f"No offer found for business {business_id}.")

        score_q = select(LeadScore).where(LeadScore.business_id == business_id)
        lead_score = (await session.execute(score_q)).scalar_one_or_none()

        packet = cls.generate_packet_from_data(biz, audit, findings, offer, lead_score)
        logger.info(f"[RequirementsEngine] Generated packet for {biz.domain} ({len(packet.requirements)} items).")
        return packet

    @staticmethod
    def _determine_target_metric(category: str, finding_title: str) -> str:
        cat_lower = category.lower()
        title_lower = finding_title.lower()

        if "ttfb" in title_lower or "latency" in title_lower or "response time" in title_lower:
            return "Server response latency < 600ms"
        if "script" in title_lower or "render-blocking" in title_lower:
            return "100% non-critical scripts deferred or asynchronous"
        if "image" in title_lower or "raster" in title_lower:
            return "Modern format WebP/AVIF with compression ratio >= 40%"
        if "tel" in title_lower or "click-to-call" in title_lower or "phone" in title_lower:
            return "Active clickable 'tel:' link on all phone numbers"
        if "h1" in title_lower or "heading" in title_lower:
            return "Single primary <h1> tag containing targeted location & service"
        if "schema" in title_lower or "structured data" in title_lower:
            return "Valid schema.org/LocalBusiness JSON-LD markup"
        if "meta" in title_lower or "description" in title_lower:
            return "150-160 character meta description with CTA"
        return "100% compliance with engineering remediation specification"


requirements_engine = RequirementsEngine()
