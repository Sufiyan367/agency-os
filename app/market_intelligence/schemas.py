from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class CountryMarketProfileDTO(BaseModel):
    country_code: str
    country_name: str
    region: str
    currency: str
    timezone: str
    primary_languages: List[str]
    secondary_languages: List[str] = []
    population_estimate: Optional[float] = None
    business_density_estimate: Optional[float] = None
    sme_density_estimate: Optional[float] = None
    ai_adoption_signal: Optional[float] = None
    automation_adoption_signal: Optional[float] = None
    digital_maturity_signal: Optional[float] = None
    ability_to_pay_signal: Optional[float] = None
    market_growth_signal: Optional[float] = None
    compliance_risk_signal: str = "UNKNOWN"
    outreach_risk_signal: str = "UNKNOWN"
    research_status: str = "UNKNOWN"
    confidence: float = 0.1
    research_timestamp: Optional[datetime] = None
    next_refresh_at: Optional[datetime] = None


class NicheMarketProfileDTO(BaseModel):
    niche_slug: str
    name: str
    category: str
    typical_lead_value_usd: float
    missed_lead_pain_severity: float
    automation_potential: float
    baseline_ability_to_pay: float
    suitable_services: List[str] = []
    research_status: str = "UNKNOWN"


class MarketEvidenceDTO(BaseModel):
    id: int
    evidence_id: str
    country_code: str
    niche_slug: Optional[str] = None
    service_id: Optional[str] = None
    claim: str
    source_url: str
    source_domain: str
    source_type: str
    source_tier: int
    publisher: str
    publication_date: Optional[datetime] = None
    retrieved_at: datetime
    raw_excerpt: str
    signal_type: str
    source_quality_score: float
    freshness_score: float
    confidence_score: float
    supports_claim: bool


class CountryNicheOpportunityDTO(BaseModel):
    id: int
    country_code: str
    niche_slug: str
    service_id: str
    opportunity_key: str
    market_score: float
    demand_score: float
    ability_to_pay_score: float
    automation_score: float
    expected_deal_value_usd: float
    p_contact: float
    p_fit: float
    p_deal: float
    expected_value_usd: float
    confidence: float
    research_status: str
    evidence_count: int
    freshest_evidence_at: Optional[datetime] = None
    decision_trace: Dict[str, Any] = {}
    updated_at: datetime


class OpportunityFilterParams(BaseModel):
    country_code: Optional[str] = None
    niche_slug: Optional[str] = None
    service_id: Optional[str] = None
    min_score: Optional[float] = None
    min_confidence: Optional[float] = None
    research_status: Optional[str] = None
    limit: int = 50


class ResearchTriggerRequest(BaseModel):
    country_code: Optional[str] = None
    niche_slug: Optional[str] = None
    service_id: Optional[str] = None
    force_refresh: bool = False
