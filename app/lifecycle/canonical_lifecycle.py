"""
Canonical Lifecycle Module — Mega Prompt 9.
Unified Commercial and Operational Lifecycle State Machine.
Reconciles Acquisition, Sales, Payment, Delivery, and Customer Support.
"""
import enum
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database.models import (
    Business, Customer, Project, SupportTicket, CustomerIncident,
    PipelineEvent, PipelineStage
)
from app.core.config import settings

logger = logging.getLogger("agency.lifecycle")


class CanonicalLifecycleStage(str, enum.Enum):
    # 1. Acquisition & Prioritization
    DISCOVERED = "DISCOVERED"
    QUALIFIED = "QUALIFIED"
    PRIORITIZED = "PRIORITIZED"
    CONTACTABLE = "CONTACTABLE"

    # 2. Outreach & Engagement
    OUTREACH_ELIGIBLE = "OUTREACH_ELIGIBLE"
    OUTREACH_SENT = "OUTREACH_SENT"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    POSITIVE = "POSITIVE"

    # 3. Sales, Demo & Proposal
    DEMO_ELIGIBLE = "DEMO_ELIGIBLE"
    DEMO_READY = "DEMO_READY"
    PROPOSAL_READY = "PROPOSAL_READY"
    PROPOSAL_ACCEPTED = "PROPOSAL_ACCEPTED"

    # 4. Financial Verification (Strict Gate)
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_VERIFIED = "PAYMENT_VERIFIED"
    DELIVERY_UNLOCKED = "DELIVERY_UNLOCKED"

    # 5. Delivery, QA & Production
    ONBOARDING = "ONBOARDING"
    BUILDING = "BUILDING"
    QA = "QA"
    DEPLOYING = "DEPLOYING"
    LIVE = "LIVE"

    # 6. Customer Success & Retention
    RETAINED = "RETAINED"

    # --- Exception & Branching States ---
    NEGATIVE = "NEGATIVE"
    UNSUBSCRIBED = "UNSUBSCRIBED"
    DO_NOT_CONTACT = "DO_NOT_CONTACT"
    WAITING_FOR_CUSTOMER = "WAITING_FOR_CUSTOMER"
    WAITING_FOR_EXTERNAL_PROVIDER = "WAITING_FOR_EXTERNAL_PROVIDER"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"
    DELIVERY_BLOCKED = "DELIVERY_BLOCKED"
    SUPPORT_INCIDENT = "SUPPORT_INCIDENT"


class CanonicalTransitionAudit(BaseModel):
    transition_id: str = Field(default_factory=lambda: f"TR-{uuid.uuid4().hex[:8].upper()}")
    business_id: int
    customer_id: Optional[int] = None
    from_stage: Optional[CanonicalLifecycleStage] = None
    to_stage: CanonicalLifecycleStage
    actor: str = "system"
    reason: str
    idempotency_key: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CanonicalLifecycleManager:
    """
    Central deterministic authority governing transitions across the entire
    21-stage revenue, delivery, support, and retention lifecycle.
    """

    # Comprehensive state transition graph
    VALID_TRANSITIONS: Dict[CanonicalLifecycleStage, List[CanonicalLifecycleStage]] = {
        # Acquisition
        CanonicalLifecycleStage.DISCOVERED: [
            CanonicalLifecycleStage.QUALIFIED,
            CanonicalLifecycleStage.DO_NOT_CONTACT
        ],
        CanonicalLifecycleStage.QUALIFIED: [
            CanonicalLifecycleStage.PRIORITIZED,
            CanonicalLifecycleStage.DO_NOT_CONTACT
        ],
        CanonicalLifecycleStage.PRIORITIZED: [
            CanonicalLifecycleStage.CONTACTABLE,
            CanonicalLifecycleStage.DO_NOT_CONTACT
        ],
        CanonicalLifecycleStage.CONTACTABLE: [
            CanonicalLifecycleStage.OUTREACH_ELIGIBLE,
            CanonicalLifecycleStage.DO_NOT_CONTACT
        ],
        # Outreach
        CanonicalLifecycleStage.OUTREACH_ELIGIBLE: [
            CanonicalLifecycleStage.OUTREACH_SENT,
            CanonicalLifecycleStage.DO_NOT_CONTACT,
            CanonicalLifecycleStage.WAITING_FOR_CUSTOMER
        ],
        CanonicalLifecycleStage.OUTREACH_SENT: [
            CanonicalLifecycleStage.RESPONSE_RECEIVED,
            CanonicalLifecycleStage.WAITING_FOR_CUSTOMER,
            CanonicalLifecycleStage.DO_NOT_CONTACT
        ],
        CanonicalLifecycleStage.RESPONSE_RECEIVED: [
            CanonicalLifecycleStage.POSITIVE,
            CanonicalLifecycleStage.NEGATIVE,
            CanonicalLifecycleStage.UNSUBSCRIBED,
            CanonicalLifecycleStage.DO_NOT_CONTACT,
            CanonicalLifecycleStage.ESCALATED
        ],
        CanonicalLifecycleStage.POSITIVE: [
            CanonicalLifecycleStage.DEMO_ELIGIBLE,
            CanonicalLifecycleStage.PROPOSAL_READY,
            CanonicalLifecycleStage.WAITING_FOR_CUSTOMER,
            CanonicalLifecycleStage.ESCALATED
        ],
        # Sales & Demo
        CanonicalLifecycleStage.DEMO_ELIGIBLE: [
            CanonicalLifecycleStage.DEMO_READY,
            CanonicalLifecycleStage.WAITING_FOR_EXTERNAL_PROVIDER,
            CanonicalLifecycleStage.ESCALATED
        ],
        CanonicalLifecycleStage.DEMO_READY: [
            CanonicalLifecycleStage.PROPOSAL_READY,
            CanonicalLifecycleStage.DEMO_ELIGIBLE,  # changes requested / rebuild
            CanonicalLifecycleStage.WAITING_FOR_CUSTOMER,
            CanonicalLifecycleStage.NEGATIVE
        ],
        CanonicalLifecycleStage.PROPOSAL_READY: [
            CanonicalLifecycleStage.PROPOSAL_ACCEPTED,
            CanonicalLifecycleStage.WAITING_FOR_CUSTOMER,
            CanonicalLifecycleStage.NEGATIVE,
            CanonicalLifecycleStage.CANCELLED
        ],
        CanonicalLifecycleStage.PROPOSAL_ACCEPTED: [
            CanonicalLifecycleStage.PAYMENT_PENDING,
            CanonicalLifecycleStage.CANCELLED
        ],
        # Payment Gate
        CanonicalLifecycleStage.PAYMENT_PENDING: [
            CanonicalLifecycleStage.PAYMENT_VERIFIED,
            CanonicalLifecycleStage.PAYMENT_FAILED,
            CanonicalLifecycleStage.WAITING_FOR_CUSTOMER,
            CanonicalLifecycleStage.CANCELLED
        ],
        CanonicalLifecycleStage.PAYMENT_VERIFIED: [
            CanonicalLifecycleStage.DELIVERY_UNLOCKED
        ],
        CanonicalLifecycleStage.DELIVERY_UNLOCKED: [
            CanonicalLifecycleStage.ONBOARDING,
            CanonicalLifecycleStage.DELIVERY_BLOCKED
        ],
        # Delivery & QA
        CanonicalLifecycleStage.ONBOARDING: [
            CanonicalLifecycleStage.BUILDING,
            CanonicalLifecycleStage.WAITING_FOR_CUSTOMER,
            CanonicalLifecycleStage.DELIVERY_BLOCKED
        ],
        CanonicalLifecycleStage.BUILDING: [
            CanonicalLifecycleStage.QA,
            CanonicalLifecycleStage.WAITING_FOR_EXTERNAL_PROVIDER,
            CanonicalLifecycleStage.DELIVERY_BLOCKED
        ],
        CanonicalLifecycleStage.QA: [
            CanonicalLifecycleStage.DEPLOYING,
            CanonicalLifecycleStage.BUILDING,  # QA rejected, rebuild required
            CanonicalLifecycleStage.DELIVERY_BLOCKED,
            CanonicalLifecycleStage.ESCALATED
        ],
        CanonicalLifecycleStage.DEPLOYING: [
            CanonicalLifecycleStage.LIVE,
            CanonicalLifecycleStage.DELIVERY_BLOCKED,
            CanonicalLifecycleStage.SUPPORT_INCIDENT
        ],
        CanonicalLifecycleStage.LIVE: [
            CanonicalLifecycleStage.RETAINED,
            CanonicalLifecycleStage.SUPPORT_INCIDENT,
            CanonicalLifecycleStage.CANCELLED
        ],
        # Retained
        CanonicalLifecycleStage.RETAINED: [
            CanonicalLifecycleStage.SUPPORT_INCIDENT,
            CanonicalLifecycleStage.PROPOSAL_READY,  # Upsell
            CanonicalLifecycleStage.CANCELLED
        ],
        # Exception states & recovery
        CanonicalLifecycleStage.SUPPORT_INCIDENT: [
            CanonicalLifecycleStage.LIVE,
            CanonicalLifecycleStage.RETAINED,
            CanonicalLifecycleStage.ESCALATED,
            CanonicalLifecycleStage.DELIVERY_BLOCKED
        ],
        CanonicalLifecycleStage.DELIVERY_BLOCKED: [
            CanonicalLifecycleStage.ONBOARDING,
            CanonicalLifecycleStage.BUILDING,
            CanonicalLifecycleStage.QA,
            CanonicalLifecycleStage.DEPLOYING,
            CanonicalLifecycleStage.ESCALATED
        ],
        CanonicalLifecycleStage.PAYMENT_FAILED: [
            CanonicalLifecycleStage.PAYMENT_PENDING,
            CanonicalLifecycleStage.CANCELLED
        ],
        CanonicalLifecycleStage.WAITING_FOR_CUSTOMER: [
            CanonicalLifecycleStage.OUTREACH_ELIGIBLE,
            CanonicalLifecycleStage.RESPONSE_RECEIVED,
            CanonicalLifecycleStage.POSITIVE,
            CanonicalLifecycleStage.PROPOSAL_ACCEPTED,
            CanonicalLifecycleStage.PAYMENT_VERIFIED,
            CanonicalLifecycleStage.ONBOARDING,
            CanonicalLifecycleStage.CANCELLED
        ],
        CanonicalLifecycleStage.WAITING_FOR_EXTERNAL_PROVIDER: [
            CanonicalLifecycleStage.DEMO_READY,
            CanonicalLifecycleStage.BUILDING,
            CanonicalLifecycleStage.QA,
            CanonicalLifecycleStage.DEPLOYING,
            CanonicalLifecycleStage.ESCALATED
        ],
        CanonicalLifecycleStage.ESCALATED: [
            CanonicalLifecycleStage.POSITIVE,
            CanonicalLifecycleStage.DEMO_READY,
            CanonicalLifecycleStage.PROPOSAL_READY,
            CanonicalLifecycleStage.PAYMENT_VERIFIED,
            CanonicalLifecycleStage.BUILDING,
            CanonicalLifecycleStage.LIVE,
            CanonicalLifecycleStage.RETAINED,
            CanonicalLifecycleStage.CANCELLED
        ],
        CanonicalLifecycleStage.NEGATIVE: [],
        CanonicalLifecycleStage.UNSUBSCRIBED: [],
        CanonicalLifecycleStage.DO_NOT_CONTACT: [],
        CanonicalLifecycleStage.CANCELLED: []
    }

    @classmethod
    def can_transition(
        cls,
        from_stage: CanonicalLifecycleStage,
        to_stage: CanonicalLifecycleStage
    ) -> Tuple[bool, str]:
        """Validates whether a transition from one stage to another is permitted."""
        if from_stage == to_stage:
            return True, "No-op transition (already in target stage)."

        allowed = cls.VALID_TRANSITIONS.get(from_stage, [])
        if to_stage in allowed:
            return True, f"Transition from {from_stage.value} to {to_stage.value} is valid."

        return False, (
            f"Invalid transition from {from_stage.value} to {to_stage.value}. "
            f"Allowed next stages: {[s.value for s in allowed]}"
        )

    @classmethod
    def map_to_canonical(
        cls,
        business: Business,
        customer: Optional[Customer] = None,
        project: Optional[Project] = None,
        active_incident: Optional[CustomerIncident] = None
    ) -> CanonicalLifecycleStage:
        """
        Reconciles disparate model statuses across Business, Customer, Project, and Support
        into a single canonical lifecycle stage without modifying the database schema.
        """
        if active_incident and not active_incident.is_resolved:
            return CanonicalLifecycleStage.SUPPORT_INCIDENT

        if customer:
            status = (customer.onboarding_status or "").upper()
            if status in ("LIVE", "CUSTOMER_ACTIVE", "HANDOVER_DELIVERED"):
                return CanonicalLifecycleStage.LIVE
            if status == "RETAINED":
                return CanonicalLifecycleStage.RETAINED
            if status == "BUILDING":
                return CanonicalLifecycleStage.BUILDING
            if status == "QA":
                return CanonicalLifecycleStage.QA
            if status == "DEPLOYING":
                return CanonicalLifecycleStage.DEPLOYING
            if status in ("PENDING_ONBOARDING", "ONBOARDING"):
                return CanonicalLifecycleStage.ONBOARDING
            if status == "PAYMENT_VERIFIED":
                return CanonicalLifecycleStage.DELIVERY_UNLOCKED

        if project:
            p_status = (project.status or "").upper()
            if p_status == "READY":
                return CanonicalLifecycleStage.LIVE
            if p_status in ("BUILDING", "AI_PROTOTYPING", "DESIGNING"):
                return CanonicalLifecycleStage.BUILDING
            if p_status in ("QA", "REPAIRING"):
                return CanonicalLifecycleStage.QA
            if p_status == "DEPLOYING":
                return CanonicalLifecycleStage.DEPLOYING
            if p_status == "BLOCKED":
                return CanonicalLifecycleStage.DELIVERY_BLOCKED

        stage_str = (business.pipeline_stage or "").upper()
        mapping = {
            "DISCOVERED": CanonicalLifecycleStage.DISCOVERED,
            "VERIFIED": CanonicalLifecycleStage.QUALIFIED,
            "AUDITED": CanonicalLifecycleStage.QUALIFIED,
            "QUALIFIED": CanonicalLifecycleStage.QUALIFIED,
            "PRIORITIZED": CanonicalLifecycleStage.PRIORITIZED,
            "CONTACTABLE": CanonicalLifecycleStage.CONTACTABLE,
            "OUTREACH_READY": CanonicalLifecycleStage.OUTREACH_ELIGIBLE,
            "OUTREACH_ELIGIBLE": CanonicalLifecycleStage.OUTREACH_ELIGIBLE,
            "APPROVAL": CanonicalLifecycleStage.OUTREACH_ELIGIBLE,
            "CONTACTED": CanonicalLifecycleStage.OUTREACH_SENT,
            "OUTREACH_SENT": CanonicalLifecycleStage.OUTREACH_SENT,
            "REPLIED": CanonicalLifecycleStage.RESPONSE_RECEIVED,
            "RESPONSE_RECEIVED": CanonicalLifecycleStage.RESPONSE_RECEIVED,
            "QUALIFIED_REPLY": CanonicalLifecycleStage.POSITIVE,
            "POSITIVE": CanonicalLifecycleStage.POSITIVE,
            "DEMO_REQUESTED": CanonicalLifecycleStage.DEMO_ELIGIBLE,
            "DEMO_ELIGIBLE": CanonicalLifecycleStage.DEMO_ELIGIBLE,
            "DEMO_BUILDING": CanonicalLifecycleStage.DEMO_ELIGIBLE,
            "DEMO_SPEC_READY": CanonicalLifecycleStage.DEMO_ELIGIBLE,
            "DEMO_READY": CanonicalLifecycleStage.DEMO_READY,
            "DEMO_DELIVERED": CanonicalLifecycleStage.DEMO_READY,
            "CALL": CanonicalLifecycleStage.POSITIVE,
            "MEETING": CanonicalLifecycleStage.POSITIVE,
            "PROPOSAL": CanonicalLifecycleStage.PROPOSAL_READY,
            "PROPOSAL_READY": CanonicalLifecycleStage.PROPOSAL_READY,
            "PROPOSAL_ACCEPTED": CanonicalLifecycleStage.PROPOSAL_ACCEPTED,
            "PAYMENT_REQUESTED": CanonicalLifecycleStage.PAYMENT_PENDING,
            "PAYMENT_PENDING": CanonicalLifecycleStage.PAYMENT_PENDING,
            "ADVANCE_PAID": CanonicalLifecycleStage.PAYMENT_VERIFIED,
            "PAYMENT_VERIFIED": CanonicalLifecycleStage.PAYMENT_VERIFIED,
            "DELIVERY_UNLOCKED": CanonicalLifecycleStage.DELIVERY_UNLOCKED,
            "IN_DELIVERY": CanonicalLifecycleStage.BUILDING,
            "ONBOARDING": CanonicalLifecycleStage.ONBOARDING,
            "BUILDING": CanonicalLifecycleStage.BUILDING,
            "QA": CanonicalLifecycleStage.QA,
            "DEPLOYING": CanonicalLifecycleStage.DEPLOYING,
            "COMPLETED": CanonicalLifecycleStage.LIVE,
            "LIVE": CanonicalLifecycleStage.LIVE,
            "RETAINED": CanonicalLifecycleStage.RETAINED,
            "WON": CanonicalLifecycleStage.PAYMENT_VERIFIED,
            "LOST": CanonicalLifecycleStage.NEGATIVE,
            "NEGATIVE": CanonicalLifecycleStage.NEGATIVE,
            "UNSUBSCRIBED": CanonicalLifecycleStage.UNSUBSCRIBED,
            "REJECTED": CanonicalLifecycleStage.DO_NOT_CONTACT,
            "COLD": CanonicalLifecycleStage.WAITING_FOR_CUSTOMER,
            "WAITING_FOR_CUSTOMER": CanonicalLifecycleStage.WAITING_FOR_CUSTOMER,
            "WAITING_FOR_EXTERNAL_PROVIDER": CanonicalLifecycleStage.WAITING_FOR_EXTERNAL_PROVIDER,
            "DEAD": CanonicalLifecycleStage.DO_NOT_CONTACT,
            "DO_NOT_CONTACT": CanonicalLifecycleStage.DO_NOT_CONTACT,
            "PAYMENT_FAILED": CanonicalLifecycleStage.PAYMENT_FAILED,
            "DELIVERY_BLOCKED": CanonicalLifecycleStage.DELIVERY_BLOCKED,
            "SUPPORT_INCIDENT": CanonicalLifecycleStage.SUPPORT_INCIDENT,
            "ESCALATED": CanonicalLifecycleStage.ESCALATED,
            "CANCELLED": CanonicalLifecycleStage.CANCELLED
        }
        return mapping.get(stage_str, CanonicalLifecycleStage.DISCOVERED)

    @classmethod
    async def transition(
        cls,
        session: AsyncSession,
        business_id: int,
        target_stage: CanonicalLifecycleStage,
        actor: str = "orchestrator",
        reason: str = "Canonical pipeline progression",
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CanonicalTransitionAudit:
        """
        Executes an audited state transition. Enforces deterministic rules
        and updates underlying DB models via adapters.
        """
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business #{business_id} not found.")

        # Check existing customer / project / incidents for full context
        stmt_cust = select(Customer).where(Customer.business_id == business_id)
        customer = (await session.execute(stmt_cust)).scalar_one_or_none()

        project = None
        if customer:
            stmt_proj = select(Project).where(Project.customer_id == customer.id).order_by(desc(Project.id))
            project = (await session.execute(stmt_proj)).scalars().first()

        stmt_inc = select(CustomerIncident).where(
            CustomerIncident.business_id == business_id,
            CustomerIncident.is_resolved == False
        )
        active_inc = (await session.execute(stmt_inc)).scalars().first()

        current_canonical = cls.map_to_canonical(biz, customer, project, active_inc)

        # Idempotency check: If already in target stage, return audit no-op safely
        if current_canonical == target_stage:
            return CanonicalTransitionAudit(
                business_id=business_id,
                customer_id=customer.id if customer else None,
                from_stage=current_canonical,
                to_stage=target_stage,
                actor=actor,
                reason=f"Idempotent: Already in stage {target_stage.value}",
                idempotency_key=idempotency_key,
                metadata=metadata or {}
            )

        # Check transition permission
        valid, err_msg = cls.can_transition(current_canonical, target_stage)
        if not valid:
            raise ValueError(f"Policy Gate Denied Transition: {err_msg}")

        # Update underlying DB models based on target stage
        if target_stage == CanonicalLifecycleStage.DISCOVERED:
            biz.pipeline_stage = PipelineStage.DISCOVERED.value
        elif target_stage == CanonicalLifecycleStage.QUALIFIED:
            biz.pipeline_stage = PipelineStage.QUALIFIED.value
        elif target_stage == CanonicalLifecycleStage.PRIORITIZED:
            biz.pipeline_stage = "PRIORITIZED"
        elif target_stage == CanonicalLifecycleStage.CONTACTABLE:
            biz.pipeline_stage = "CONTACTABLE"
        elif target_stage == CanonicalLifecycleStage.OUTREACH_ELIGIBLE:
            biz.pipeline_stage = PipelineStage.OUTREACH_READY.value
        elif target_stage == CanonicalLifecycleStage.OUTREACH_SENT:
            biz.pipeline_stage = PipelineStage.CONTACTED.value
        elif target_stage == CanonicalLifecycleStage.RESPONSE_RECEIVED:
            biz.pipeline_stage = PipelineStage.REPLIED.value
        elif target_stage == CanonicalLifecycleStage.POSITIVE:
            biz.pipeline_stage = PipelineStage.QUALIFIED_REPLY.value
        elif target_stage == CanonicalLifecycleStage.DEMO_ELIGIBLE:
            biz.pipeline_stage = PipelineStage.DEMO_REQUESTED.value
        elif target_stage == CanonicalLifecycleStage.DEMO_READY:
            biz.pipeline_stage = PipelineStage.DEMO_READY.value
        elif target_stage == CanonicalLifecycleStage.PROPOSAL_READY:
            biz.pipeline_stage = PipelineStage.PROPOSAL.value
        elif target_stage == CanonicalLifecycleStage.PROPOSAL_ACCEPTED:
            biz.pipeline_stage = "PROPOSAL_ACCEPTED"
        elif target_stage == CanonicalLifecycleStage.PAYMENT_PENDING:
            biz.pipeline_stage = PipelineStage.PAYMENT_REQUESTED.value
        elif target_stage == CanonicalLifecycleStage.PAYMENT_VERIFIED:
            biz.pipeline_stage = "PAYMENT_VERIFIED"
            if customer:
                customer.onboarding_status = "PAYMENT_VERIFIED"
        elif target_stage == CanonicalLifecycleStage.DELIVERY_UNLOCKED:
            biz.pipeline_stage = "DELIVERY_UNLOCKED"
            if customer:
                customer.onboarding_status = "PAYMENT_VERIFIED"
        elif target_stage == CanonicalLifecycleStage.ONBOARDING:
            biz.pipeline_stage = "ONBOARDING"
            if customer:
                customer.onboarding_status = "ONBOARDING"
        elif target_stage == CanonicalLifecycleStage.BUILDING:
            biz.pipeline_stage = PipelineStage.IN_DELIVERY.value
            if customer:
                customer.onboarding_status = "BUILDING"
            if project:
                project.status = "BUILDING"
        elif target_stage == CanonicalLifecycleStage.QA:
            biz.pipeline_stage = "QA"
            if customer:
                customer.onboarding_status = "QA"
            if project:
                project.status = "QA"
        elif target_stage == CanonicalLifecycleStage.DEPLOYING:
            biz.pipeline_stage = "DEPLOYING"
            if customer:
                customer.onboarding_status = "DEPLOYING"
            if project:
                project.status = "DEPLOYING"
        elif target_stage == CanonicalLifecycleStage.LIVE:
            biz.pipeline_stage = PipelineStage.COMPLETED.value
            if customer:
                customer.onboarding_status = "LIVE"
            if project:
                project.status = "READY"
        elif target_stage == CanonicalLifecycleStage.RETAINED:
            biz.pipeline_stage = "RETAINED"
            if customer:
                customer.onboarding_status = "RETAINED"
        elif target_stage == CanonicalLifecycleStage.NEGATIVE:
            biz.pipeline_stage = PipelineStage.LOST.value
        elif target_stage == CanonicalLifecycleStage.UNSUBSCRIBED:
            biz.pipeline_stage = "UNSUBSCRIBED"
        elif target_stage == CanonicalLifecycleStage.DO_NOT_CONTACT:
            biz.pipeline_stage = PipelineStage.DEAD.value
        elif target_stage == CanonicalLifecycleStage.WAITING_FOR_CUSTOMER:
            biz.pipeline_stage = "WAITING_FOR_CUSTOMER"
        elif target_stage == CanonicalLifecycleStage.WAITING_FOR_EXTERNAL_PROVIDER:
            biz.pipeline_stage = "WAITING_FOR_EXTERNAL_PROVIDER"
        elif target_stage == CanonicalLifecycleStage.PAYMENT_FAILED:
            biz.pipeline_stage = "PAYMENT_FAILED"
        elif target_stage == CanonicalLifecycleStage.DELIVERY_BLOCKED:
            biz.pipeline_stage = "DELIVERY_BLOCKED"
        elif target_stage == CanonicalLifecycleStage.SUPPORT_INCIDENT:
            biz.pipeline_stage = "SUPPORT_INCIDENT"
        elif target_stage == CanonicalLifecycleStage.ESCALATED:
            biz.pipeline_stage = "ESCALATED"
        elif target_stage == CanonicalLifecycleStage.CANCELLED:
            biz.pipeline_stage = "CANCELLED"

        # Record standard PipelineEvent for audit trail
        event = PipelineEvent(
            business_id=business_id,
            from_stage=current_canonical.value,
            to_stage=target_stage.value,
            deal_value=float(metadata.get("deal_value", 0.0)) if metadata else 0.0,
            note=f"[{actor}] {reason}"
        )
        session.add(event)
        await session.flush()

        # Emit to Unified Event Bus
        from app.core.event_bus import event_bus, AgencyEvent
        await event_bus.publish(AgencyEvent(
            event_type="LIFECYCLE_TRANSITION",
            entity_type="business",
            entity_id=business_id,
            actor=actor,
            idempotency_key=idempotency_key,
            payload={
                "from_stage": current_canonical.value,
                "to_stage": target_stage.value,
                "reason": reason,
                "metadata": metadata or {}
            }
        ))

        audit = CanonicalTransitionAudit(
            business_id=business_id,
            customer_id=customer.id if customer else None,
            from_stage=current_canonical,
            to_stage=target_stage,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            metadata=metadata or {}
        )
        logger.info(f"[CanonicalLifecycle] #{business_id} transitioned: {current_canonical.value} -> {target_stage.value} ({actor}): {reason}")
        return audit


# Global Singleton
canonical_lifecycle_manager = CanonicalLifecycleManager()
