"""
Client-Safe Demo Models — Phase 19 / Demo Factory Architecture.
Defines data structures strictly decoupled from internal operational metrics,
safe for public prospect-facing interactive landing pages and demos.
"""
from enum import Enum
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class InteractiveScenarioType(str, Enum):
    CALL_SIMULATOR = "CALL_SIMULATOR"
    CHAT_SIMULATOR = "CHAT_SIMULATOR"
    SPEED_COMPARATOR = "SPEED_COMPARATOR"
    WORKFLOW_STEPPER = "WORKFLOW_STEPPER"
    ROI_CALCULATOR = "ROI_CALCULATOR"


class BusinessIdentity(BaseModel):
    business_name: str
    domain: str
    slug: str
    niche: str
    city: Optional[str] = None
    country: str = "US"
    brand_color: Optional[str] = "#0284c7"
    phone: Optional[str] = None
    verified_facts: List[str] = Field(default_factory=list)


class OpportunitySummary(BaseModel):
    headline: str
    subheadline: str
    diplomatic_observations: List[str] = Field(default_factory=list)
    projected_impact: str


class SolutionSpecification(BaseModel):
    service_id: Optional[str] = None
    service_title: str
    service_category: str
    scope_deliverables: List[str] = Field(default_factory=list)
    specifications: List[Dict[str, Any]] = Field(default_factory=list)
    turnaround_days: int = 5
    total_price_usd: float = 1000.0
    advance_amount_usd: float = 400.0


class InteractiveScenario(BaseModel):
    scenario_type: InteractiveScenarioType
    title: str
    description: str
    scenario_badge: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ClientSafeDemoConfig(BaseModel):
    demo_id: str
    identity: BusinessIdentity
    opportunity: OpportunitySummary
    solution: SolutionSpecification
    scenario: InteractiveScenario
    benefits: List[str] = Field(default_factory=list)
    cta_text: str = "Authorize Implementation"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    checksum: str = ""
