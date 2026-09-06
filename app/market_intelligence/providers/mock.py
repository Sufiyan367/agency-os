from typing import List, Dict, Any
from datetime import datetime, timedelta
from app.market_intelligence.providers.base import BaseMarketResearchProvider
from app.market_intelligence.models import RawEvidenceItem, EvidenceTier

class MockMarketResearchProvider(BaseMarketResearchProvider):
    """
    Deterministic mock provider for unit tests and synthetic isolation.
    Ensures zero external cost, zero network dependence, and 100% reproducible tests.
    """

    def __init__(self):
        self.should_fail = False
        self.timeout = False
        self.call_count = 0

    @property
    def name(self) -> str:
        return "mock_market_provider"

    def is_available(self) -> bool:
        return not self.should_fail

    def get_health(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "available": not self.should_fail,
            "calls": self.call_count,
            "mock_mode": True
        }

    async def search_market_evidence(
        self,
        country_code: str,
        country_name: str,
        niche_slug: str,
        service_id: str,
        queries: List[str]
    ) -> List[RawEvidenceItem]:
        self.call_count += 1
        if self.timeout:
            import asyncio
            await asyncio.sleep(5)
            raise TimeoutError("Mock research provider simulated timeout.")
        if self.should_fail:
            raise RuntimeError("Mock research provider deliberate failure mode.")

        c = country_code.upper()
        clean_niche = niche_slug.replace("-", " ")
        now = datetime.utcnow()

        return [
            RawEvidenceItem(
                claim=f"{country_name} commercial {clean_niche} enterprises report high reliance on digital intake and 80%+ willingness to invest in AI qualification.",
                source_url=f"https://statista.com/market-outlook/{c.lower()}-{niche_slug}-automation",
                source_domain="statista.com",
                publisher="Statista Industry Intelligence",
                publication_date=now - timedelta(days=15),
                raw_excerpt=f"According to enterprise surveys across {country_name}, {clean_niche} operators face recurring missed lead costs and are actively adopting 24/7 AI qualification solutions.",
                signal_type="SERVICE_DEMAND",
                country_code=c,
                niche_slug=niche_slug,
                service_id=service_id,
                source_type="research_report",
                source_tier=EvidenceTier.TIER_1_OFFICIAL.value,
                supports_claim=True,
                confidence=0.92
            ),
            RawEvidenceItem(
                claim=f"{country_name} exhibits high digital maturity with fast adoption of automated CRM and scheduling workflows.",
                source_url=f"https://mckinsey.com/capabilities/digital/{c.lower()}-business-maturity",
                source_domain="mckinsey.com",
                publisher="McKinsey Digital Insights",
                publication_date=now - timedelta(days=40),
                raw_excerpt=f"Small and mid-size commercial firms in {country_name} show high ability-to-pay for turnkey operational automation that guarantees verified ROI.",
                signal_type="ABILITY_TO_PAY",
                country_code=c,
                niche_slug=niche_slug,
                service_id=service_id,
                source_type="research_report",
                source_tier=EvidenceTier.TIER_2_RESEARCH.value,
                supports_claim=True,
                confidence=0.88
            ),
            RawEvidenceItem(
                claim=f"High labor costs and skilled trade staffing shortages in {country_name} drive rapid automation ROI.",
                source_url=f"https://oecd.org/employment/{c.lower()}-labor-costs-2026",
                source_domain="oecd.org",
                publisher="OECD Employment Directorate",
                publication_date=now - timedelta(days=60),
                raw_excerpt=f"Elevated wage indexes and front-office recruitment challenges across {country_name} make software automation 3-5x more cost-efficient than additional administrative hires.",
                signal_type="LABOR_COST",
                country_code=c,
                niche_slug=niche_slug,
                service_id=service_id,
                source_type="government",
                source_tier=EvidenceTier.TIER_1_OFFICIAL.value,
                supports_claim=True,
                confidence=0.95
            ),
            RawEvidenceItem(
                claim=f"Agency saturation remains low to moderate for specialized {clean_niche} vertical AI workflows in {country_name}.",
                source_url=f"https://forbes.com/business/{c.lower()}-vertical-automation-opportunities",
                source_domain="forbes.com",
                publisher="Forbes Tech Council",
                publication_date=now - timedelta(days=20),
                raw_excerpt=f"While generic marketing agencies are saturated in {country_name}, domain-specific workflow automation for {clean_niche} remains highly underserved.",
                signal_type="COMPETITION",
                country_code=c,
                niche_slug=niche_slug,
                service_id=service_id,
                source_type="business_press",
                source_tier=EvidenceTier.TIER_2_RESEARCH.value,
                supports_claim=False, # Low competition means favorable penalty
                contradicts_claim=False,
                confidence=0.85
            ),
        ]

    async def fetch_evidence(self, country_code: str, country_name: str, niche_slug: str, service_id: str = "SERVICE_001", queries: List[str] = None) -> List[RawEvidenceItem]:
        return await self.search_market_evidence(country_code, country_name, niche_slug, service_id, queries or [])

