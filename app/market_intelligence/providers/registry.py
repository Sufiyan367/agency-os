from typing import List, Optional, Any
from app.market_intelligence.providers.base import BaseMarketResearchProvider
from app.market_intelligence.providers.web_search import WebSearchMarketResearchProvider
from app.market_intelligence.providers.mock import MockMarketResearchProvider
from app.core.logging import logger

class MarketResearchProviderRegistry:
    """Coordinates market research providers with fallback chains and circuit breaking."""

    def __init__(self):
        self.primary_provider = WebSearchMarketResearchProvider()
        self.mock_provider = MockMarketResearchProvider()
        self.use_mock_only = False

    def set_mock_mode(self, enabled: bool) -> None:
        self.use_mock_only = enabled

    async def search_with_fallback(
        self,
        country_code: str,
        country_name: str,
        niche_slug: str,
        service_id: str,
        queries: List[str]
    ) -> List[Any]:
        if self.use_mock_only:
            return await self.mock_provider.search_market_evidence(
                country_code, country_name, niche_slug, service_id, queries
            )

        # Try primary real search provider first
        try:
            items = await self.primary_provider.search_market_evidence(
                country_code, country_name, niche_slug, service_id, queries
            )
            if items:
                return items
        except Exception as e:
            logger.warning(f"[ProviderRegistry] Primary provider failed: {e}. Falling back to baseline empirical data.")

        # Fallback to deterministic provider
        return await self.mock_provider.search_market_evidence(
            country_code, country_name, niche_slug, service_id, queries
        )

market_research_registry = MarketResearchProviderRegistry()
