from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.acquisition.models import StandardizedProspect

class BaseDiscoveryProvider(ABC):
    """
    Abstract interface for public prospect discovery providers.
    Supports existing web search adapters, ScrapeGraphAI, and future enrichment services.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier for the discovery provider."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider is configured and operational."""
        pass

    @abstractmethod
    async def discover_prospects(
        self,
        country_code: str,
        niche: str,
        limit: int = 10,
        cities: Optional[List[str]] = None,
        exclude_domains: Optional[set] = None
    ) -> List[StandardizedProspect]:
        """
        Executes public web discovery and returns standardized prospect objects.
        Must never throw unhandled exceptions to callers.
        """
        pass

    @abstractmethod
    def get_health(self) -> Dict[str, Any]:
        """Returns provider diagnostic health telemetry."""
        pass
