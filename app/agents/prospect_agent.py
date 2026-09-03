"""
Single-Prospect Worker.
Executes Discovery, Verification, Diagnostic Auditing, Buyer Scoring, and Commercial Packaging
for exactly ONE prospect at a time.
"""
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.entities import LocalBusiness
from app.lead_generation.service import LeadDiscoveryService, ProspectQualityFilter
from app.lead_generation.buyer_scoring import HighValueBuyerScorer
from app.lead_generation.targeting import TargetingConfig, load_targeting_config
from app.lead_generation.providers.prospect_provider import RealProspectProvider, MockProspectProvider


class SingleProspectAgent:
    """Processes prospects strictly one-at-a-time."""

    def __init__(self, provider_type: str = "mock"):
        self.provider = MockProspectProvider() if provider_type == "mock" else RealProspectProvider()
        self.service = LeadDiscoveryService(provider=self.provider)

    async def get_next_uncontacted_prospect(
        self,
        db: AsyncSession,
        commercial_floor: float = 500.0
    ) -> Optional[LocalBusiness]:
        """Queries the single highest-value eligible prospect in the local database."""
        q = (
            select(LocalBusiness)
            .where(LocalBusiness.contacted == False)
            .where(LocalBusiness.pipeline_stage.in_(["DISCOVERED", "LEAD"]))
            .order_by(LocalBusiness.lead_score.desc().nullslast(), LocalBusiness.id.asc())
            .limit(1)
        )
        res = await db.execute(q)
        return res.scalar_one_or_none()

    async def discover_single_candidate(
        self,
        country: str,
        city: str,
        niche: str
    ) -> Optional[Dict[str, Any]]:
        """Queries the provider for candidates and returns exactly the first valid un-audited business."""
        candidates = await self.provider.discover_prospects(country=country, city=city, niche=niche, limit=5)
        for cand in candidates:
            norm_dom = self.service.normalize_domain(cand.website or cand.domain)
            is_valid, _ = ProspectQualityFilter.check_validity(norm_dom, cand.website)
            if is_valid:
                return {
                    "name": cand.business_name,
                    "domain": norm_dom,
                    "website": cand.website or f"https://{norm_dom}",
                    "phone": cand.phone,
                    "email": cand.email,
                    "city": cand.city,
                    "country": cand.country,
                    "niche": cand.category
                }
        return None
