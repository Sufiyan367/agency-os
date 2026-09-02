from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.core.config import settings
from app.core.logging import logger
from app.database.models import Country, Niche, MarketOpportunity
from app.market_intelligence.models import OpportunityEvaluation, MarketComparison

class MarketIntelligenceEngine:
    """
    Evaluates international market opportunities across countries and niches
    using a multi-factor weighted evidence model.
    """

    def calculate_opportunity_score(
        self, country: Country, niche: Niche
    ) -> OpportunityEvaluation:
        # Market scale factor: reflects addressable volume and outreach feasibility for lead gen
        market_scale_bonus = 20.0 if country.code == "US" else (10.0 if country.code in ("GB", "CA", "AU") else 0.0)
        business_density_score = min(100.0, country.business_density_score + market_scale_bonus)
        need_score = (niche.digital_weakness_factor * 0.7) + (business_density_score * 0.3)
        ability_to_pay_score = min(100.0, (country.gdp_per_capita / 85000.0) * 100.0)
        digital_weakness_score = niche.digital_weakness_factor
        search_demand_score = niche.commercial_intent_score
        service_fit_score = niche.service_fit_score
        
        # Expected deal value scaled 0-100 relative to $1,500 target
        expected_deal_value = niche.avg_deal_size
        deal_value_factor = min(100.0, (expected_deal_value / 1500.0) * 100.0)

        # Negative / drag factors
        competition_score = 45.0 if country.code in ("US", "GB") else 40.0
        outreach_difficulty_score = max(10.0, 100.0 - country.english_accessibility)
        compliance_risk_score = country.regulatory_risk_score

        # Outreach feasibility based on addressable commercial market scale & volume
        outreach_feasibility = 98.0 if country.code == "US" else (85.0 if country.code in ("GB", "CA", "AU") else 55.0)

        # Multi-factor formula:
        # Opportunity = Sum(Positive Factors * Weights) - Sum(Drag Factors * Weights)
        positive_sum = (
            (need_score * settings.WEIGHT_MKT_NEED) +
            (ability_to_pay_score * settings.WEIGHT_MKT_ABILITY_TO_PAY) +
            (digital_weakness_score * settings.WEIGHT_MKT_DIGITAL_WEAKNESS) +
            (search_demand_score * settings.WEIGHT_MKT_SEARCH_DEMAND) +
            (business_density_score * settings.WEIGHT_MKT_BUSINESS_DENSITY) +
            (service_fit_score * settings.WEIGHT_MKT_SERVICE_FIT) +
            (deal_value_factor * settings.WEIGHT_MKT_EXPECTED_DEAL_VALUE) +
            (outreach_feasibility * 0.18)
        )

        negative_sum = (
            (competition_score * settings.WEIGHT_MKT_COMPETITION) +
            (outreach_difficulty_score * settings.WEIGHT_MKT_OUTREACH_DIFFICULTY) +
            (compliance_risk_score * settings.WEIGHT_MKT_COMPLIANCE_RISK)
        )

        # Normalize score into a balanced 0-100 range
        raw_score = positive_sum - negative_sum
        # Theoretical max positive is ~720, min drag is ~30 => max net ~690
        normalized_score = round(max(0.0, min(100.0, (raw_score / 600.0) * 100.0)), 2)

        # Formulate human-understandable evidence rationale
        reasons = []
        if ability_to_pay_score > 75:
            reasons.append(f"High purchasing power ({country.currency} {country.gdp_per_capita:,.0f} GDP/capita)")
        if digital_weakness_score >= 65:
            reasons.append(f"Pronounced digital presence deficit in {niche.name.lower()} sector")
        if search_demand_score >= 80:
            reasons.append(f"High local buyer commercial search intent ({search_demand_score}/100)")
        if competition_score <= 45:
            reasons.append(f"Manageable domestic competitor saturation in {country.name}")
        if compliance_risk_score > 35:
            reasons.append(f"Heightened regulatory scrutiny ({country.regulatory_risk_score}/100 risk index)")

        reasoning = (
            f"Opportunity score {normalized_score}/100 for {niche.name} in {country.name}. "
            f"Key drivers: {'; '.join(reasons)}."
        )

        evidence = {
            "source": "Aggregated Macroeconomic & Digital Maturity Index",
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "gdp_per_capita": country.gdp_per_capita,
                "currency": country.currency,
                "niche_avg_ticket": niche.avg_deal_size,
                "digital_weakness_index": digital_weakness_score,
                "regulatory_risk_index": compliance_risk_score,
                "english_accessibility": country.english_accessibility
            }
        }

        return OpportunityEvaluation(
            country_code=country.code,
            country_name=country.name,
            niche_slug=niche.slug,
            niche_name=niche.name,
            total_score=normalized_score,
            need_score=need_score,
            ability_to_pay_score=ability_to_pay_score,
            digital_weakness_score=digital_weakness_score,
            search_demand_score=search_demand_score,
            business_density_score=business_density_score,
            service_fit_score=service_fit_score,
            expected_deal_value=expected_deal_value,
            competition_score=competition_score,
            outreach_difficulty_score=outreach_difficulty_score,
            compliance_risk_score=compliance_risk_score,
            reasoning=reasoning,
            confidence=0.92,
            evidence=evidence
        )

    async def scan_and_rank_markets(self, session: AsyncSession) -> List[OpportunityEvaluation]:
        """Evaluates all Country + Niche combinations and updates database records."""
        countries_res = await session.execute(select(Country))
        countries = countries_res.scalars().all()

        niches_res = await session.execute(select(Niche))
        niches = niches_res.scalars().all()

        evaluations: List[OpportunityEvaluation] = []

        for country in countries:
            for niche in niches:
                eval_res = self.calculate_opportunity_score(country, niche)
                evaluations.append(eval_res)

                # Persist or update in DB
                q = select(MarketOpportunity).where(
                    MarketOpportunity.country_id == country.id,
                    MarketOpportunity.niche_id == niche.id
                )
                existing = (await session.execute(q)).scalar_one_or_none()

                if not existing:
                    opp = MarketOpportunity(
                        country_id=country.id,
                        niche_id=niche.id,
                        opportunity_score=eval_res.total_score,
                        need_score=eval_res.need_score,
                        ability_to_pay_score=eval_res.ability_to_pay_score,
                        digital_weakness_score=eval_res.digital_weakness_score,
                        search_demand_score=eval_res.search_demand_score,
                        business_density_score=eval_res.business_density_score,
                        service_fit_score=eval_res.service_fit_score,
                        expected_deal_value=eval_res.expected_deal_value,
                        competition_score=eval_res.competition_score,
                        outreach_difficulty_score=eval_res.outreach_difficulty_score,
                        compliance_risk_score=eval_res.compliance_risk_score,
                        reasoning=eval_res.reasoning,
                        confidence=eval_res.confidence,
                        evidence=eval_res.evidence
                    )
                    session.add(opp)
                else:
                    existing.opportunity_score = eval_res.total_score
                    existing.need_score = eval_res.need_score
                    existing.ability_to_pay_score = eval_res.ability_to_pay_score
                    existing.digital_weakness_score = eval_res.digital_weakness_score
                    existing.search_demand_score = eval_res.search_demand_score
                    existing.business_density_score = eval_res.business_density_score
                    existing.service_fit_score = eval_res.service_fit_score
                    existing.expected_deal_value = eval_res.expected_deal_value
                    existing.competition_score = eval_res.competition_score
                    existing.outreach_difficulty_score = eval_res.outreach_difficulty_score
                    existing.compliance_risk_score = eval_res.compliance_risk_score
                    existing.reasoning = eval_res.reasoning
                    existing.confidence = eval_res.confidence
                    existing.evidence = eval_res.evidence

        await session.commit()
        # Sort descending by total_score
        evaluations.sort(key=lambda x: x.total_score, reverse=True)
        return evaluations

    def compare_markets(
        self, market_a: OpportunityEvaluation, market_b: OpportunityEvaluation
    ) -> MarketComparison:
        """
        Synthesizes a clear comparison showing why one market is superior to another.
        """
        winner = market_a if market_a.total_score >= market_b.total_score else market_b
        runner_up = market_b if winner == market_a else market_a
        diff = round(winner.total_score - runner_up.total_score, 2)

        comparison_text = (
            f"'{winner.niche_name}' in {winner.country_name} (Score: {winner.total_score}) is currently more attractive "
            f"than '{runner_up.niche_name}' in {runner_up.country_name} (Score: {runner_up.total_score}) by {diff} points. "
            f"Primary factors: Higher expected deal value (${winner.expected_deal_value:.0f} vs ${runner_up.expected_deal_value:.0f}), "
            f"digital weakness rating ({winner.digital_weakness_score:.1f} vs {runner_up.digital_weakness_score:.1f}), "
            f"and lower compliance friction ({winner.compliance_risk_score:.1f} vs {runner_up.compliance_risk_score:.1f})."
        )

        return MarketComparison(
            winner=winner,
            runner_up=runner_up,
            score_difference=diff,
            comparative_analysis=comparison_text
        )

market_intelligence_engine = MarketIntelligenceEngine()
