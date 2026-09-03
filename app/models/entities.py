import enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.connection import Base

# Enums for strict lifecycle tracking
class LeadQualification(str, enum.Enum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"
    INVALID = "INVALID"

class LeadStatus(str, enum.Enum):
    NEW = "NEW"
    QUALIFIED = "QUALIFIED"
    CONTACTABLE = "CONTACTABLE"
    CONTACT_UNAVAILABLE = "CONTACT_UNAVAILABLE"
    OUTREACH_DRAFTED = "OUTREACH_DRAFTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    OUTREACH_PENDING = "OUTREACH_PENDING"
    SENT = "SENT"
    SEND_FAILED = "SEND_FAILED"
    CONTACTED = "CONTACTED"
    REPLIED = "REPLIED"
    REPLY_PENDING_HUMAN_REVIEW = "REPLY_PENDING_HUMAN_REVIEW"
    BOOKED = "BOOKED"
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    OPT_OUT = "OPT_OUT"
    LOST = "LOST"
    DISQUALIFIED = "DISQUALIFIED"
    REJECTED = "REJECTED"

class MessageStatus(str, enum.Enum):
    DRAFTED = "DRAFTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MOCKED_SENT = "MOCKED_SENT"
    SENT = "SENT"
    FAILED = "FAILED"
    SEND_FAILED = "SEND_FAILED"

class FollowupStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    CANCELLED_REPLY = "CANCELLED_REPLY"
    CANCELLED_BOOKING = "CANCELLED_BOOKING"
    CANCELLED_OPT_OUT = "CANCELLED_OPT_OUT"
    CANCELLED_TAKEOVER = "CANCELLED_TAKEOVER"

class EventType(str, enum.Enum):
    LEAD_DISCOVERED = "LEAD_DISCOVERED"
    AUDIT_COMPLETED = "AUDIT_COMPLETED"
    LEAD_QUALIFIED = "LEAD_QUALIFIED"
    CONTACT_VERIFIED = "CONTACT_VERIFIED"
    CONTACT_UNAVAILABLE = "CONTACT_UNAVAILABLE"
    OUTREACH_GENERATED = "OUTREACH_GENERATED"
    OUTREACH_APPROVED = "OUTREACH_APPROVED"
    OUTREACH_SENT = "OUTREACH_SENT"
    OUTREACH_FAILED = "OUTREACH_FAILED"
    FOLLOWUP_SCHEDULED = "FOLLOWUP_SCHEDULED"
    FOLLOWUP_EXECUTED = "FOLLOWUP_EXECUTED"
    FOLLOWUP_CANCELLED = "FOLLOWUP_CANCELLED"
    CUSTOMER_REPLY = "CUSTOMER_REPLY"
    APPOINTMENT_BOOKED = "APPOINTMENT_BOOKED"
    HUMAN_TAKEOVER_ENABLED = "HUMAN_TAKEOVER_ENABLED"
    HUMAN_TAKEOVER_DISABLED = "HUMAN_TAKEOVER_DISABLED"
    OWNER_NOTIFIED = "OWNER_NOTIFIED"
    PROPOSAL_CREATED = "PROPOSAL_CREATED"
    PROPOSAL_APPROVED = "PROPOSAL_APPROVED"
    PAYMENT_REQUESTED = "PAYMENT_REQUESTED"
    PAYMENT_SUCCEEDED = "PAYMENT_SUCCEEDED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    ADVANCE_RECEIVED = "ADVANCE_RECEIVED"
    DEAL_WON = "DEAL_WON"
    DELIVERY_UNLOCKED = "DELIVERY_UNLOCKED"

# 1. Local Businesses
class LocalBusiness(Base):
    __tablename__ = "local_businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    website_url: Mapped[str] = mapped_column(String(500), default="")
    niche: Mapped[str] = mapped_column(String(100), index=True)
    address: Mapped[Optional[str]] = mapped_column(Text, default=None)
    city: Mapped[Optional[str]] = mapped_column(String(100), default=None)
    state: Mapped[Optional[str]] = mapped_column(String(50), default="TX")
    country: Mapped[str] = mapped_column(String(50), default="US")
    email: Mapped[Optional[str]] = mapped_column(String(255), default=None, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), default=None)
    rating: Mapped[Optional[float]] = mapped_column(Float, default=None)
    review_count: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    source: Mapped[str] = mapped_column(String(100), default="discovery_engine")
    source_url: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    leads: Mapped[List["LocalLead"]] = relationship("LocalLead", back_populates="business", cascade="all, delete-orphan")
    audits: Mapped[List["LocalAudit"]] = relationship("LocalAudit", back_populates="business", cascade="all, delete-orphan")

# 2. Local Leads
class LocalLead(Base):
    __tablename__ = "local_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("local_businesses.id"), index=True)
    contact_name: Mapped[str] = mapped_column(String(200), default="Business Owner")
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), default=None)
    contact_email_source: Mapped[Optional[str]] = mapped_column(String(100), default=None)
    contact_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    contact_verification_reason: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    
    status: Mapped[str] = mapped_column(String(50), default=LeadStatus.NEW.value, index=True)
    qualification: Mapped[str] = mapped_column(String(20), default=LeadQualification.WARM.value, index=True)
    lead_score: Mapped[float] = mapped_column(Float, default=0.0)
    intent_level: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    confidence: Mapped[float] = mapped_column(Float, default=0.85)
    
    pain_points: Mapped[List[str]] = mapped_column(JSON, default=list)
    recommended_service: Mapped[str] = mapped_column(String(255), default="")
    reasoning: Mapped[str] = mapped_column(Text, default="")
    
    human_takeover: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    human_takeover_reason: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business: Mapped["LocalBusiness"] = relationship("LocalBusiness", back_populates="leads")
    outreach_messages: Mapped[List["LocalOutreachMessage"]] = relationship("LocalOutreachMessage", back_populates="lead", cascade="all, delete-orphan")
    followups: Mapped[List["LocalFollowup"]] = relationship("LocalFollowup", back_populates="lead", cascade="all, delete-orphan")
    events: Mapped[List["LocalLeadEvent"]] = relationship("LocalLeadEvent", back_populates="lead", cascade="all, delete-orphan")

# 3. Local Audits
class LocalAudit(Base):
    __tablename__ = "local_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("local_businesses.id"), index=True)
    url_audited: Mapped[str] = mapped_column(String(500))
    overall_health_score: Mapped[float] = mapped_column(Float, default=50.0)
    performance_score: Mapped[float] = mapped_column(Float, default=50.0)
    seo_score: Mapped[float] = mapped_column(Float, default=50.0)
    accessibility_score: Mapped[float] = mapped_column(Float, default=50.0)
    security_score: Mapped[float] = mapped_column(Float, default=50.0)
    mobile_responsive: Mapped[bool] = mapped_column(Boolean, default=True)
    
    findings: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    audited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    business: Mapped["LocalBusiness"] = relationship("LocalBusiness", back_populates="audits")

# 4. Local Outreach Messages
class LocalOutreachMessage(Base):
    __tablename__ = "local_outreach_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("local_leads.id"), index=True)
    channel: Mapped[str] = mapped_column(String(50), default="EMAIL")
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default=MessageStatus.PENDING_APPROVAL.value, index=True)
    is_mocked: Mapped[bool] = mapped_column(Boolean, default=True)
    provider: Mapped[Optional[str]] = mapped_column(String(50), default=None)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(100), default=None)
    reply_to: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    evidence_used: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped["LocalLead"] = relationship("LocalLead", back_populates="outreach_messages")

# 5. Local Followup Schedule
class LocalFollowup(Base):
    __tablename__ = "local_followups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("local_leads.id"), index=True)
    step_number: Mapped[int] = mapped_column(Integer, default=1)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(50), default=FollowupStatus.PENDING.value, index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped["LocalLead"] = relationship("LocalLead", back_populates="followups")

# 6. Local Lead Events (Complete Audit Trail)
class LocalLeadEvent(Base):
    __tablename__ = "local_lead_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("local_leads.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped["LocalLead"] = relationship("LocalLead", back_populates="events")

# Aliases
Business = LocalBusiness
Lead = LocalLead
Audit = LocalAudit
OutreachMessage = LocalOutreachMessage
FollowupSchedule = LocalFollowup
LeadEvent = LocalLeadEvent
