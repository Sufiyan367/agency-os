from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class BusinessSegment(str, Enum):
    MICRO = "micro"            # 1-3 people, solo-operator, single van/chair
    SMALL = "small"            # 4-10 employees, local crew, single location
    SMB = "SMB"                # 11-50 employees, multi-crew, local/regional presence
    MID_MARKET = "mid-market"  # 51-250 employees, multiple locations, departmental
    ENTERPRISE = "enterprise"  # 250+ employees, national/multi-state


class PainCategory(str, Enum):
    LEAD_RESPONSE = "Lead Response"
    LEAD_QUALIFICATION = "Lead Qualification"
    FOLLOW_UP = "Follow-up"
    CUSTOMER_SUPPORT = "Customer Support"
    APPOINTMENT_SCHEDULING = "Appointment Scheduling"
    CRM_DATA_ENTRY = "CRM/Data Entry"
    INVOICE_AP_PROCESSING = "Invoice/AP Processing"
    REPORTING = "Reporting"
    MANUAL_REPETITIVE_OPS = "Manual Repetitive Operations"
    WEBSITE_CONVERSION = "Website Conversion"
    COMMUNICATION_FRAGMENTATION = "Communication Fragmentation"
    DATA_WORKFLOW_INTEGRATION = "Data/Workflow Integration"
    MARKETING_OPS = "Marketing Operations"
    KNOWLEDGE_RETRIEVAL = "Internal Knowledge Retrieval"


class InferredField(BaseModel):
    value: Any
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = "observed_website"
    notes: Optional[str] = None


class BusinessProfile(BaseModel):
    business_name: str
    domain: str
    industry: InferredField
    location: InferredField
    services: InferredField  # List[str]
    website_quality: InferredField  # float 0-100
    contact_channels: InferredField  # List[str]: phone, email, form, chat
    booking_workflow: InferredField  # none, static_form, calendar_widget, email_only
    visible_tooling: InferredField  # List[str] e.g. WordPress, HubSpot, Calendly
    review_signals: InferredField  # count, rating estimate
    operational_maturity: InferredField  # nascent, developing, mature
    raw_signals: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class BusinessSizeEstimate(BaseModel):
    segment: BusinessSegment
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    signals: List[str] = Field(default_factory=list)
    estimated_employee_range: str = "1-10"


class DetectedPainPoint(BaseModel):
    category: PainCategory
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    estimated_frequency: str = "Daily"
    estimated_business_impact: str
    automation_feasible: bool = True


class OperationalWasteEstimate(BaseModel):
    estimated_manual_hours_weekly_low: float = 0.0
    estimated_manual_hours_weekly_high: float = 0.0
    automation_opportunity_score: float = Field(default=50.0, ge=0.0, le=100.0)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    observed_inefficiencies: List[str] = Field(default_factory=list)


class ServiceMatch(BaseModel):
    service_id: str
    service_name: str
    fit_score: float = Field(ge=0.0, le=1.0)
    reasons: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    implementation_complexity: str = "Moderate"
    estimated_effort_days: int = 5


class ROIEstimate(BaseModel):
    status: str = "ESTIMATED"  # "ESTIMATED" or "INSUFFICIENT_DATA"
    monthly_value_low_usd: Optional[float] = None
    monthly_value_expected_usd: Optional[float] = None
    monthly_value_high_usd: Optional[float] = None
    annual_value_expected_usd: Optional[float] = None
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    assumptions: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


class ClientOffer(BaseModel):
    problem_statement: str
    observed_evidence: List[str] = Field(default_factory=list)
    recommended_solution: str
    implementation_scope: List[str] = Field(default_factory=list)
    expected_outcome: str
    investment_usd: float = Field(ge=500.0)
    target_investment_usd: float = Field(default=1000.0, ge=500.0)
    timeline_days: int = 7
    next_step: str = "Schedule a 15-minute diagnostic walkthrough to review workflow scope."


class PricingRecommendation(BaseModel):
    recommended_price_usd: float = Field(ge=500.0)
    target_price_usd: float = Field(default=1000.0, ge=500.0)
    minimum_price_usd: float = Field(default=500.0, ge=500.0)
    pricing_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    value_multiple: float = 1.5
    tier: str = "$1,000–$2,000"
    reasoning: List[str] = Field(default_factory=list)


class DecisionTrace(BaseModel):
    trace_id: str
    business_id: int
    domain: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    input_snapshot: Dict[str, Any] = Field(default_factory=dict)
    feature_snapshot: Dict[str, Any] = Field(default_factory=dict)
    evidence_items: List[str] = Field(default_factory=list)
    inferred_profile: Dict[str, Any] = Field(default_factory=dict)
    pain_points_detected: List[Dict[str, Any]] = Field(default_factory=list)
    service_ranking: List[Dict[str, Any]] = Field(default_factory=list)
    roi_calculation: Dict[str, Any] = Field(default_factory=dict)
    pricing_determination: Dict[str, Any] = Field(default_factory=dict)
    selection_score: float = 0.0
    selection_reasons: List[str] = Field(default_factory=list)
    human_exception_required: bool = False
    exception_reason: Optional[str] = None
