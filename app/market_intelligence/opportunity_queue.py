from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database.models import CountryNicheOpportunity, Business
from app.acquisition.pool import global_prospect_pool
from app.core.logging import logger

class GlobalOpportunityQueueManager:
    """Manages the ranked Country x Niche x Service opportunity scoreboard."""

    async def get_ranked_queue(
        self,
        session: AsyncSession,
        limit: int = 50,
        country_code: Optional[str] = None,
        niche_slug: Optional[str] = None,
        service_id: Optional[str] = None,
        min_score: Optional[float] = None
    ) -> List[CountryNicheOpportunity]:
        stmt = select(CountryNicheOpportunity)
        conditions = []

        if country_code:
            conditions.append(CountryNicheOpportunity.country_code == country_code.upper())
        if niche_slug:
            conditions.append(CountryNicheOpportunity.niche_slug == niche_slug)
        if service_id:
            conditions.append(CountryNicheOpportunity.service_id == service_id)
        if min_score is not None:
            conditions.append(CountryNicheOpportunity.market_score >= min_score)

        if conditions:
            stmt = stmt.where(*conditions)

        stmt = stmt.order_by(
            CountryNicheOpportunity.expected_value_usd.desc(),
            CountryNicheOpportunity.market_score.desc()
        ).limit(limit)

        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def feed_phase10_pool(
        self,
        session: AsyncSession,
        top_n: int = 3,
        target_per_country: int = 2
    ) -> List[Business]:
        """
        Selects the top-ranked opportunities from market intelligence and triggers
        Phase 10 real prospect discovery for those exact country x niche targets.
        """
        top_opps = await self.get_ranked_queue(session, limit=top_n)
        if not top_opps:
            logger.warning("[OpportunityQueue] No ranked opportunities available to feed Phase 10.")
            return []

        discovered_all: List[Business] = []
        for opp in top_opps:
            logger.info(f"[OpportunityQueue] Feeding Phase 10: {opp.country_code} x {opp.niche_slug} (Target Service: {opp.service_id}, EV: ${opp.expected_value_usd:,.2f})")
            businesses = await global_prospect_pool.discover_across_countries(
                session=session,
                countries=[opp.country_code],
                niche=opp.niche_slug,
                target_per_country=target_per_country
            )
            discovered_all.extend(businesses)

        return discovered_all

global_opportunity_queue = GlobalOpportunityQueueManager()
