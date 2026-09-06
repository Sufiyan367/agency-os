from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import CountryMarketProfile, NicheMarketProfile
from app.core.logging import logger

class DynamicMarketDiscovery:
    """
    Discovers candidate markets and niches outside the initial seed lists
    based on high digital maturity, strong ability-to-pay, and automation demand signals.
    """

    CANDIDATE_COUNTRIES = [
        {"code": "SE", "name": "Sweden", "region": "Europe", "currency": "SEK", "tz": "Europe/Stockholm", "langs": ["sv", "en"], "rationale": "High AI adoption and cashless commercial operations."},
        {"code": "NO", "name": "Norway", "region": "Europe", "currency": "NOK", "tz": "Europe/Oslo", "langs": ["no", "en"], "rationale": "High GDP per capita and high labor costs creating strong automation ROI."},
        {"code": "CH", "name": "Switzerland", "region": "Europe", "currency": "CHF", "tz": "Europe/Zurich", "langs": ["de", "fr", "en"], "rationale": "Exceptional purchasing power and dense SME corporate base."},
        {"code": "DK", "name": "Denmark", "region": "Europe", "currency": "DKK", "tz": "Europe/Copenhagen", "langs": ["da", "en"], "rationale": "Advanced public digital infrastructure and active B2B digitization."},
    ]

    CANDIDATE_NICHES = [
        {"slug": "specialty-subcontractors", "name": "Specialty Subcontractors", "cat": "Construction", "lead_val": 3000.0, "pain": 0.85, "automation": 0.80, "atp": 0.80, "services": ["SERVICE_001", "SERVICE_004", "SERVICE_005"]},
        {"slug": "veterinary-hospitals", "name": "Veterinary Hospitals", "cat": "Healthcare", "lead_val": 1500.0, "pain": 0.80, "automation": 0.90, "atp": 0.85, "services": ["SERVICE_002", "SERVICE_006"]},
        {"slug": "solar-installation", "name": "Commercial Solar Installation", "cat": "Energy", "lead_val": 6000.0, "pain": 0.90, "automation": 0.85, "atp": 0.90, "services": ["SERVICE_001", "SERVICE_003"]},
    ]

    async def discover_new_candidate_markets(self, session: AsyncSession) -> List[Dict[str, Any]]:
        existing_codes = set((await session.execute(select(CountryMarketProfile.country_code))).scalars().all())
        discovered = []

        for cand in self.CANDIDATE_COUNTRIES:
            if cand["code"] not in existing_codes:
                profile = CountryMarketProfile(
                    country_code=cand["code"],
                    country_name=cand["name"],
                    region=cand["region"],
                    currency=cand["currency"],
                    timezone=cand["tz"],
                    primary_languages=cand["langs"],
                    research_status="CANDIDATE",
                    confidence=0.5,
                    metadata_json={"discovery_rationale": cand["rationale"], "auto_recommended": True}
                )
                session.add(profile)
                discovered.append(cand)

        await session.flush()
        logger.info(f"[DynamicDiscovery] Discovered {len(discovered)} new candidate market countries.")
        return discovered

    async def discover_new_candidate_niches(self, session: AsyncSession) -> List[Dict[str, Any]]:
        existing_slugs = set((await session.execute(select(NicheMarketProfile.niche_slug))).scalars().all())
        discovered = []

        for cand in self.CANDIDATE_NICHES:
            if cand["slug"] not in existing_slugs:
                profile = NicheMarketProfile(
                    niche_slug=cand["slug"],
                    name=cand["name"],
                    category=cand["cat"],
                    typical_lead_value_usd=cand["lead_val"],
                    missed_lead_pain_severity=cand["pain"],
                    automation_potential=cand["automation"],
                    baseline_ability_to_pay=cand["atp"],
                    suitable_services=cand["services"],
                    research_status="CANDIDATE",
                    metadata_json={"auto_recommended": True}
                )
                session.add(profile)
                discovered.append(cand)

        await session.flush()
        logger.info(f"[DynamicDiscovery] Discovered {len(discovered)} new candidate niches.")
        return discovered

dynamic_market_discovery = DynamicMarketDiscovery()
