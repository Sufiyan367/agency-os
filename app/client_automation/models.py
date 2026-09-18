"""
Agency OS — Client Automation Configuration & Domain Models.

Enforces strict client isolation, typed domain contracts, and deterministic
qualification/booking/FAQ state machines for client-facing automations.
"""

from __future__ import annotations
import enum
from datetime import datetime, time
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class AutomationModule(str, enum.Enum):
    CALL_ANSWERING = "call_answering"
    MISSED_CALL = "missed_call"
    FAQ_KNOWLEDGE = "faq_knowledge"
    APPOINTMENTS = "appointments"
    LEAD_QUALIFICATION = "lead_qualification"
    CRM_FOLLOWUP = "crm_followup"
    ANALYTICS = "analytics"


class LeadStage(str, enum.Enum):
    INQUIRY = "INQUIRY"
    QUALIFIED = "QUALIFIED"
    BOOKING_REQUESTED = "BOOKING_REQUESTED"
    BOOKED = "BOOKED"
    COMPLETED = "COMPLETED"
    FOLLOWUP_DUE = "FOLLOWUP_DUE"
    LOST = "LOST"
    ESCALATED = "ESCALATED"


class CallType(str, enum.Enum):
    INBOUND = "INBOUND"
    MISSED = "MISSED"
    VOICEMAIL = "VOICEMAIL"
    OUTBOUND_TEXTBACK = "OUTBOUND_TEXTBACK"


class EscalationReason(str, enum.Enum):
    UNKNOWN_INTENT = "UNKNOWN_INTENT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    EXPLICIT_HUMAN_REQUEST = "EXPLICIT_HUMAN_REQUEST"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    HIGH_VALUE_OPPORTUNITY = "HIGH_VALUE_OPPORTUNITY"
    COMPLIANCE_RISK = "COMPLIANCE_RISK"
    EMERGENCY = "EMERGENCY"


class AppointmentStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"
    NO_SHOW = "NO_SHOW"


class BusinessHours(BaseModel):
    open_time: str = "09:00"
    close_time: str = "17:00"
    days_of_week: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])  # 0=Monday, 6=Sunday
    timezone: str = "UTC"

    def is_open(self, dt: datetime) -> bool:
        """Determines if the given datetime falls within business hours."""
        if dt.weekday() not in self.days_of_week:
            return False
        current_time_str = dt.strftime("%H:%M")
        return self.open_time <= current_time_str < self.close_time


class ServiceItem(BaseModel):
    service_id: str
    name: str
    description: str = ""
    duration_minutes: int = 30
    price: float = 0.0
    currency: str = "USD"
    requires_deposit: bool = False
    deposit_amount: float = 0.0


class FAQItem(BaseModel):
    faq_id: str
    question: str
    answer: str
    keywords: List[str] = Field(default_factory=list)
    category: str = "general"


class BookingRules(BaseModel):
    slot_duration_minutes: int = 30
    buffer_minutes: int = 15
    min_notice_hours: int = 2
    max_advance_days: int = 30
    allow_same_day: bool = True


class CancellationPolicy(BaseModel):
    notice_hours_required: int = 24
    fee_amount: float = 0.0
    terms: str = "Cancellations require at least 24 hours notice."


class EscalationRules(BaseModel):
    notify_on_escalation: bool = True
    human_phone: Optional[str] = None
    human_email: Optional[str] = None
    max_unanswered_questions: int = 2
    escalation_keywords: List[str] = Field(
        default_factory=lambda: ["speak to human", "manager", "operator", "agent", "emergency", "lawsuit", "refund"]
    )


class QualificationRule(BaseModel):
    rule_id: str
    question: str
    key: str
    required: bool = True
    expected_type: str = "string"  # string, number, boolean, choice
    min_value: Optional[float] = None
    allowed_values: Optional[List[str]] = None
    weight: float = 1.0


class ClientAutomationConfig(BaseModel):
    """
    Client-isolated configuration profile defining business rules, hours,
    services, booking parameters, brand voice, and enabled automation modules.
    """
    client_id: str = Field(..., description="Unique client/tenant identifier")
    business_name: str
    contact_email: str
    contact_phone: Optional[str] = None
    timezone: str = "UTC"
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    location: str = "Virtual / Remote"
    services: List[ServiceItem] = Field(default_factory=list)
    faqs: List[FAQItem] = Field(default_factory=list)
    booking_rules: BookingRules = Field(default_factory=BookingRules)
    cancellation_policy: CancellationPolicy = Field(default_factory=CancellationPolicy)
    escalation_rules: EscalationRules = Field(default_factory=EscalationRules)
    brand_voice: str = "Warm, professional, concise, and helpful."
    qualification_rules: List[QualificationRule] = Field(default_factory=list)
    notification_channels: List[str] = Field(default_factory=lambda: ["email", "dashboard"])
    enabled_modules: List[AutomationModule] = Field(
        default_factory=lambda: [
            AutomationModule.CALL_ANSWERING,
            AutomationModule.MISSED_CALL,
            AutomationModule.FAQ_KNOWLEDGE,
            AutomationModule.APPOINTMENTS,
            AutomationModule.LEAD_QUALIFICATION,
            AutomationModule.CRM_FOLLOWUP,
            AutomationModule.ANALYTICS,
        ]
    )
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def has_module(self, module: AutomationModule) -> bool:
        return module in self.enabled_modules


class LeadRecord(BaseModel):
    """Client-isolated lead state within the automation lifecycle."""
    lead_id: str
    client_id: str
    contact_name: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    stage: LeadStage = LeadStage.INQUIRY
    source: str = "INBOUND"
    score: float = 0.0
    qualification_answers: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AppointmentRecord(BaseModel):
    """Client-isolated scheduled appointment."""
    appointment_id: str
    client_id: str
    lead_id: str
    service_id: str
    service_name: str
    start_time: datetime
    end_time: datetime
    status: AppointmentStatus = AppointmentStatus.SCHEDULED
    confirmation_code: str
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CallRecord(BaseModel):
    """Client-isolated call log."""
    call_id: str
    client_id: str
    caller_phone: str
    call_type: CallType
    duration_seconds: int = 0
    is_after_hours: bool = False
    textback_sent: bool = False
    textback_message: Optional[str] = None
    disposition: str = "PROCESSED"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EscalationEvent(BaseModel):
    """Record of an automation escalation to human operator."""
    escalation_id: str
    client_id: str
    lead_id: Optional[str] = None
    reason: EscalationReason
    message: str
    context: Dict[str, Any] = Field(default_factory=dict)
    resolved: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)
