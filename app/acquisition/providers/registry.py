from typing import List, Dict, Any, Optional, Set
from app.acquisition.providers.base import BaseDiscoveryProvider
from app.acquisition.providers.existing_adapter import ExistingDiscoveryAdapterProvider
from app.acquisition.providers.scrapegraph_provider import ScrapeGraphProvider
from app.acquisition.models import StandardizedProspect
from app.core.logging import logger

class DiscoveryProviderRegistry:
    """
    Coordinates discovery across registered providers with prioritized fallback.
    Never fails completely if at least one provider is operational.
    """

    def __init__(self):
        self.scrapegraph = ScrapeGraphProvider()
        self.existing_adapter = ExistingDiscoveryAdapterProvider()
        self.providers: List[BaseDiscoveryProvider] = [
            self.scrapegraph,
            self.existing_adapter
        ]

    def register_provider(self, provider: BaseDiscoveryProvider, priority_index: int = 0) -> None:
        self.providers.insert(priority_index, provider)

    def get_provider(self, name: str) -> Optional[BaseDiscoveryProvider]:
        for p in self.providers:
            if p.name == name:
                return p
        return None

    def get_providers_health(self) -> List[Dict[str, Any]]:
        return [p.get_health() for p in self.providers]

    async def execute_discovery_with_fallback(
        self,
        country_code: str,
        niche: str,
        limit: int = 10,
        cities: Optional[List[str]] = None,
        exclude_domains: Optional[Set[str]] = None
    ) -> List[StandardizedProspect]:
        """
        Attempts discovery through providers in order of priority.
        If ScrapeGraph is available and configured, uses it; otherwise falls back gracefully.
        """
        excluded = set(exclude_domains or [])
        combined_results: List[StandardizedProspect] = []

        for provider in self.providers:
            if len(combined_results) >= limit:
                break

            if not provider.is_available():
                continue

            needed = limit - len(combined_results)
            try:
                leads = await provider.discover_prospects(
                    country_code=country_code,
                    niche=niche,
                    limit=needed,
                    cities=cities,
                    exclude_domains=excluded
                )
                for l in leads:
                    if l.domain not in excluded:
                        combined_results.append(l)
                        excluded.add(l.domain)
            except Exception as e:
                logger.warning(f"[DiscoveryRegistry] Provider '{provider.name}' failed gracefully: {e}")

        return combined_results[:limit]

discovery_registry = DiscoveryProviderRegistry()
