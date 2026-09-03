from typing import Optional, List
from pydantic import BaseModel, Field

class NormalizedBusinessRecord(BaseModel):
    business_name: str = Field(..., description="Cleaned, normalized legal/trade name of the business")
    category: str = Field(..., description="Business category or trade (e.g. HVAC Contractor)")
    address: Optional[str] = Field(default=None, description="Physical street address if available")
    city: str = Field(..., description="City location")
    region: str = Field(..., description="State or province (e.g. Texas, TX)")
    country: str = Field(default="US", description="Country name or ISO code")
    website: Optional[str] = Field(default=None, description="Official company website URL")
    phone: Optional[str] = Field(default=None, description="E.164 or normalized standard phone number")
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0, description="Average review rating")
    review_count: Optional[int] = Field(default=None, ge=0, description="Total verified review count")
    source: str = Field(default="mock_discovery", description="Origin provider or directory source")
    source_url: Optional[str] = Field(default=None, description="Direct URL of the listing or directory page")

class DiscoveryStats(BaseModel):
    businesses_discovered: int = Field(default=0)
    valid_businesses: int = Field(default=0)
    duplicates_removed: int = Field(default=0)
    with_websites: int = Field(default=0)
    with_phone_numbers: int = Field(default=0)
    cities_covered: List[str] = Field(default_factory=list)
