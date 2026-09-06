from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field
from datetime import datetime

class DiscoveredLeadRaw(BaseModel):
    name: str
    domain: str
    website_url: str
    country: str
    city: str
    niche: str
    public_email: str | None = None
    email_status: str = "unknown"
    phone: str | None = None
    contact_page_url: str | None = None
    address: str | None = None
    social_profiles: Dict[str, Any] = Field(default_factory=dict)
    source: str
    source_url: str | None = None
    discovery_timestamp: datetime = Field(default_factory=datetime.utcnow)

class BaseLeadDiscoveryAdapter(ABC):
    @abstractmethod
    async def discover_leads(
        self,
        country_code: str,
        niche_slug: str,
        limit: int = 10,
        exclude_domains: Optional[Any] = None
    ) -> List[DiscoveredLeadRaw]:
        """Discovers raw prospect businesses for a target country and niche, skipping excluded domains."""
        pass
