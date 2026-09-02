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

        # Weighted composite score
        raw_score = (
            (website_weakness * settings.WEIGHT_WEBSITE_WEAKNESS) +
            (seo_opp * settings.WEIGHT_SEO_OPPORTUNITY) +
            (a11y_opp * settings.WEIGHT_A11Y_OPPORTUNITY) +
            (perf_opp * settings.WEIGHT_PERFORMANCE_OPPORTUNITY) +
            (ux_opp * settings.WEIGHT_CONVERSION_OPPORTUNITY) +
            (ability_to_pay * settings.WEIGHT_ABILITY_TO_PAY)
        )

        # Apply contactability multiplier (if completely unreachable, cap priority)
        contact_multiplier = 0.6 + (contactability / 100.0) * 0.4
        final_score = round(min(100.0, max(0.0, raw_score * contact_multiplier)), 1)

        # Priority categorization
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
            "contactability": round(contactability, 1),
            "contact_multiplier": round(contact_multiplier, 2)
        }

        # Transparent rationale
        drivers = []
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

        niche_q = select(Niche).where(Niche.slug == business.niche)
        niche = (await session.execute(niche_q)).scalar_one_or_none()
        if not niche:
            niche = Niche(slug=business.niche, name=business.niche, avg_deal_size=800.0)

        total_score, priority, breakdown, rationale = self.calculate_score(business, audit, country, niche)

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

        # If qualified (score >= 55), transition pipeline stage
        old_stage = business.pipeline_stage
        if total_score >= 55.0:
            business.pipeline_stage = PipelineStage.QUALIFIED.value
            event = PipelineEvent(
                business_id=business.id,
                from_stage=old_stage,
                to_stage=PipelineStage.QUALIFIED.value,
                deal_value=niche.avg_deal_size,
                note=f"Lead qualified with score {total_score}/100 (Priority {priority})."
            )
            session.add(event)

        await session.commit()
        logger.info(f"Scored {business.name}: {total_score}/100 (Priority {priority})")
        return lead_score

lead_scoring_engine = LeadScoringEngine()
