from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class StandardizedProspect(BaseModel):
    """
    Unified cross-country prospect representation.
    Ensures every discovery adapter produces identical structured data.
    """
    business_name: str
    website: str
    domain: str
    country: str
    region: Optional[str] = None
    city: Optional[str] = None
    niche: str = "Local Services"
    public_email: Optional[str] = None
    public_phone: Optional[str] = None
    services: List[str] = Field(default_factory=list)
    business_category: str = "Local Business"
    source_urls: List[str] = Field(default_factory=list)
    discovery_source: str = "real_web"
    verification_status: str = "NEW"
    confidence: float = 0.85
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    contactability: float = 50.0
    audit_status: str = "PENDING"
    raw_signals: Dict[str, Any] = Field(default_factory=dict)

class CountryConfigDTO(BaseModel):
    """Configuration structure for country-aware pipelines."""
    country_code: str
    country_name: str
    enabled: bool = True
    language: str = "en"
    currency: str = "USD"
    timezone: str = "UTC"
    target_cities: List[str] = Field(default_factory=list)
    target_niches: List[str] = Field(default_factory=list)
    discovery_query_templates: List[str] = Field(default_factory=list)
    qualification_rules: Dict[str, Any] = Field(default_factory=dict)
    outreach_rules: Dict[str, Any] = Field(default_factory=dict)
    compliance_settings: Dict[str, Any] = Field(default_factory=dict)
    max_daily_discovery: int = 50
    concurrency_limit: int = 3

class ActiveSlotStatus(BaseModel):
    """Status DTO representing the singular commercial outreach slot."""
    slot_id: int = 1
    is_occupied: bool = False
    business_id: Optional[int] = None
    business_name: Optional[str] = None
    country: Optional[str] = None
    domain: Optional[str] = None
    status: str = "IDLE"
    locked_at: Optional[datetime] = None
    waiting_since: Optional[datetime] = None
    current_stage: Optional[str] = None
    selection_score: Optional[float] = None
    service_fit: Optional[str] = None
    recommended_price_usd: Optional[float] = None
    why_this_prospect: List[str] = Field(default_factory=list)
    next_action: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)

class GlobalQueueItem(BaseModel):
    """Item in the globally ranked prospect opportunity queue."""
    rank: int
    business_id: int
    business_name: str
    domain: str
    country: str
    city: Optional[str] = None
    niche: str
    composite_score: float
    expected_revenue: float
    p_win: float
    lead_quality: float
    contactability: float
    service_fit: float
    top_service: str
    recommended_price_usd: float
    pipeline_stage: str
    why_this_prospect: List[str] = Field(default_factory=list)
    decision_trace: Dict[str, Any] = Field(default_factory=dict)
