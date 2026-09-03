from abc import ABC, abstractmethod
from typing import List
from app.lead_generation.targeting import TargetingConfig
from app.lead_generation.schemas import NormalizedBusinessRecord

class BaseLeadDiscoveryProvider(ABC):
    """
    Abstract Lead Discovery Provider.
    Enforces provider independence so directories, search engines, or APIs
    can be swapped without modifying core business logic.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def discover_businesses(self, targeting: TargetingConfig) -> List[NormalizedBusinessRecord]:
        """Discovers and returns a raw list of normalized business records."""
        pass
