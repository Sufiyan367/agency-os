"""
Canonical Intelligence Models & Schemas — Mega Prompt 8.
Enforces strict segregation between OBSERVED FACT, INFERENCE, PREDICTION, and HYPOTHESIS.
"""
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class EpistemicStatus(str, Enum):
    """
    Mandatory epistemic status of all intelligence signals.
    Prevents predictions or hypotheses from being represented as observed facts.
    """
    OBSERVED_FACT = "OBSERVED_FACT"  # Verified measurement, explicit user response, verified payment, HTTP 200
    INFERENCE = "INFERENCE"          # Rule-based deduction from observed facts
    PREDICTION = "PREDICTION"        # Probabilistic future estimation (P(Win), Churn Risk, etc.)
    HYPOTHESIS = "HYPOTHESIS"        # Unverified optimization premise or A/B experiment variant


class ConfidenceBand(str, Enum):
    HIGH = "HIGH"        # Supported by direct multi-source telemetry & sufficient sample
    MEDIUM = "MEDIUM"    # Deterministic heuristic or moderate sample
    LOW = "LOW"          # Cold-start, sparse data, or maximum entropy estimation


class SignalCategory(str, Enum):
    LEAD = "LEAD"
    CONVERSATION = "CONVERSATION"
    SALES = "SALES"
    CUSTOMER = "CUSTOMER"
    MAINTENANCE = "MAINTENANCE"
    CODE = "CODE"
    FINANCIAL = "FINANCIAL"
    SYSTEM = "SYSTEM"


class SignalType(str, Enum):
    # Lead Signals
    LEAD_FIT = "LEAD_FIT"
    BUYING_INTENT = "BUYING_INTENT"
    WEBSITE_OPPORTUNITY = "WEBSITE_OPPORTUNITY"
    SERVICE_FIT = "SERVICE_FIT"
    CONTACTABILITY = "CONTACTABILITY"
    GEOGRAPHIC_PRIORITY = "GEOGRAPHIC_PRIORITY"
    INDUSTRY_PRIORITY = "INDUSTRY_PRIORITY"
    COMPETITIVE_SIGNAL = "COMPETITIVE_SIGNAL"
    RECENCY = "RECENCY"
    EVIDENCE_QUALITY = "EVIDENCE_QUALITY"

    # Conversation & Objection Signals
    RESPONSE_INTENT = "RESPONSE_INTENT"
    PRICE_OBJECTION = "PRICE_OBJECTION"
    TRUST_OBJECTION = "TRUST_OBJECTION"
    TIMING_OBJECTION = "TIMING_OBJECTION"
    FEATURE_REQUEST = "FEATURE_REQUEST"
    COMPETITOR_REFERENCE = "COMPETITOR_REFERENCE"
    AUTHORITY_SIGNAL = "AUTHORITY_SIGNAL"
    URGENCY = "URGENCY"
    BUDGET_SIGNAL = "BUDGET_SIGNAL"
    PROCUREMENT_SIGNAL = "PROCUREMENT_SIGNAL"
    READY_TO_BUY = "READY_TO_BUY"

    # Sales & Revenue Signals
    DEAL_PROBABILITY = "DEAL_PROBABILITY"
    PRICE_SENSITIVITY = "PRICE_SENSITIVITY"
    FOLLOWUP_TIMING = "FOLLOWUP_TIMING"
    EXPECTED_VALUE = "EXPECTED_VALUE"
    STAGE_VELOCITY = "STAGE_VELOCITY"

    # Customer & Support Signals
    CUSTOMER_HEALTH = "CUSTOMER_HEALTH"
    CHURN_RISK = "CHURN_RISK"
    SUPPORT_BURDEN = "SUPPORT_BURDEN"

    # Maintenance & DevOps Signals
    INCIDENT_RISK = "INCIDENT_RISK"
    MAINTENANCE_RISK = "MAINTENANCE_RISK"
    CODE_RISK = "CODE_RISK"
    COST_ANOMALY = "COST_ANOMALY"


class ActionType(str, Enum):
    WAIT = "WAIT"
    RESEARCH = "RESEARCH"
    AUDIT = "AUDIT"
    OPPORTUNITY_ANALYSIS = "OPPORTUNITY_ANALYSIS"
    PERSONALIZE = "PERSONALIZE"
    CEO_REVIEW = "CEO_REVIEW"
    OUTREACH = "OUTREACH"
    WAIT_FOR_REPLY = "WAIT_FOR_REPLY"
    CEO_NOTIFICATION = "CEO_NOTIFICATION"
    PREPARE_RESPONSE = "PREPARE_RESPONSE"
    FOLLOW_UP = "FOLLOW_UP"
    ANSWER_QUESTION = "ANSWER_QUESTION"
    DEMO_FACTORY = "DEMO_FACTORY"
    DEMO = "DEMO"
    PROPOSAL = "PROPOSAL"
    SEND_PROPOSAL = "SEND_PROPOSAL"
    PAYMENT = "PAYMENT"
    PAYMENT_FOLLOWUP = "PAYMENT_FOLLOWUP"
    PRODUCTION = "PRODUCTION"
    ONBOARD = "ONBOARD"
    SUPPORT = "SUPPORT"
    ESCALATE = "ESCALATE"
    EXPANSION_ANALYSIS = "EXPANSION_ANALYSIS"
    REQUEST_REQUIREMENTS = "REQUEST_REQUIREMENTS"
    SCHEDULE_CALL = "SCHEDULE_CALL"
    NO_ACTION = "NO_ACTION"


class RecommendationStatus(str, Enum):
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    OUTCOME_PENDING = "OUTCOME_PENDING"
    EVALUATED = "EVALUATED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


# ==============================================================================
# CANONICAL INTELLIGENCE SIGNAL
# ==============================================================================

class IntelligenceSignal(BaseModel):
    """
    Canonical, immutable intelligence signal format for Agency OS.
    Grounds all deductions with explicit evidence and epistemic provenance.
    """
    id: str = Field(..., description="Unique deterministic or UUID signal identifier")
    entity_type: str = Field(..., description="Target entity type: business, customer, ticket, outreach, market")
    entity_id: int = Field(..., description="Target entity identifier")
    category: SignalCategory = Field(default=SignalCategory.LEAD)
    signal_type: SignalType = Field(..., description="Canonical signal type enum")
    epistemic_status: EpistemicStatus = Field(..., description="FACT, INFERENCE, PREDICTION, or HYPOTHESIS")
    signal_value: float = Field(..., description="Normalized quantitative signal magnitude [0.0 - 100.0 or ratio]")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Mathematical confidence score [0.0 - 1.0]")
    confidence_band: ConfidenceBand = Field(default=ConfidenceBand.MEDIUM)
    source: str = Field(default="deterministic_engine", description="Originating provider, model, or telemetry system")
    evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Grounding evidence facts or quotes")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(default=None, description="TTL timestamp when signal goes stale")
    model_provider: str = Field(default="local")
    version: str = Field(default="v1.0.0")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# RECOMMENDATION & ACTION SCHEMAS
# ==============================================================================

class NextBestActionDecision(BaseModel):
    """Structured, explainable Next Best Action recommendation."""
    entity_type: str
    entity_id: int
    action: ActionType
    confidence: float
    confidence_band: ConfidenceBand
    priority_score: float
    reasoning: str
    evidence: List[str]
    policy_passed: bool
    policy_notes: str
    commercial_value_usd: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OptimizationRecommendation(BaseModel):
    """Actionable recommendation synthesized by the Optimization Engine."""
    id: str
    category: str  # PIPELINE, PRICING, OUTREACH, SUPPORT, SYSTEM
    recommendation: str
    why: str
    evidence: List[Dict[str, Any]]
    expected_impact: str
    confidence: float
    confidence_band: ConfidenceBand
    risk_level: RiskLevel
    next_action: str
    status: RecommendationStatus = RecommendationStatus.GENERATED
    entity_type: str = "system"
    entity_id: Optional[int] = None
    decision_trace: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# SPECIALIZED REPORT SCHEMAS
# ==============================================================================

class BlastRadiusReport(BaseModel):
    report_id: str
    repair_ticket_id: Optional[int] = None
    modified_files: List[str]
    affected_routes: List[str]
    affected_services: List[str]
    affected_models: List[str]
    affected_customers_count: int = 0
    regression_risk: RiskLevel
    regression_score: float
    rollback_reference: Optional[str] = None
    reasoning: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DataQualityReport(BaseModel):
    report_id: str
    entity_type: str
    overall_score: float
    duplicate_count: int = 0
    stale_count: int = 0
    missing_fields_count: int = 0
    invalid_domains_count: int = 0
    anomalies: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AIUsageTelemetry(BaseModel):
    correlation_id: str
    operation: str
    provider: str
    model_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
