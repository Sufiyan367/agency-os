from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.market_intelligence.models import RawEvidenceItem

class BaseMarketResearchProvider(ABC):
    """Abstract base interface for public web and market research providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def get_health(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def search_market_evidence(
        self,
        country_code: str,
        country_name: str,
        niche_slug: str,
        service_id: str,
        queries: List[str]
    ) -> List[RawEvidenceItem]:
        pass
