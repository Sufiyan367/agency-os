from typing import Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import Business, AuditRun, LeadScore, LeadPriority, PipelineStage, PipelineEvent, Country, Niche
from app.core.config import settings
from app.core.logging import logger

class LeadScoringEngine:
    """
    Computes a transparent 0-100 commercial lead score based on:
    - Website deficiency (Performance, SEO, A11y, UX/Conversion opportunities)
    - Ability to pay (Country GDP & Niche average deal value)
    - Contactability (availability of direct verified business email/phone)
    """

    def calculate_score(
        self, business: Business, audit: AuditRun, country: Country, niche: Niche
    ) -> Tuple[float, str, Dict[str, Any], str]:
        # Deficit/Opportunity in each category = 100 - audit_score
        perf_opp = max(0.0, 100.0 - audit.performance_score)
        seo_opp = max(0.0, 100.0 - audit.seo_score)
        a11y_opp = max(0.0, 100.0 - audit.a11y_score)
        ux_opp = max(0.0, 100.0 - audit.ux_conversion_score)
        website_weakness = max(0.0, 100.0 - audit.overall_health_score)

        # Ability to pay factor (scaled 0-100)
        ability_to_pay = min(100.0, (country.gdp_per_capita / 80000.0) * 60.0 + (niche.avg_deal_size / 1500.0) * 40.0)

        # Contactability factor (0-100)
        if business.public_email and business.email_status == "verified":
            contactability = 100.0
        elif business.public_email:
            contactability = 80.0
        elif business.phone:
            contactability = 50.0
        else:
            contactability = 20.0

        # Extract Call Opportunity Evidence from audit metrics
        metrics = getattr(audit, "metrics", None) or {}
        call_opp = metrics.get("ux_conversion", {}).get("call_opportunity", {})
        call_driven_score = float(call_opp.get("call_driven_score", 50.0))
        has_hours = bool(call_opp.get("business_hours_detected", False))
        after_hours_gap = bool(call_opp.get("after_hours_gap_detected", False))
        app_dep = bool(call_opp.get("appointment_dependency", False))

        raw_slug = (getattr(niche, "slug", "") or getattr(niche, "id", "") or getattr(niche, "name", "") or "").lower().replace("_", "-").strip()
        call_icp_slugs = {
            "dental", "dental-practices", "dental-medical-clinics", "cosmetic-clinics", "dentist",
            "roofing", "roofing-contractors", "roofers",
            "hvac", "hvac-home-services", "hvac-services", "heating-cooling",
            "medical-clinics", "med-spas", "med-spa",
            "real-estate", "property-management",
            "commercial-law", "legal-services", "law-firm", "professional-services",
            "plumbing", "electrical", "electrical-contractors",
            "automotive", "auto-repair",
            "salons-barbers", "beauty",
        }
        is_call_icp = raw_slug in call_icp_slugs or any(k in raw_slug for k in ("dental", "roof", "hvac", "clinic", "real-estate", "plumb", "electric", "auto", "law"))
        call_value_potential = min(100.0, (niche.avg_deal_size / 1500.0) * 70.0 + (call_driven_score * 0.3))
        after_hours_demand = 85.0 if after_hours_gap else (60.0 if has_hours else 40.0)

        # Clean 0-100 ICP fit score based on high-ticket service appointment/call dependency
        icp_score = 75.0 if is_call_icp else 35.0
        if call_driven_score >= 60.0:
            icp_score = min(100.0, icp_score + 25.0)

        # Weighted composite commercial opportunity score (strictly 0.0 - 100.0)
        # Separated from contactability: A missing email does not make a commercially viable prospect look bad.
        # Weights sum strictly to 1.00:
        # - UX & Conversion Opportunity (25%): Core turnaround deliverable (inquiry friction, booking dropoff)
        # - PageSpeed & Core Web Vitals (20%): Measurable performance acceleration deliverable
        # - Local SEO & Visibility (20%): Search schema, metadata, and local capture deliverable
        # - Commercial Ability to Pay (20%): GDP per capita + average deal value ($500+ floor affordability)
        # - ICP Vertical Fit (10%): High-ticket appointment-driven commercial service fit
        # - Accessibility Deficit (5%): Compliance risk and basic usability hygiene
        w_conv = getattr(settings, "WEIGHT_CONVERSION_OPPORTUNITY", 0.25)
        w_perf = getattr(settings, "WEIGHT_PERFORMANCE_OPPORTUNITY", 0.20)
        w_seo = getattr(settings, "WEIGHT_SEO_OPPORTUNITY", 0.20)
        w_pay = getattr(settings, "WEIGHT_ABILITY_TO_PAY", 0.20)
        w_icp = getattr(settings, "WEIGHT_ICP_FIT", 0.10)
        w_a11y = getattr(settings, "WEIGHT_A11Y_OPPORTUNITY", 0.05)

        commercial_score = (
            (ux_opp * w_conv) +
            (perf_opp * w_perf) +
            (seo_opp * w_seo) +
            (ability_to_pay * w_pay) +
            (icp_score * w_icp) +
            (a11y_opp * w_a11y)
        )
        final_score = round(min(100.0, max(0.0, commercial_score)), 1)

        # Priority categorization based on commercial opportunity
        if final_score >= 85.0:
            priority = LeadPriority.A.value
        elif final_score >= 70.0:
            priority = LeadPriority.B.value
        elif final_score >= 55.0:
            priority = LeadPriority.C.value
        else:
            priority = LeadPriority.LOW.value

        breakdown = {
            "website_weakness_opp": round(website_weakness, 1),
            "seo_opp": round(seo_opp, 1),
            "a11y_opp": round(a11y_opp, 1),
            "performance_opp": round(perf_opp, 1),
            "ux_conversion_opp": round(ux_opp, 1),
            "ability_to_pay": round(ability_to_pay, 1),
            "icp_fit": round(icp_score, 1),
            "contactability": round(contactability, 1),
            "call_opportunity": {
                "call_driven_score": round(call_driven_score, 1),
                "call_value_potential": round(call_value_potential, 1),
                "after_hours_demand_likelihood": round(after_hours_demand, 1),
                "is_call_driven_icp": is_call_icp,
                "has_published_phone": bool(call_opp.get("has_published_phone")),
                "has_business_hours": has_hours,
                "after_hours_gap": after_hours_gap,
                "appointment_dependency": app_dep
            }
        }

        # Transparent rationale
        drivers = []
        if is_call_icp and call_driven_score >= 50.0:
            drivers.append(f"High-value call-driven ICP ({niche.name}, {call_driven_score:.0f}/100 opportunity score)")
        if after_hours_gap:
            drivers.append("Stated operating hours indicate potential after-hours missed-call opportunity")
        if app_dep:
            drivers.append("High appointment/inquiry booking dependency observed")
        if ux_opp >= 50:
            drivers.append(f"Major conversion friction ({ux_opp:.0f}% deficit)")
        if seo_opp >= 50:
            drivers.append(f"High local SEO expansion potential ({seo_opp:.0f}% deficit)")
        if perf_opp >= 50:
            drivers.append(f"Sub-par page speed/Core Web Vitals ({perf_opp:.0f}% deficit)")
        if ability_to_pay >= 70:
            drivers.append(f"High purchasing capacity in {country.name} {niche.name}")
        if contactability >= 80:
            drivers.append("Direct verified email available")

        rationale = (
            f"Lead Score: {final_score}/100 [Priority {priority}]. "
            f"Key justification: {'; '.join(drivers)}."
        )

        return final_score, priority, breakdown, rationale

    async def score_business(self, session: AsyncSession, business: Business) -> LeadScore:
        # Fetch latest audit run
        audit_q = select(AuditRun).where(AuditRun.business_id == business.id).order_by(AuditRun.audited_at.desc())
        audit = (await session.execute(audit_q)).scalars().first()

        if not audit:
            raise ValueError(f"Cannot score business {business.id}: No audit run found.")

        # Fetch country and niche
        country_q = select(Country).where(Country.code == business.country)
        country = (await session.execute(country_q)).scalar_one_or_none()
        if not country:
            # Fallback default country
            country = Country(code=business.country, name=business.country, gdp_per_capita=65000.0)

        niche_str = (business.niche or "").strip()
        niche_slug_norm = niche_str.lower().replace("_", "-")
        niche_q = select(Niche).where(
            (Niche.slug == niche_str) | 
            (Niche.slug == niche_slug_norm) |
            (Niche.slug.like(f"%{niche_slug_norm}%"))
        )
        niche_res = await session.execute(niche_q)
        try:
            niche = niche_res.scalars().first()
        except Exception:
            niche = None
        if not isinstance(niche, Niche):
            try:
                candidate = niche_res.scalar_one_or_none()
                if isinstance(candidate, Niche):
                    niche = candidate
            except Exception:
                pass
        if not isinstance(niche, Niche):
            from app.acquisition.targeting_catalog import NICHE_CATALOG, normalize_niche
            canon_id = normalize_niche(niche_str) or niche_str.upper()
            catalog_item = NICHE_CATALOG.get(canon_id)
            avg_deal = (
                float(catalog_item.min_estimated_service_value)
                if catalog_item and catalog_item.min_estimated_service_value
                else 1200.0
            )
            niche = Niche(
                slug=niche_slug_norm,
                name=catalog_item.name if catalog_item else niche_str,
                avg_deal_size=avg_deal
            )

        total_score, priority, breakdown, rationale = self.calculate_score(business, audit, country, niche)

        # If audit failed due to insufficient research, zero score immediately
        if audit.overall_health_score == 0.0 or "RESEARCH_INSUFFICIENT" in (audit.summary or ""):
            total_score = 0.0
            priority = LeadPriority.LOW.value
            rationale = "Disqualified: Research insufficient due to unreachable website."

        # Check for existing score
        score_q = select(LeadScore).where(LeadScore.business_id == business.id)
        lead_score = (await session.execute(score_q)).scalar_one_or_none()

        if not lead_score:
            lead_score = LeadScore(
                business_id=business.id,
                total_score=total_score,
                priority=priority,
                website_weakness_subscore=breakdown["website_weakness_opp"],
                seo_opportunity_subscore=breakdown["seo_opp"],
                a11y_opportunity_subscore=breakdown["a11y_opp"],
                performance_opportunity_subscore=breakdown["performance_opp"],
                conversion_opportunity_subscore=breakdown["ux_conversion_opp"],
                ability_to_pay_subscore=breakdown["ability_to_pay"],
                contactability_subscore=breakdown["contactability"],
                scoring_breakdown=breakdown,
                rationale=rationale
            )
            session.add(lead_score)
        else:
            lead_score.total_score = total_score
            lead_score.priority = priority
            lead_score.website_weakness_subscore = breakdown["website_weakness_opp"]
            lead_score.seo_opportunity_subscore = breakdown["seo_opp"]
            lead_score.a11y_opportunity_subscore = breakdown["a11y_opp"]
            lead_score.performance_opportunity_subscore = breakdown["performance_opp"]
            lead_score.conversion_opportunity_subscore = breakdown["ux_conversion_opp"]
            lead_score.ability_to_pay_subscore = breakdown["ability_to_pay"]
            lead_score.contactability_subscore = breakdown["contactability"]
            lead_score.scoring_breakdown = breakdown
            lead_score.rationale = rationale

        # Decouple commercial score from contactability routing:
        # Leads scoring >= 55.0 with verified public email are routed to QUALIFIED (ready for outreach drafting).
        # Leads scoring >= 55.0 without verified email are routed to RESEARCH_REQUIRED (enrichment queue, not rejected).
        # Leads scoring < 55.0 are commercially disqualified to REJECTED.
        old_stage = business.pipeline_stage
        has_verified_email = bool(business.public_email and str(business.email_status).lower() in ("verified", "valid", "deliverable"))

        if total_score >= 55.0:
            if has_verified_email:
                new_stage = PipelineStage.QUALIFIED.value
                business.pipeline_stage = new_stage
                business.research_status = "QUALIFIED"
                event = PipelineEvent(
                    business_id=business.id,
                    from_stage=old_stage,
                    to_stage=new_stage,
                    deal_value=niche.avg_deal_size,
                    note=f"Lead qualified with score {total_score}/100 (Priority {priority}) with verified contact ({business.public_email})."
                )
                session.add(event)
            else:
                new_stage = PipelineStage.RESEARCH_REQUIRED.value
                business.pipeline_stage = new_stage
                business.research_status = "RESEARCH_REQUIRED"
                event = PipelineEvent(
                    business_id=business.id,
                    from_stage=old_stage,
                    to_stage=new_stage,
                    deal_value=niche.avg_deal_size,
                    note=f"Lead commercially qualified ({total_score}/100, Priority {priority}) but held in RESEARCH_REQUIRED awaiting contact enrichment."
                )
                session.add(event)
        else:
            new_stage = PipelineStage.REJECTED.value
            business.pipeline_stage = new_stage
            event = PipelineEvent(
                business_id=business.id,
                from_stage=old_stage,
                to_stage=new_stage,
                deal_value=0.0,
                note=f"Lead disqualified: Score {total_score}/100 below 55.0 qualification floor or research insufficient."
            )
            session.add(event)

        await session.commit()
        logger.info(f"Scored {business.name}: {total_score}/100 (Priority {priority}, Stage: {business.pipeline_stage})")
        return lead_score

lead_scoring_engine = LeadScoringEngine()
