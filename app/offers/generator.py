from typing import List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import Business, AuditRun, AuditFinding, Offer, LeadScore
from app.core.config import settings
from app.core.logging import logger

SERVICE_PACKAGES = {
    "CONVERSION_REMEDIATION": {
        "title": "Mobile Conversion & Inquiry Engine Turnaround",
        "service_type": "Conversion Rate Optimization",
        "base_min": 450.0,
        "base_max": 850.0,
        "recommended": 650.0,
        "days": 5,
        "deliverables": [
            "Implementation of high-converting Above-the-Fold mobile CTA banner",
            "One-tap click-to-call direct dial integration across all page headers",
            "Streamlined 3-field high-converting inquiry capture form with instant SMS notification",
            "Social proof and Google Reviews badge integration on primary conversion pathways"
        ],
        "value_prop": "Directly eliminates mobile drop-off and turns passive visitors into qualified inbound phone and form inquiries."
    },
    "LOCAL_SEO_SCHEMA": {
        "title": "Local Search Authority & Schema Acceleration",
        "service_type": "Technical & Local SEO",
        "base_min": 500.0,
        "base_max": 950.0,
        "recommended": 750.0,
        "days": 7,
        "deliverables": [
            "Complete schema.org/LocalBusiness JSON-LD structured data deployment",
            "Meta title and description optimization across core service pages",
            "Canonical link structuring and Google indexation audit",
            "H1-H3 heading topical hierarchy alignment with local search intent"
        ],
        "value_prop": "Positions the business for Google Local 3-Pack visibility and rich map snippets to outrank domestic competitors."
    },
    "PERFORMANCE_SPEED": {
        "title": "Core Web Vitals & Load Speed Acceleration",
        "service_type": "Performance Optimization",
        "base_min": 400.0,
        "base_max": 750.0,
        "recommended": 550.0,
        "days": 4,
        "deliverables": [
            "Script deferral and render-blocking JavaScript/CSS optimization",
            "Full asset conversion to next-gen WebP/AVIF formats with responsive srcset",
            "Browser caching configuration and static payload compression",
            "Mobile viewport layout shift (CLS) and Largest Contentful Paint (LCP) fix"
        ],
        "value_prop": "Slashes mobile load times under 2 seconds, preventing bounce rates and boosting search algorithm rankings."
    },
    "ACCESSIBILITY_COMPLIANCE": {
        "title": "ADA & WCAG 2.1 AA Accessibility Remediation",
        "service_type": "Accessibility Remediation",
        "base_min": 450.0,
        "base_max": 900.0,
        "recommended": 680.0,
        "days": 5,
        "deliverables": [
            "Full alt text remediation across all informational and gallery images",
            "Form field accessible label (<label> and aria-label) compliance fix",
            "Keyboard navigation focus states and empty button label remediation",
            "HTML document language and landmark semantic tagging"
        ],
        "value_prop": "Protects against compliance liability while ensuring effortless navigation for users with assistive technology."
    },
    "FULL_DIGITAL_TURNAROUND": {
        "title": "Comprehensive Revenue & Performance Digital Turnaround",
        "service_type": "Full Digital Turnaround Package",
        "base_min": 950.0,
        "base_max": 1850.0,
        "recommended": 1350.0,
        "days": 10,
        "deliverables": [
            "Complete mobile conversion overhaul (above-fold CTA, click-to-call, lead capture)",
            "Core Web Vitals speed optimization and script deferral (< 2s load time)",
            "LocalBusiness JSON-LD schema injection and on-page SEO meta overhaul",
            "WCAG 2.1 AA accessibility remediation across forms and imagery",
            "Dedicated service page content expansion outline"
        ],
        "value_prop": "A turn-key modernization that transforms the website from a passive brochure into an active client acquisition engine."
    }
}

class OfferEngine:
    """
    Analyzes audit findings and lead scores to recommend the most commercially viable,
    highest-impact service package and generate tailored commercial offers ($400-$1,500+).
    """

    def recommend_service_package(self, audit: AuditRun) -> Dict[str, Any]:
        # Count severe findings by category
        perf_deficit = 100.0 - audit.performance_score
        seo_deficit = 100.0 - audit.seo_score
        a11y_deficit = 100.0 - audit.a11y_score
        ux_deficit = 100.0 - audit.ux_conversion_score

        severe_categories = sum(1 for d in [perf_deficit, seo_deficit, a11y_deficit, ux_deficit] if d > 45.0)

        # If 3 or more categories have severe issues, recommend the full turnaround package
        if severe_categories >= 3:
            return SERVICE_PACKAGES["FULL_DIGITAL_TURNAROUND"]

        # Otherwise recommend the single most impactful deficit package (smallest package, highest value)
        deficits = [
            ("CONVERSION_REMEDIATION", ux_deficit),
            ("LOCAL_SEO_SCHEMA", seo_deficit),
            ("PERFORMANCE_SPEED", perf_deficit),
            ("ACCESSIBILITY_COMPLIANCE", a11y_deficit)
        ]
        deficits.sort(key=lambda x: x[1], reverse=True)
        top_package_key = deficits[0][0]
        return SERVICE_PACKAGES[top_package_key]

    async def generate_offer_for_business(self, session: AsyncSession, business: Business) -> Offer:
        audit_q = select(AuditRun).where(AuditRun.business_id == business.id).order_by(AuditRun.audited_at.desc())
        audit = (await session.execute(audit_q)).scalars().first()
        if not audit:
            raise ValueError(f"Cannot generate offer: Business {business.id} has no audit records.")

        pkg = self.recommend_service_package(audit)

        # Check existing offer
        existing_q = select(Offer).where(Offer.business_id == business.id)
        offer = (await session.execute(existing_q)).scalars().first()

        scope_desc = (
            f"Tailored remediation for {business.name} ({business.domain}). "
            f"Addresses primary findings identified during technical inspection: "
            f"{', '.join(pkg['deliverables'][:2])}."
        )

        if not offer:
            offer = Offer(
                business_id=business.id,
                service_type=pkg["service_type"],
                title=pkg["title"],
                scope_description=scope_desc,
                deliverables=pkg["deliverables"],
                suggested_price_min=pkg["base_min"],
                suggested_price_max=pkg["base_max"],
                recommended_price=pkg["recommended"],
                estimated_delivery_days=pkg["days"],
                value_proposition=pkg["value_prop"]
            )
            session.add(offer)
        else:
            offer.service_type = pkg["service_type"]
            offer.title = pkg["title"]
            offer.scope_description = scope_desc
            offer.deliverables = pkg["deliverables"]
            offer.suggested_price_min = pkg["base_min"]
            offer.suggested_price_max = pkg["base_max"]
            offer.recommended_price = pkg["recommended"]
            offer.estimated_delivery_days = pkg["days"]
            offer.value_proposition = pkg["value_prop"]

        await session.commit()
        logger.info(f"Generated offer for {business.name}: {offer.title} (${offer.recommended_price:.0f})")
        return offer

offer_engine = OfferEngine()
