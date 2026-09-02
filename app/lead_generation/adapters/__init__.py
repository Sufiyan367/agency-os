from app.lead_generation.adapters.base import BaseLeadDiscoveryAdapter, DiscoveredLeadRaw
from app.lead_generation.adapters.real_web_discovery import RealWebDiscoveryAdapter
from app.lead_generation.adapters.directory import DirectoryDiscoveryAdapter
from app.lead_generation.adapters.web_search import WebSearchDiscoveryAdapter

__all__ = [
    "BaseLeadDiscoveryAdapter",
    "DiscoveredLeadRaw",
    "RealWebDiscoveryAdapter",
    "DirectoryDiscoveryAdapter",
    "WebSearchDiscoveryAdapter"
]
