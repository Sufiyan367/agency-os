from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pydantic import BaseModel, Field


# Legacy models for backwards compatibility
class OpportunityEvaluation(BaseModel):
    country_code: str
    country_name: str
    niche_slug: str
    niche_name: str
    total_score: float
    
    need_score: float
    ability_to_pay_score: float
    digital_weakness_score: float
    search_demand_score: float
    business_density_score: float
    service_fit_score: float
    expected_deal_value: float
    competition_score: float
    outreach_difficulty_score: float
    compliance_risk_score: float
    
    reasoning: str
    confidence: float = 0.90
    evidence: Dict[str, Any] = Field(default_factory=dict)
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class MarketComparison(BaseModel):
    winner: OpportunityEvaluation
    runner_up: OpportunityEvaluation
    score_difference: float
    comparative_analysis: str



class EvidenceTier(int, Enum):
    TIER_1_OFFICIAL = 1       # Government, census, national statistics, major institutions (World Bank, OECD)
    TIER_2_RESEARCH = 2       # Established research firms, reputable business press, industry associations
    TIER_3_PUBLIC_WEB = 3     # Public business directories, verified company websites, industry blogs
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


class FreshnessCategory(str, Enum):
    VERY_RECENT = "very_recent"   # < 30 days old
    RECENT = "recent"             # 30-90 days old
    AGING = "aging"               # 90-180 days old
    STALE = "stale"               # > 180 days old (or > 365 days for macro stats)


class SignalDirection(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class SignalType(str, Enum):
    AI_ADOPTION = "AI_ADOPTION"
    AUTOMATION_ADOPTION = "AUTOMATION_ADOPTION"
    DIGITAL_MATURITY = "DIGITAL_MATURITY"
    BUSINESS_DENSITY = "BUSINESS_DENSITY"
    SME_DENSITY = "SME_DENSITY"
    ABILITY_TO_PAY = "ABILITY_TO_PAY"
    LABOR_COST = "LABOR_COST"
    LABOR_SHORTAGE = "LABOR_SHORTAGE"
    MARKET_GROWTH = "MARKET_GROWTH"
    SERVICE_DEMAND = "SERVICE_DEMAND"
    AI_INVESTMENT = "AI_INVESTMENT"
    TECH_INVESTMENT = "TECH_INVESTMENT"
    COMPETITION = "COMPETITION"
    AGENCY_SATURATION = "AGENCY_SATURATION"
    CONTACTABILITY = "CONTACTABILITY"
    DATA_AVAILABILITY = "DATA_AVAILABILITY"
    COMPLIANCE_RISK = "COMPLIANCE_RISK"
    OUTREACH_RISK = "OUTREACH_RISK"
    EVIDENCE_QUALITY = "EVIDENCE_QUALITY"


class ComplianceRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class ResearchStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    CURRENT = "CURRENT"
    AGING = "AGING"
    STALE = "STALE"
    REFRESHING = "REFRESHING"
    FAILED = "FAILED"


@dataclass
class RawEvidenceItem:
    claim: str
    source_url: str
    source_domain: str
    publisher: str
    publication_date: Optional[datetime]
    raw_excerpt: str
    signal_type: str
    country_code: str
    niche_slug: Optional[str] = None
    service_id: Optional[str] = None
    source_type: str = "public_web"
    source_tier: int = 3
    supports_claim: bool = True
    contradicts_claim: bool = False
    confidence: float = 0.8
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedSignal:
    signal_type: str
    value: Optional[float]
    unit: str
    direction: str  # "POSITIVE", "NEGATIVE", "NEUTRAL"
    confidence: float
    evidence_ids: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ScoredOpportunity:
    country_code: str
    niche_slug: str
    service_id: str
    market_score: float
    expected_deal_value_usd: float
    p_contact: float
    p_fit: float
    p_deal: float
    expected_value_usd: float
    confidence: float
    research_status: str
    decision_trace: Dict[str, Any]
    scoring_weights: Dict[str, Any]
    evidence_count: int = 0
    freshest_evidence_at: Optional[datetime] = None
