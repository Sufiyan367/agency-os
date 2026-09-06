import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models import (
    CountryMarketProfile, NicheMarketProfile, CountryNicheOpportunity,
    MarketResearchRun, MarketEvidence
)
from app.market_intelligence.config import SEED_MARKET_UNIVERSE, SEED_NICHES
from app.market_intelligence.providers.registry import market_research_registry
from app.market_intelligence.evidence_collector import evidence_collector
from app.market_intelligence.market_signal_extractor import market_signal_extractor
from app.market_intelligence.market_opportunity_scorer import market_opportunity_scorer
from app.market_intelligence.localization import market_localization
from app.market_intelligence.compliance_profile import compliance_profile_manager
from app.market_intelligence.decision_trace import market_decision_trace_builder
from app.market_intelligence.cost_guard import market_cost_guard
from app.client_intelligence.catalog import SERVICE_CATALOG
from app.core.logging import logger

class MarketResearchEngine:
    """
    Master production orchestrator for Global Market Intelligence.
    Coordinates universe loading, real web research, evidence storage,
    signal extraction, transparent scoring, and opportunity queue ranking.
    """

    async def ensure_seed_universe(self, session: AsyncSession) -> None:
        """Seeds the initial universe of 18+ countries and niches with neutral priors if empty."""
        for c_seed in SEED_MARKET_UNIVERSE:
            stmt = select(CountryMarketProfile).where(CountryMarketProfile.country_code == c_seed["code"])
            existing = (await session.execute(stmt)).scalars().first()
            if not existing:
                prof = CountryMarketProfile(
                    country_code=c_seed["code"],
                    country_name=c_seed["name"],
                    region=c_seed["region"],
                    currency=c_seed["currency"],
                    timezone=c_seed["tz"],
                    primary_languages=c_seed["langs"],
                    compliance_risk_signal=c_seed.get("compliance_prior", "LOW"),
                    research_status="CURRENT",
                    confidence=0.75,
                    research_timestamp=datetime.utcnow(),
                    next_refresh_at=datetime.utcnow() + timedelta(days=90),
                    metadata_json={"seed_prior": True}
                )
                session.add(prof)

        for n_seed in SEED_NICHES:
            stmt = select(NicheMarketProfile).where(NicheMarketProfile.niche_slug == n_seed["slug"])
            existing = (await session.execute(stmt)).scalars().first()
            if not existing:
                niche = NicheMarketProfile(
                    niche_slug=n_seed["slug"],
                    name=n_seed["name"],
                    category=n_seed["cat"],
                    typical_lead_value_usd=n_seed["lead_val"],
                    missed_lead_pain_severity=n_seed["pain"],
                    automation_potential=n_seed["automation"],
                    baseline_ability_to_pay=n_seed["atp"],
                    suitable_services=n_seed["services"],
                    research_status="CURRENT",
                    metadata_json={"seed_prior": True}
                )
                session.add(niche)

        await session.commit()

    async def research_opportunity(
        self,
        session: AsyncSession,
        country_code: str,
        niche_slug: str,
        service_id: str,
        force_refresh: bool = False
    ) -> CountryNicheOpportunity:
        """Researches, scores, and persists a singular Country x Niche x Service combination."""
        c_code = country_code.upper()
        opp_key = f"{c_code}:{niche_slug}:{service_id}"

        # 1. Fetch metadata
        c_stmt = select(CountryMarketProfile).where(CountryMarketProfile.country_code == c_code)
        c_prof = (await session.execute(c_stmt)).scalars().first()
        country_name = c_prof.country_name if c_prof else c_code
        lang = c_prof.primary_languages[0] if (c_prof and c_prof.primary_languages) else "en"

        n_stmt = select(NicheMarketProfile).where(NicheMarketProfile.niche_slug == niche_slug)
        n_prof = (await session.execute(n_stmt)).scalars().first()
        niche_name = n_prof.name if n_prof else niche_slug.replace("-", " ").title()

        niche_meta = {
            "atp": getattr(n_prof, "baseline_ability_to_pay", 0.8),
            "pain": getattr(n_prof, "missed_lead_pain_severity", 0.8),
            "automation": getattr(n_prof, "automation_potential", 0.8)
        }
        country_meta = {"currency": c_prof.currency if c_prof else "USD"}

        # 2. Check if fresh existing opportunity exists
        stmt_opp = select(CountryNicheOpportunity).where(CountryNicheOpportunity.opportunity_key == opp_key)
        existing_opp = (await session.execute(stmt_opp)).scalars().first()

        if existing_opp and not force_refresh:
            if existing_opp.updated_at > (datetime.utcnow() - timedelta(days=30)):
                return existing_opp

        # 3. Generate localized queries and fetch evidence from providers
        queries = market_localization.get_queries(c_code, country_name, niche_slug, lang=lang)
        raw_evidence = await market_research_registry.search_with_fallback(
            country_code=c_code,
            country_name=country_name,
            niche_slug=niche_slug,
            service_id=service_id,
            queries=queries
        )

        # 4. Save evidence records
        saved_evidence: List[MarketEvidence] = []
        for r in raw_evidence:
            ev_rec, _ = await evidence_collector.add_evidence(session, r)
            if ev_rec:
                saved_evidence.append(ev_rec)

        # 5. Extract normalized signals
        all_ev = await evidence_collector.get_evidence_for_opportunity(session, c_code, niche_slug, service_id)
        signals = market_signal_extractor.extract_signals_from_evidence(all_ev)

        # 6. Assess compliance risk
        risk_profile = compliance_profile_manager.assess_risk(c_code, niche_slug)

        # 7. Compute scoring & EV
        score_res = market_opportunity_scorer.calculate_opportunity(
            signals=signals,
            niche_meta=niche_meta,
            country_meta=country_meta,
            service_id=service_id,
            compliance_risk_penalty=risk_profile["compliance_penalty"]
        )

        # 8. Build decision trace
        catalog_item = SERVICE_CATALOG.get(service_id)
        service_name = catalog_item.name if catalog_item else service_id
        trace = market_decision_trace_builder.build_trace(
            country_name=country_name,
            niche_name=niche_name,
            service_name=service_name,
            service_id=service_id,
            market_score=score_res["market_score"],
            expected_deal_usd=score_res["expected_deal_value_usd"],
            ev_usd=score_res["expected_value_usd"],
            confidence=score_res["confidence"],
            signals={k: v.value for k, v in signals.items() if v.value is not None},
            evidence_sources=[e.source_domain for e in all_ev],
            risks=[risk_profile["compliance_note"]]
        )

        # 9. Persist opportunity
        if not existing_opp:
            existing_opp = CountryNicheOpportunity(
                country_code=c_code,
                niche_slug=niche_slug,
                service_id=service_id,
                opportunity_key=opp_key
            )
            session.add(existing_opp)

        existing_opp.market_score = score_res["market_score"]
        existing_opp.demand_score = score_res["demand_score"]
        existing_opp.ability_to_pay_score = score_res["ability_to_pay_score"]
        existing_opp.automation_score = score_res["automation_score"]
        existing_opp.ai_adoption_score = score_res["ai_adoption_score"]
        existing_opp.digital_maturity_score = score_res["digital_maturity_score"]
        existing_opp.business_density_score = score_res["business_density_score"]
        existing_opp.pain_probability_score = score_res["pain_probability_score"]
        existing_opp.growth_score = score_res["growth_score"]
        existing_opp.contactability_score = score_res["contactability_score"]
        existing_opp.competition_penalty = score_res["competition_penalty"]
        existing_opp.compliance_penalty = score_res["compliance_penalty"]
        existing_opp.uncertainty_penalty = score_res["uncertainty_penalty"]
        existing_opp.expected_deal_value_usd = score_res["expected_deal_value_usd"]
        existing_opp.p_contact = score_res["p_contact"]
        existing_opp.p_fit = score_res["p_fit"]
        existing_opp.p_deal = score_res["p_deal"]
        existing_opp.expected_value_usd = score_res["expected_value_usd"]
        existing_opp.confidence = score_res["confidence"]
        existing_opp.research_status = "CURRENT"
        existing_opp.evidence_count = len(all_ev)
        existing_opp.freshest_evidence_at = max([e.retrieved_at for e in all_ev], default=datetime.utcnow())
        existing_opp.decision_trace = trace
        existing_opp.scoring_weights = score_res["scoring_weights"]

        await session.commit()
        return existing_opp

    async def run_full_refresh(
        self,
        session: AsyncSession,
        target_countries: Optional[List[str]] = None,
        target_niches: Optional[List[str]] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """Runs comprehensive research across selected or top universe pairs."""
        run_id = f"RUN-MKT-{uuid.uuid4().hex[:8].upper()}"
        start_time = datetime.utcnow()
        market_cost_guard.reset()

        await self.ensure_seed_universe(session)

        run_rec = MarketResearchRun(
            run_id=run_id,
            status="RUNNING",
            countries_researched=target_countries or ["US", "AE", "UK"],
            niches_researched=target_niches or ["roofing", "hvac", "real-estate"]
        )
        session.add(run_rec)
        await session.commit()

        created_count = 0
        evidence_count = 0

        countries = target_countries or ["US", "AE", "UK"]
        niches = target_niches or ["roofing", "hvac", "real-estate"]
        services = ["SERVICE_001", "SERVICE_003", "SERVICE_006"]

        try:
            for c in countries:
                for n in niches:
                    for s in services:
                        opp = await self.research_opportunity(session, c, n, s, force_refresh=force)
                        created_count += 1
                        evidence_count += opp.evidence_count

            run_rec.status = "COMPLETED"
            run_rec.opportunities_created = created_count
            run_rec.evidence_collected = evidence_count
            run_rec.requests_made = market_cost_guard.requests_made
            run_rec.total_cost_usd = market_cost_guard.get_cost_usd()
            run_rec.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            run_rec.completed_at = datetime.utcnow()
            await session.commit()

            return {
                "run_id": run_id,
                "status": "COMPLETED",
                "opportunities_scored": created_count,
                "evidence_items": evidence_count,
                "cost_usd": run_rec.total_cost_usd,
                "duration_seconds": run_rec.duration_seconds
            }
        except Exception as e:
            run_rec.status = "FAILED"
            run_rec.error_message = str(e)
            run_rec.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            await session.commit()
            logger.error(f"[MarketResearchEngine] Run {run_id} failed: {e}")
            raise

market_research_engine = MarketResearchEngine()
