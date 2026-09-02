from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime

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
