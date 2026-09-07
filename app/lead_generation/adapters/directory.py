from typing import List
from app.lead_generation.adapters.base import BaseLeadDiscoveryAdapter, DiscoveredLeadRaw
from app.core.security import normalize_domain

class DirectoryDiscoveryAdapter(BaseLeadDiscoveryAdapter):
    """
    Simulates / integrates structured business directory feeds
    for local trade associations and business chambers.
    """
    async def discover_leads(
        self, country_code: str, niche_slug: str, limit: int = 10
    ) -> List[DiscoveredLeadRaw]:
        # Real-data-only enforcement: do NOT synthesize placeholder businesses
        # When no active external directory feed is connected, return empty candidate list
        return []
