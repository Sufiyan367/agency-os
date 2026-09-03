import enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class BuyerTier(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"

class ProspectClassification(str, enum.Enum):
    DISCARD = "DISCARD"
    LOW_VALUE = "LOW_VALUE"
    NURTURE = "NURTURE"
    PRIORITY_PROSPECT = "PRIORITY_PROSPECT"

class HighValueBuyerScore(BaseModel):
    score: float = Field(..., ge=0.0, le=100.0, description="Overall purchasing capacity score (0-100)")
    tier: BuyerTier = Field(..., description="Commercial buyer tier")
    estimated_service_budget: str = Field(
        ...,
        description="Estimated service budget range based on capacity proxies (NOT confirmed revenue or guaranteed budget)"
    )
    buying_capacity_signals: List[str] = Field(default_factory=list, description="Observed proxies of scale, team size, multi-location, premium positioning")
    opportunity_signals: List[str] = Field(default_factory=list, description="Observed digital gaps, slow mobile UX, conversion bottlenecks, missing SEO")
    negative_signals: List[str] = Field(default_factory=list, description="Signals indicating small solo operation, low review volume, or budget constraint")
    reasoning: str = Field(..., description="Transparent factual breakdown distinguishing observed data from inferences")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0, description="Confidence in the observable signals")

class NormalizedBusinessRecord(BaseModel):
    business_name: str = Field(..., description="Cleaned, normalized legal/trade name of the business")
    category: str = Field(..., description="Business category or trade (e.g. HVAC Contractor)")
    address: Optional[str] = Field(default=None, description="Physical street address if available")
    city: str = Field(..., description="City location")
    region: str = Field(..., description="State or province (e.g. Texas, TX)")
    country: str = Field(default="US", description="Country name or ISO code")
    website: Optional[str] = Field(default=None, description="Official company website URL")
    phone: Optional[str] = Field(default=None, description="E.164 or normalized standard phone number")
    email: Optional[str] = Field(default=None, description="Direct email if observed")
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0, description="Average review rating")
    review_count: Optional[int] = Field(default=None, ge=0, description="Total verified review count")
    source: str = Field(default="mock_discovery", description="Origin provider or directory source")
    source_url: Optional[str] = Field(default=None, description="Direct URL of the listing or directory page")

    # Observable Operational & Market Signals
    num_locations: int = Field(default=1, ge=1, description="Number of active physical locations")
    years_in_business: Optional[int] = Field(default=None, description="Years in operation if observable")
    is_commercial_and_residential: bool = Field(default=False, description="Operates commercial contracts in addition to residential")
    has_fleet_or_technicians: bool = Field(default=False, description="Observable indicators of field technicians, dispatcher, or fleet vehicles")
    offers_emergency_service: bool = Field(default=False, description="Offers 24/7 or emergency dispatch")
    authorized_dealer_or_financing: bool = Field(default=False, description="Authorized Trane/Carrier dealer or offers customer financing")
    hiring_active: bool = Field(default=False, description="Public job postings for technicians/installers")
    affluent_service_area: bool = Field(default=False, description="Servicing high-income zip codes")

    # Observable Digital / Diagnostic Signals
    page_speed_issue: bool = Field(default=False, description="Observed slow page load (>4s LCP)")
    seo_issue: bool = Field(default=False, description="Observed missing schema or title tags")
    mobile_ux_issue: bool = Field(default=False, description="Observed mobile viewport or tap target issues")
    lacks_lead_capture: bool = Field(default=False, description="No click-to-call or direct online booking on mobile")

class ScoredProspect(BaseModel):
    business: NormalizedBusinessRecord
    buyer_score: HighValueBuyerScore
    opportunity_score: float = Field(..., ge=0.0, le=100.0)
    classification: ProspectClassification
    has_contact_path: bool = Field(default=True)
    classification_rationale: str = Field(...)

class DiscoveryStats(BaseModel):
    businesses_discovered: int = Field(default=0)
    valid_businesses: int = Field(default=0)
    duplicates_removed: int = Field(default=0)
    with_websites: int = Field(default=0)
    with_phone_numbers: int = Field(default=0)
    cities_covered: List[str] = Field(default_factory=list)

    # Commercial High-Value Analytics
    high_value_buyer_candidates: int = Field(default=0)
    high_opportunity_candidates: int = Field(default=0)
    priority_prospects: int = Field(default=0)
    discarded_prospects: int = Field(default=0)
    average_buyer_score: float = Field(default=0.0)
    average_opportunity_score: float = Field(default=0.0)
