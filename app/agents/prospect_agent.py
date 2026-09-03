"""
Single-Prospect Worker.
Executes Discovery, Verification, Diagnostic Auditing, Buyer Scoring, and Commercial Packaging
for exactly ONE prospect at a time.
"""
from typing import Optional, Tuple, Dict, Any, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.entities import LocalBusiness, LocalLead, LeadStatus
from app.database.models import Business, PipelineStage, LeadScore
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
    ) -> Optional[Union[Business, LocalBusiness]]:
        """
        Queries the single highest-value eligible uncontacted prospect in the local database.
        Identifies uncontacted prospects using canonical lifecycle states:
        - For Business: checks pipeline_stage is in an uncontacted stage (DISCOVERED, VERIFIED, AUDITED, QUALIFIED, OUTREACH_READY).
        - For LocalBusiness: checks associated LocalLead records to ensure status != CONTACTED.
        """
        # 1. Query canonical Business table for uncontacted prospects
        q_biz = (
            select(Business)
            .outerjoin(LeadScore, Business.id == LeadScore.business_id)
            .where(
                Business.pipeline_stage.in_([
                    PipelineStage.DISCOVERED.value,
                    PipelineStage.VERIFIED.value,
                    PipelineStage.AUDITED.value,
                    PipelineStage.QUALIFIED.value,
                    PipelineStage.OUTREACH_READY.value
                ])
            )
            .order_by(
                LeadScore.total_score.desc().nullslast(),
                Business.id.asc()
            )
            .limit(1)
        )
        res_biz = await db.execute(q_biz)
        cand_biz = res_biz.scalars().first()
        if cand_biz:
            return cand_biz

        # 2. Fall back to LocalBusiness table for uncontacted leads
        q_local = (
            select(LocalBusiness)
            .outerjoin(LocalLead, LocalBusiness.id == LocalLead.business_id)
            .where(
                or_(
                    LocalLead.status == None,
                    LocalLead.status.in_([
                        LeadStatus.NEW.value,
                        LeadStatus.VERIFIED.value,
                        LeadStatus.AUDITED.value,
                        LeadStatus.SCORED.value,
                        LeadStatus.QUALIFIED.value,
                        LeadStatus.APPROVED.value
                    ])
                )
            )
            .where(
                or_(
                    LocalLead.status == None,
                    LocalLead.status != LeadStatus.CONTACTED.value
                )
            )
            .order_by(
                LocalLead.lead_score.desc().nullslast(),
                LocalBusiness.id.asc()
            )
            .limit(1)
        )
        res_local = await db.execute(q_local)
        return res_local.scalars().first()

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
