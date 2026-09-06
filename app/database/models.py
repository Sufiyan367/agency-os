import enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON, Numeric, Index, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.connection import Base

# Enums
class PipelineStage(str, enum.Enum):
    DISCOVERED = "DISCOVERED"
    VERIFIED = "VERIFIED"
    AUDITED = "AUDITED"
    QUALIFIED = "QUALIFIED"
    OUTREACH_READY = "OUTREACH_READY"
    APPROVAL = "APPROVAL"
    CONTACTED = "CONTACTED"
    REPLIED = "REPLIED"
    QUALIFIED_REPLY = "QUALIFIED_REPLY"
    CALL = "CALL"
    MEETING = "MEETING"
    PROPOSAL = "PROPOSAL"
    PAYMENT_REQUESTED = "PAYMENT_REQUESTED"
    ADVANCE_PAID = "ADVANCE_PAID"
    IN_DELIVERY = "IN_DELIVERY"
    COMPLETED = "COMPLETED"
    BALANCE_PAID = "BALANCE_PAID"
    WON = "WON"
    LOST = "LOST"
    REJECTED = "REJECTED"

class LeadPriority(str, enum.Enum):
    A = "A"        # 90-100
    B = "B"        # 75-89
    C = "C"        # 60-74
    LOW = "LOW"    # <60

class VerificationStatus(str, enum.Enum):
    NEW = "NEW"
    RESEARCHING = "RESEARCHING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

class AuditSeverity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

class OutreachStatus(str, enum.Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    HELD = "HELD"
    SENT = "SENT"
    FAILED = "FAILED"

class ReplyClassification(str, enum.Enum):
    INTERESTED = "INTERESTED"
    QUESTION = "QUESTION"
    NOT_INTERESTED = "NOT_INTERESTED"
    LATER = "LATER"
    PRICE_REQUEST = "PRICE_REQUEST"
    MEETING_REQUEST = "MEETING_REQUEST"
    REFERRAL = "REFERRAL"
    OUT_OF_OFFICE = "OUT_OF_OFFICE"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    BOUNCE = "BOUNCE"
    OBJECTION = "OBJECTION"
    UNKNOWN = "UNKNOWN"

class FollowupStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    CANCELLED_REPLY = "CANCELLED_REPLY"
    CANCELLED_UNSUB = "CANCELLED_UNSUB"
    CANCELLED_MANUAL = "CANCELLED_MANUAL"

# 1. Countries
class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    gdp_per_capita: Mapped[float] = mapped_column(Float, default=0.0)
    business_density_score: Mapped[float] = mapped_column(Float, default=50.0)
    digital_maturity_score: Mapped[float] = mapped_column(Float, default=50.0)
    english_accessibility: Mapped[float] = mapped_column(Float, default=100.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    regulatory_risk_score: Mapped[float] = mapped_column(Float, default=20.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    opportunities: Mapped[List["MarketOpportunity"]] = relationship("MarketOpportunity", back_populates="country", lazy="selectin")

# 2. Niches
class Niche(Base):
    __tablename__ = "niches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100), default="Local Services")
    avg_deal_size: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=750.0)
    digital_weakness_factor: Mapped[float] = mapped_column(Float, default=60.0)
    service_fit_score: Mapped[float] = mapped_column(Float, default=70.0)
    commercial_intent_score: Mapped[float] = mapped_column(Float, default=75.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    opportunities: Mapped[List["MarketOpportunity"]] = relationship("MarketOpportunity", back_populates="niche", lazy="selectin")

# 3. Market Opportunities
class MarketOpportunity(Base):
    __tablename__ = "market_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_id: Mapped[int] = mapped_column(Integer, ForeignKey("countries.id"), index=True)
    niche_id: Mapped[int] = mapped_column(Integer, ForeignKey("niches.id"), index=True)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    need_score: Mapped[float] = mapped_column(Float, default=50.0)
    ability_to_pay_score: Mapped[float] = mapped_column(Float, default=50.0)
    digital_weakness_score: Mapped[float] = mapped_column(Float, default=50.0)
    search_demand_score: Mapped[float] = mapped_column(Float, default=50.0)
    business_density_score: Mapped[float] = mapped_column(Float, default=50.0)
    service_fit_score: Mapped[float] = mapped_column(Float, default=50.0)
    expected_deal_value: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=750.0)
    competition_score: Mapped[float] = mapped_column(Float, default=50.0)
    outreach_difficulty_score: Mapped[float] = mapped_column(Float, default=50.0)
    compliance_risk_score: Mapped[float] = mapped_column(Float, default=20.0)
    
    reasoning: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.85)
    evidence: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    country: Mapped["Country"] = relationship("Country", back_populates="opportunities", lazy="selectin")
    niche: Mapped["Niche"] = relationship("Niche", back_populates="opportunities", lazy="selectin")

# 4. Businesses (Prospects)
class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    website_url: Mapped[str] = mapped_column(String(500), default="")
    country: Mapped[str] = mapped_column(String(50), index=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), default=None)
    niche: Mapped[str] = mapped_column(String(100), index=True)
    
    public_email: Mapped[Optional[str]] = mapped_column(String(255), default=None, index=True)
    email_status: Mapped[str] = mapped_column(String(50), default="unknown")
    phone: Mapped[Optional[str]] = mapped_column(String(50), default=None)
    contact_page_url: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    address: Mapped[Optional[str]] = mapped_column(Text, default=None)
    social_profiles: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    source: Mapped[str] = mapped_column(String(100), default="web_discovery")
    verification_status: Mapped[str] = mapped_column(String(50), default=VerificationStatus.NEW.value)
    pipeline_stage: Mapped[str] = mapped_column(String(50), default=PipelineStage.DISCOVERED.value, index=True)
    
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    effective_evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    research_status: Mapped[str] = mapped_column(String(50), default="RESEARCH_REQUIRED", index=True)
    prospect_score: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_businesses_stage_verif", "pipeline_stage", "verification_status"),
        Index("ix_businesses_country_niche", "country", "niche"),
        Index("ix_businesses_created_at", "created_at"),
    )

    contacts: Mapped[List["Contact"]] = relationship("Contact", back_populates="business", cascade="all, delete-orphan", lazy="selectin")
    audits: Mapped[List["AuditRun"]] = relationship("AuditRun", back_populates="business", cascade="all, delete-orphan", lazy="selectin")
    lead_score: Mapped[Optional["LeadScore"]] = relationship("LeadScore", back_populates="business", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    offers: Mapped[List["Offer"]] = relationship("Offer", back_populates="business", cascade="all, delete-orphan", lazy="selectin")
    outreach_messages: Mapped[List["OutreachMessage"]] = relationship("OutreachMessage", back_populates="business", cascade="all, delete-orphan", lazy="selectin")
    pipeline_events: Mapped[List["PipelineEvent"]] = relationship("PipelineEvent", back_populates="business", cascade="all, delete-orphan", lazy="selectin")
    customer: Mapped[Optional["Customer"]] = relationship("Customer", back_populates="business", uselist=False, lazy="selectin")
    memory: Mapped[Optional["ProspectMemory"]] = relationship("ProspectMemory", back_populates="business", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    client_intelligence: Mapped[Optional["ClientIntelligenceRecord"]] = relationship("ClientIntelligenceRecord", back_populates="business", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    artifacts: Mapped[List["Artifact"]] = relationship("Artifact", back_populates="business", cascade="all, delete-orphan", lazy="selectin")
    activity_events: Mapped[List["AgentActivityEvent"]] = relationship("AgentActivityEvent", back_populates="business", cascade="all, delete-orphan", lazy="selectin")
    evidence_items: Mapped[List["ProspectEvidence"]] = relationship("ProspectEvidence", back_populates="business", cascade="all, delete-orphan", lazy="selectin")


# 5. Contacts
class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="Business Owner / Marketing Lead")
    title: Mapped[str] = mapped_column(String(100), default="Owner")
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), default=None)
    linkedin: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    email_status: Mapped[str] = mapped_column(String(50), default="unknown")
    source: Mapped[str] = mapped_column(String(100), default="website_scrape")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    business: Mapped["Business"] = relationship("Business", back_populates="contacts", lazy="selectin")

# 6. Audit Runs
class AuditRun(Base):
    __tablename__ = "audit_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), index=True)
    url_audited: Mapped[str] = mapped_column(String(500))
    audited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    performance_score: Mapped[float] = mapped_column(Float, default=50.0)
    seo_score: Mapped[float] = mapped_column(Float, default=50.0)
    a11y_score: Mapped[float] = mapped_column(Float, default=50.0)
    ux_conversion_score: Mapped[float] = mapped_column(Float, default=50.0)
    security_score: Mapped[float] = mapped_column(Float, default=50.0)
    content_score: Mapped[float] = mapped_column(Float, default=50.0)
    overall_health_score: Mapped[float] = mapped_column(Float, default=50.0)
    
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    tech_stack: Mapped[List[str]] = mapped_column(JSON, default=list)

    business: Mapped["Business"] = relationship("Business", back_populates="audits", lazy="selectin")
    findings: Mapped[List["AuditFinding"]] = relationship("AuditFinding", back_populates="audit", cascade="all, delete-orphan", lazy="selectin")

# 7. Audit Findings
class AuditFinding(Base):
    __tablename__ = "audit_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[int] = mapped_column(Integer, ForeignKey("audit_runs.id"), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    finding: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(20), default=AuditSeverity.MEDIUM.value)
    evidence: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(500))
    recommended_fix: Mapped[str] = mapped_column(Text)
    estimated_business_impact: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    audit: Mapped["AuditRun"] = relationship("AuditRun", back_populates="findings", lazy="selectin")

# 8. Lead Scores
class LeadScore(Base):
    __tablename__ = "lead_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), unique=True, index=True)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[str] = mapped_column(String(10), default=LeadPriority.LOW.value)
    
    website_weakness_subscore: Mapped[float] = mapped_column(Float, default=0.0)
    seo_opportunity_subscore: Mapped[float] = mapped_column(Float, default=0.0)
    a11y_opportunity_subscore: Mapped[float] = mapped_column(Float, default=0.0)
    performance_opportunity_subscore: Mapped[float] = mapped_column(Float, default=0.0)
    conversion_opportunity_subscore: Mapped[float] = mapped_column(Float, default=0.0)
    ability_to_pay_subscore: Mapped[float] = mapped_column(Float, default=0.0)
    contactability_subscore: Mapped[float] = mapped_column(Float, default=0.0)
    
    scoring_breakdown: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    business: Mapped["Business"] = relationship("Business", back_populates="lead_score", lazy="selectin")

# 9. Offers
class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), index=True)
    service_type: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(255))
    scope_description: Mapped[str] = mapped_column(Text, default="")
    deliverables: Mapped[List[str]] = mapped_column(JSON, default=list)
    suggested_price_min: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=500.0)
    suggested_price_max: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=950.0)
    recommended_price: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=650.0)
    estimated_delivery_days: Mapped[int] = mapped_column(Integer, default=7)
    value_proposition: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    business: Mapped["Business"] = relationship("Business", back_populates="offers", lazy="selectin")
    outreach_messages: Mapped[List["OutreachMessage"]] = relationship("OutreachMessage", back_populates="offer", lazy="selectin")

# 10. Outreach Messages
class OutreachMessage(Base):
    __tablename__ = "outreach_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), index=True)
    offer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("offers.id"), nullable=True)
    recipient_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    variant_name: Mapped[str] = mapped_column(String(50), default="Value-First")
    status: Mapped[str] = mapped_column(String(50), default=OutreachStatus.PENDING_APPROVAL.value, index=True)
    sequence_step: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    compliance_notes: Mapped[str] = mapped_column(Text, default="Complies with CAN-SPAM / GDPR B2B public legitimate interest")
    
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_outreach_messages_status_created", "status", "created_at"),
    )

    business: Mapped["Business"] = relationship("Business", back_populates="outreach_messages", lazy="selectin")
    offer: Mapped[Optional["Offer"]] = relationship("Offer", back_populates="outreach_messages", lazy="selectin")
    events: Mapped[List["OutreachEvent"]] = relationship("OutreachEvent", back_populates="outreach_message", cascade="all, delete-orphan", lazy="selectin")
    followups: Mapped[List["FollowupSequence"]] = relationship("FollowupSequence", back_populates="initial_message", cascade="all, delete-orphan", lazy="selectin")

# 11. Outreach Events
class OutreachEvent(Base):
    __tablename__ = "outreach_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outreach_message_id: Mapped[int] = mapped_column(Integer, ForeignKey("outreach_messages.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    outreach_message: Mapped["OutreachMessage"] = relationship("OutreachMessage", back_populates="events", lazy="selectin")

# 12. Follow-up Sequences
class FollowupSequence(Base):
    __tablename__ = "followup_sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    initial_message_id: Mapped[int] = mapped_column(Integer, ForeignKey("outreach_messages.id"), index=True)
    step_number: Mapped[int] = mapped_column(Integer, default=2)
    delay_days: Mapped[int] = mapped_column(Integer, default=3)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default=FollowupStatus.SCHEDULED.value)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_followup_status_scheduled", "status", "scheduled_for"),
    )

    initial_message: Mapped["OutreachMessage"] = relationship("OutreachMessage", back_populates="followups", lazy="selectin")

# 13. Replies
class Reply(Base):
    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), index=True)
    outreach_message_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("outreach_messages.id"), nullable=True)
    sender_email: Mapped[str] = mapped_column(String(255))
    raw_body: Mapped[str] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(50), default=ReplyClassification.UNKNOWN.value, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.85)
    suggested_response: Mapped[str] = mapped_column(Text, default="")
    is_handled: Mapped[bool] = mapped_column(Boolean, default=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# 14. Pipeline Events
class PipelineEvent(Base):
    __tablename__ = "pipeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), index=True)
    from_stage: Mapped[str] = mapped_column(String(50))
    to_stage: Mapped[str] = mapped_column(String(50))
    deal_value: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=0.0)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    business: Mapped["Business"] = relationship("Business", back_populates="pipeline_events", lazy="selectin")

# 15. Customers
class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(255))
    contact_email: Mapped[str] = mapped_column(String(255))
    contract_amount: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=0.0)
    onboarding_status: Mapped[str] = mapped_column(String(50), default="PENDING_ONBOARDING")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    business: Mapped["Business"] = relationship("Business", back_populates="customer", lazy="selectin")
    projects: Mapped[List["Project"]] = relationship("Project", back_populates="customer", lazy="selectin")

# 16. Projects
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    service_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="IN_PROGRESS")
    tasks: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    audit_report_path: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    qa_checklist: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="projects", lazy="selectin")

# 17. Payments
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    business_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=True, index=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    deal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    proposal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    
    amount: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    payment_type: Mapped[str] = mapped_column(String(50), default="FULL_PAYMENT")  # ADVANCE, FULL_PAYMENT, FINAL_BALANCE
    status: Mapped[str] = mapped_column(String(50), default="COMPLETED")  # DRAFT, PAYMENT_PENDING, PAID, FAILED, REFUNDED, CANCELLED
    reference_id: Mapped[str] = mapped_column(String(100), default="", index=True)
    provider: Mapped[str] = mapped_column(String(50), default="razorpay")
    
    razorpay_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    razorpay_payment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    razorpay_signature: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    extra_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

# 17b. Commercial Proposals
class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), index=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    
    title: Mapped[str] = mapped_column(String(255), default="B2B Optimization & Automation Package")
    service_type: Mapped[str] = mapped_column(String(100), default="Website Turnaround")
    total_value: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=1000.0)
    advance_required: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=500.0)
    advance_received: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=0.0)
    remaining_balance: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=1000.0)
    
    # State Machine: DRAFT -> APPROVED -> PAYMENT_REQUESTED -> PAYMENT_PENDING -> ADVANCE_RECEIVED -> PAID -> WON
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", index=True)
    delivery_status: Mapped[str] = mapped_column(String(50), default="NOT_STARTED", index=True)  # NOT_STARTED, READY_TO_START, IN_PROGRESS, COMPLETED
    
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    payment_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    extra_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

# 17c. Commercial Deals
class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), index=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    proposal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    
    title: Mapped[str] = mapped_column(String(255))
    service_type: Mapped[str] = mapped_column(String(100), default="Technical Engagement")
    total_value: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=1000.0)
    advance_required: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=500.0)
    cash_received: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=0.0)
    outstanding_balance: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=1000.0)
    
    status: Mapped[str] = mapped_column(String(50), default="PROPOSAL_DRAFT", index=True)
    delivery_status: Mapped[str] = mapped_column(String(50), default="NOT_STARTED", index=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 17d. Deal Audit Trail
class DealAuditTrail(Base):
    __tablename__ = "deal_audit_trail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    proposal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    business_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    
    event_type: Mapped[str] = mapped_column(String(100), index=True)  # proposal_created, proposal_approved, payment_requested, payment_succeeded, payment_failed, advance_received, deal_won, delivery_unlocked
    operator: Mapped[Optional[str]] = mapped_column(String(100), default="system")
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# 18. Suppression List
class SuppressionList(Base):
    __tablename__ = "suppression_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(100), default="UNSUBSCRIBE")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# 19. System Runs
class SystemRun(Base):
    __tablename__ = "system_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    job_name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING")
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    error_log: Mapped[Optional[str]] = mapped_column(Text, default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

# 20. Agent Tasks
class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String(100))
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# 21. Voice Call Logs
class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=True, index=True)
    call_sid: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    caller_id: Mapped[str] = mapped_column(String(50))
    recipient_phone: Mapped[str] = mapped_column(String(50), index=True)
    direction: Mapped[str] = mapped_column(String(20), default="OUTBOUND")
    status: Mapped[str] = mapped_column(String(50), default="INITIATED")  # INITIATED, RINGING, IN_PROGRESS, COMPLETED, BUSY, NO_ANSWER, FAILED
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    recording_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    recording_consent_disclosed: Mapped[bool] = mapped_column(Boolean, default=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sentiment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    qualification_intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    action_taken: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    call_state: Mapped[str] = mapped_column(String(50), default="CALL_INITIATED", index=True)
    previous_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    escalation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    agreed_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    objections_detected: Mapped[List[str]] = mapped_column(JSON, default=list)
    context_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

# 22. Scheduled Meetings
class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=True, index=True)
    prospect_name: Mapped[str] = mapped_column(String(255))
    prospect_contact: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(255), default="Diagnostic Walkthrough & Strategy Consultation")
    scheduled_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    meeting_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="SCHEDULED")  # SCHEDULED, COMPLETED, CANCELLED, NO_SHOW
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# 23. Event-Driven Prospect Memory
class ProspectMemory(Base):
    __tablename__ = "prospect_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), unique=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    call_sid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    payment_link_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    channel_used: Mapped[str] = mapped_column(String(50), default="EMAIL")
    pipeline_stage: Mapped[str] = mapped_column(String(50), default="CONTACTED")

    audit_results: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    buyer_score: Mapped[float] = mapped_column(Float, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_value: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=500.0)

    offer_proposal: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    outreach_message: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    last_interaction: Mapped[str] = mapped_column(Text, default="")
    next_expected_action: Mapped[str] = mapped_column(String(100), default="AWAITING_INBOUND_EVENT")
    conversation_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    objection_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    proposal_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    meeting_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    payment_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    human_decisions: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    suppression_state: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    commercial_context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    business: Mapped["Business"] = relationship("Business", back_populates="memory", lazy="selectin")


# 24. Live Agent Activity Events
class AgentActivityEvent(Base):
    __tablename__ = "agent_activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(100), index=True)
    business_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=True, index=True)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50), default="INFO")  # INFO, SUCCESS, WARNING, FAILED
    message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    sequence_number: Mapped[int] = mapped_column(Integer, default=0, index=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    business: Mapped[Optional["Business"]] = relationship("Business", back_populates="activity_events", lazy="selectin")


# 25. Artifact Storage & Website Previews
class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=True, index=True)
    prospect_memory_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("prospect_memories.id"), nullable=True, index=True)
    artifact_type: Mapped[str] = mapped_column(String(50), index=True)  # WEBSITE, EMAIL, AUDIT_REPORT, PROPOSAL, CODE, OTHER
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    status: Mapped[str] = mapped_column(String(50), default="READY")  # BUILDING, READY, FAILED
    path: Mapped[str] = mapped_column(String(500), default="")
    preview_url: Mapped[str] = mapped_column(String(500), default="")
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business: Mapped[Optional["Business"]] = relationship("Business", back_populates="artifacts", lazy="selectin")


# Backward-compatibility alias
LocalBusiness = Business

# 26. Machine Learning Foundation & Intelligence Lifecycle
from app.database.ml_models import (
    ModelVersion,
    ModelPrediction,
    Experiment,
    Outcome,
    ModelStatus,
    ExperimentStatus
)

# 27. System Authentication & Users
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="admin")  # owner, admin, viewer, operator, client
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    is_setup_completed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped[Optional["Customer"]] = relationship("Customer", lazy="selectin")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", backref="reset_tokens", lazy="selectin")


# 28. Client Intelligence & Service Matching Records
class ClientIntelligenceRecord(Base):
    __tablename__ = "client_intelligence_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), unique=True, index=True)
    segment: Mapped[str] = mapped_column(String(50), default="small")
    top_service_id: Mapped[str] = mapped_column(String(50), default="SERVICE_001", index=True)
    top_service_name: Mapped[str] = mapped_column(String(200), default="AI Lead Qualification")
    fit_score: Mapped[float] = mapped_column(Float, default=0.5)
    p_win: Mapped[float] = mapped_column(Float, default=0.5)
    selection_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    recommended_price_usd: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=1000.0)
    target_price_usd: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), default=1000.0)
    trace_id: Mapped[str] = mapped_column(String(100), default="")
    
    full_profile: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    pain_points: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    service_matches: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    roi_estimate: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    client_offer: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    why_this_business: Mapped[List[str]] = mapped_column(JSON, default=list)
    decision_trace: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business: Mapped["Business"] = relationship("Business", back_populates="client_intelligence", lazy="selectin")


# 29. Payment Webhook Events (Idempotency & Audit)
class PaymentWebhookEvent(Base):
    __tablename__ = "payment_webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)  # razorpay, stripe
    event_id: Mapped[str] = mapped_column(String(255), index=True)  # external event id
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(50), default="RECEIVED", index=True)  # RECEIVED, PROCESSING, PROCESSED, DUPLICATE, FAILED
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    payload_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    outcome: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event_id"),
    )


# 30. Security & Operational Audit Log
class SecurityAuditLog(Base):
    __tablename__ = "security_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(100), index=True)  # user, system, webhook, api_client
    action: Mapped[str] = mapped_column(String(100), index=True)  # auth.login, auth.setup_password, payment.received, etc.
    entity_type: Mapped[str] = mapped_column(String(100), index=True)  # user, proposal, payment, deal, business
    entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # WHY
    result: Mapped[str] = mapped_column(String(50), default="SUCCESS", index=True)  # SUCCESS, FAILURE, DENIED
    details_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)  # Sanitized (no secrets/passwords)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_audit_action_created", "action", "created_at"),
        Index("ix_audit_actor_created", "actor", "created_at"),
    )


# 31. Multi-Country Configuration & Pipelines
class CountryConfig(Base):
    __tablename__ = "country_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    country_name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    language: Mapped[str] = mapped_column(String(20), default="en")
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    target_cities: Mapped[List[str]] = mapped_column(JSON, default=list)
    target_niches: Mapped[List[str]] = mapped_column(JSON, default=list)
    discovery_query_templates: Mapped[List[str]] = mapped_column(JSON, default=list)
    qualification_rules: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    outreach_rules: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    compliance_settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    max_daily_discovery: Mapped[int] = mapped_column(Integer, default=50)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# 32. Sequential Active Prospect Outreach Lock (Enforces MAX_ACTIVE_OUTREACH = 1)
class ActiveOutreachLock(Base):
    __tablename__ = "active_outreach_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(Integer, unique=True, default=1, index=True)
    business_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=True, index=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lease_timeout_seconds: Mapped[int] = mapped_column(Integer, default=604800)  # 7 days
    status: Mapped[str] = mapped_column(String(50), default="IDLE", index=True)  # IDLE, ACTIVE, WAITING_FOR_REPLY, NEGOTIATING, RELEASED
    acquired_by: Mapped[str] = mapped_column(String(100), default="orchestrator")
    current_stage: Mapped[str] = mapped_column(String(50), default="NONE")
    waiting_since: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business: Mapped[Optional["Business"]] = relationship("Business", lazy="selectin")


# 33. Global Acquisition Runs
class AcquisitionRun(Base):
    __tablename__ = "acquisition_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)  # PENDING, RUNNING, COMPLETED, FAILED
    countries_targeted: Mapped[List[str]] = mapped_column(JSON, default=list)
    prospects_discovered: Mapped[int] = mapped_column(Integer, default=0)
    prospects_verified: Mapped[int] = mapped_column(Integer, default=0)
    prospects_qualified: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# 34. Country Market Profile (Phase 11 Market Intelligence)
class CountryMarketProfile(Base):
    __tablename__ = "country_market_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    country_name: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(50), default="Global")
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    primary_languages: Mapped[List[str]] = mapped_column(JSON, default=list)
    secondary_languages: Mapped[List[str]] = mapped_column(JSON, default=list)

    population_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    business_density_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sme_density_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    gdp_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gdp_per_capita_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    business_activity_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    ai_adoption_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    automation_adoption_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    digital_maturity_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    ai_investment_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    technology_investment_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    ability_to_pay_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high_ticket_service_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    labor_cost_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    labor_shortage_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    automation_pain_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    market_growth_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    service_demand_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    competition_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    agency_saturation_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    contactability_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data_availability_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_quality_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_freshness_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    compliance_risk_signal: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    outreach_risk_signal: Mapped[str] = mapped_column(String(20), default="UNKNOWN")

    research_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True)
    research_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_refresh_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.1)

    decision_trace: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# 35. Niche Market Profile
class NicheMarketProfile(Base):
    __tablename__ = "niche_market_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    niche_slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(100), default="General")

    typical_lead_value_usd: Mapped[float] = mapped_column(Float, default=500.0)
    missed_lead_pain_severity: Mapped[float] = mapped_column(Float, default=0.5)
    automation_potential: Mapped[float] = mapped_column(Float, default=0.5)
    inquiry_velocity: Mapped[float] = mapped_column(Float, default=0.5)
    baseline_ability_to_pay: Mapped[float] = mapped_column(Float, default=0.5)
    suitable_services: Mapped[List[str]] = mapped_column(JSON, default=list)

    research_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# 36. Market Evidence
class MarketEvidence(Base):
    __tablename__ = "market_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    country_code: Mapped[str] = mapped_column(String(10), index=True)
    niche_slug: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    service_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    claim: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(1000))
    source_domain: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(50), default="public_web")
    source_tier: Mapped[int] = mapped_column(Integer, default=3)  # 1=Official/Gov, 2=Established Research, 3=Directory/Web
    publisher: Mapped[str] = mapped_column(String(255), default="Unknown")
    publication_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    raw_excerpt: Mapped[str] = mapped_column(Text)
    signal_type: Mapped[str] = mapped_column(String(50), index=True)

    source_quality_score: Mapped[float] = mapped_column(Float, default=0.5)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.5)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)

    supports_claim: Mapped[bool] = mapped_column(Boolean, default=True)
    contradicts_claim: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# 37. Market Signal
class MarketSignal(Base):
    __tablename__ = "market_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(String(10), index=True)
    niche_slug: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    service_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    signal_type: Mapped[str] = mapped_column(String(50), index=True)

    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(50), default="normalized")
    direction: Mapped[str] = mapped_column(String(20), default="NEUTRAL")  # POSITIVE, NEGATIVE, NEUTRAL
    confidence: Mapped[float] = mapped_column(Float, default=0.1)
    evidence_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# 38. Country × Niche × Service Opportunity
class CountryNicheOpportunity(Base):
    __tablename__ = "country_niche_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(String(10), index=True)
    niche_slug: Mapped[str] = mapped_column(String(100), index=True)
    service_id: Mapped[str] = mapped_column(String(50), index=True)
    opportunity_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)

    market_score: Mapped[float] = mapped_column(Float, default=50.0, index=True)
    demand_score: Mapped[float] = mapped_column(Float, default=50.0)
    ability_to_pay_score: Mapped[float] = mapped_column(Float, default=50.0)
    automation_score: Mapped[float] = mapped_column(Float, default=50.0)
    ai_adoption_score: Mapped[float] = mapped_column(Float, default=50.0)
    digital_maturity_score: Mapped[float] = mapped_column(Float, default=50.0)
    business_density_score: Mapped[float] = mapped_column(Float, default=50.0)
    pain_probability_score: Mapped[float] = mapped_column(Float, default=50.0)
    service_fit_score: Mapped[float] = mapped_column(Float, default=50.0)
    growth_score: Mapped[float] = mapped_column(Float, default=50.0)
    contactability_score: Mapped[float] = mapped_column(Float, default=50.0)

    competition_penalty: Mapped[float] = mapped_column(Float, default=0.0)
    compliance_penalty: Mapped[float] = mapped_column(Float, default=0.0)
    uncertainty_penalty: Mapped[float] = mapped_column(Float, default=0.0)

    expected_deal_value_usd: Mapped[float] = mapped_column(Float, default=1000.0)
    p_contact: Mapped[float] = mapped_column(Float, default=0.7)
    p_fit: Mapped[float] = mapped_column(Float, default=0.7)
    p_deal: Mapped[float] = mapped_column(Float, default=0.2)
    expected_value_usd: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.5, index=True)
    research_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    freshest_evidence_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    decision_trace: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    scoring_weights: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


# 39. Market Research Runs
class MarketResearchRun(Base):
    __tablename__ = "market_research_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    countries_researched: Mapped[List[str]] = mapped_column(JSON, default=list)
    niches_researched: Mapped[List[str]] = mapped_column(JSON, default=list)
    evidence_collected: Mapped[int] = mapped_column(Integer, default=0)
    opportunities_created: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# 40. Prospect Evidence
class ProspectEvidence(Base):
    __tablename__ = "prospect_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), index=True)

    claim: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(1000))
    source_domain: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(50), default="public_web")
    source_tier: Mapped[int] = mapped_column(Integer, default=3)
    publisher: Mapped[str] = mapped_column(String(255), default="Unknown")

    raw_excerpt: Mapped[str] = mapped_column(Text)
    evidence_category: Mapped[str] = mapped_column(String(50), default="business_identity")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    source_quality_score: Mapped[float] = mapped_column(Float, default=0.5)
    freshness_score: Mapped[float] = mapped_column(Float, default=1.0)

    is_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=200)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="VERIFIED")  # VERIFIED, UNVERIFIED, UNREACHABLE, REJECTED
    verification_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_identity_match: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=True)
    source_independence_group: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    business: Mapped["Business"] = relationship("Business", back_populates="evidence_items")


# 41. Discovery Run
class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    country_code: Mapped[str] = mapped_column(String(10), index=True)
    niche_slug: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING")

    prospects_discovered: Mapped[int] = mapped_column(Integer, default=0)
    prospects_verified: Mapped[int] = mapped_column(Integer, default=0)
    prospects_rejected: Mapped[int] = mapped_column(Integer, default=0)
    evidence_items_extracted: Mapped[int] = mapped_column(Integer, default=0)

    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# 42. Autonomous Decision Audit Log (Phase 15 Full Observability)
class AutonomousDecisionLog(Base):
    __tablename__ = "autonomous_decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    business_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    decision: Mapped[str] = mapped_column(String(50), index=True)  # AUTO_APPROVE, BLOCK, HUMAN_REVIEW, SELECT, OUTREACH, TERMINAL, etc.
    policy_checklist: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    reasons: Mapped[List[str]] = mapped_column(JSON, default=list)
    evidence_ids: Mapped[List[int]] = mapped_column(JSON, default=list)
    score_inputs: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    service_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    service_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    previous_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    next_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    business: Mapped[Optional["Business"]] = relationship("Business", lazy="selectin")









