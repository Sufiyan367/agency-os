from typing import List, Optional
from pydantic import BaseModel, Field

class LeadQualificationResult(BaseModel):
    lead_score: float = Field(..., ge=0.0, le=100.0, description="Overall commercial opportunity score from 0 to 100")
    qualification: str = Field(..., description="Classification: HOT, WARM, COLD, or INVALID")
    intent_level: str = Field("MEDIUM", description="Inferred buyer intent: HIGH, MEDIUM, LOW")
    pain_points: List[str] = Field(default_factory=list, description="Concrete technical/business pain points discovered")
    recommended_service: str = Field(..., description="Service from business catalog best suited to fix pain points")
    reasoning: str = Field(..., description="Detailed analytical justification grounded in evidence")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Model confidence score")
    needs_human: bool = Field(default=False, description="Whether immediate human intervention is requested or required")
    escalation_reason: Optional[str] = Field(default=None, description="Reason if escalation is triggered")

class OutreachDraftResult(BaseModel):
    subject: str = Field(..., description="Compelling, personalized, spam-free subject line")
    body: str = Field(..., description="Structured, evidence-grounded outreach email with low-friction CTA")
    channel: str = Field(default="EMAIL")
    icebreaker: str = Field(..., description="Specific observation showing real research")
    cta_url: Optional[str] = Field(default=None, description="Booking or diagnostic review URL")

class ReplyClassificationResult(BaseModel):
    classification: str = Field(..., description="INTERESTED, MEETING_REQUEST, QUESTION, NOT_INTERESTED, UNSUBSCRIBE, BOUNCE, UNKNOWN")
    intent_level: str = Field("MEDIUM", description="HIGH, MEDIUM, LOW, NONE")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    summary: str = Field(..., description="Summary of prospect reply")
    suggested_action: str = Field(..., description="BOOK_CALL, SEND_PRICING, ANSWER_QUESTION, STOP_FOLLOWUP, HUMAN_TAKEOVER")
    needs_human: bool = Field(default=False)
