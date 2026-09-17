from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import Business, AuditRun, AuditFinding, ProspectEvidence
from app.outreach.composer.models import ResearchFact


class ResearchRepository:
    """
    Extracts and manages verified research facts strictly bound to a single prospect.
    Supplies factual evidence to the composer and detects existing capabilities
    to prevent contradictory claims.
    """

    @classmethod
    async def get_facts_for_prospect(
        cls,
        session: AsyncSession,
        business: Business
    ) -> List[ResearchFact]:
        facts: List[ResearchFact] = []
        pid = business.id

        # 1. Base business facts
        if business.niche:
            facts.append(ResearchFact(
                prospect_id=pid,
                fact=f"Operating in the {business.niche.replace('-', ' ')} industry",
                source="business_profile",
                category="industry"
            ))

        location_parts = [p for p in [business.city, business.country] if p]
        if location_parts:
            facts.append(ResearchFact(
                prospect_id=pid,
                fact=f"Located in {', '.join(location_parts)}",
                source="business_profile",
                category="location"
            ))

        # 2. Audit findings facts
        audit_q = select(AuditRun).where(AuditRun.business_id == pid).order_by(AuditRun.audited_at.desc())
        audit = (await session.execute(audit_q)).scalars().first()

        if audit:
            # Concrete actionable audit findings FIRST
            findings_q = select(AuditFinding).where(AuditFinding.audit_id == audit.id).order_by(AuditFinding.severity.desc())
            findings = (await session.execute(findings_q)).scalars().all()
            for f in findings:
                cat = "conversion"
                f_text = (f.finding or "").lower()
                if "speed" in f_text or "load" in f_text or "performance" in f_text:
                    cat = "speed"
                elif "seo" in f_text or "schema" in f_text or "meta" in f_text:
                    cat = "seo"
                elif "accessibility" in f_text or "aria" in f_text or "contrast" in f_text:
                    cat = "a11y"
                elif "call" in f_text or "phone" in f_text or "tel:" in f_text or "after-hours" in f_text:
                    cat = "booking"

                facts.append(ResearchFact(
                    prospect_id=pid,
                    fact=f.finding,
                    source=f"audit_finding:{f.id}",
                    category=cat,
                    metric_value=f.evidence
                ))

            # Sub-par overall scores ONLY added if deficient (< 60)
            if audit.ux_conversion_score < 60.0:
                facts.append(ResearchFact(
                    prospect_id=pid,
                    fact=f"Mobile UX conversion friction measured at {audit.ux_conversion_score:.0f}/100",
                    source="audit_run:ux_conversion",
                    category="conversion",
                    metric_value=audit.ux_conversion_score
                ))
            if audit.performance_score < 60.0:
                facts.append(ResearchFact(
                    prospect_id=pid,
                    fact=f"Mobile Core Web Vitals speed measured at {audit.performance_score:.0f}/100",
                    source="audit_run:performance",
                    category="speed",
                    metric_value=audit.performance_score
                ))

        # 3. Prospect evidence (e.g. from scraping or inquiry analysis)
        ev_q = select(ProspectEvidence).where(ProspectEvidence.business_id == pid)
        evidences = (await session.execute(ev_q)).scalars().all()
        for ev in evidences:
            facts.append(ResearchFact(
                prospect_id=pid,
                fact=ev.snippet or ev.key,
                source=f"evidence:{ev.source_url or 'crawl'}",
                category=ev.category or "observation"
            ))

        return facts

    @classmethod
    def analyze_capabilities(cls, facts: List[ResearchFact]) -> Dict[str, bool]:
        """
        Determines existing capabilities to prevent contradictory outreach claims.
        """
        all_text = " ".join([f.fact.lower() + " " + str(f.metric_value or "").lower() for f in facts])

        def _is_high(val: Any, threshold: float = 85.0) -> bool:
            if isinstance(val, (int, float)):
                return val >= threshold
            if isinstance(val, str):
                try:
                    return float(val.strip().replace("%", "")) >= threshold
                except (ValueError, TypeError):
                    return False
            return False

        return {
            "has_online_booking": any(k in all_text for k in ["booking system active", "schedule online", "calendly", "book appointment online", "booking form active"]),
            "has_after_hours_flow": any(k in all_text for k in ["24/7 answering", "after-hours portal", "night answering service"]),
            "has_fast_mobile_speed": any(f.category == "speed" and _is_high(f.metric_value) for f in facts),
            "has_strong_seo": any(f.category == "seo" and _is_high(f.metric_value) for f in facts),
            "has_phone_dependency": any(k in all_text for k in ["call to book", "direct phone inquiry", "relies on telephone", "phone call only"])
        }
