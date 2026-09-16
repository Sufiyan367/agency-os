"""
Agency OS — Operator Feedback Learning & Commercial Gate Enforcement.
Tracks operator overrides, traces upstream recommendations to downstream revenue,
and strictly enforces the commercial advance payment gate before production builds.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.models import (
    OperatorFeedbackLog, OutcomeTrace, Payment
)


class CommercialGateViolation(Exception):
    """
    Raised when an attempt is made to initiate a production build
    without verified advance or full payment.
    """
    pass


class OperatorLearningEngine:
    """
    Manages operator feedback loops, outcome attribution, and commercial gate enforcement.
    """

    @classmethod
    async def record_feedback(
        cls,
        session: AsyncSession,
        entity_type: str,
        entity_id: str,
        stage: str,
        system_recommendation: Dict[str, Any],
        operator_decision: str,
        operator_reason: Optional[str] = None
    ) -> OperatorFeedbackLog:
        """
        Records human operator decision on an automated system recommendation.
        Decisions: APPROVED, REJECTED, MODIFIED, OVERRIDDEN.
        """
        log = OperatorFeedbackLog(
            entity_type=entity_type,
            entity_id=str(entity_id),
            stage=stage,
            system_recommendation=system_recommendation,
            operator_decision=operator_decision,
            operator_reason=operator_reason,
            created_at=datetime.utcnow()
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log

    @classmethod
    async def trace_commercial_outcome(
        cls,
        session: AsyncSession,
        business_id: int,
        lead_source: str,
        initial_service_recommended: str,
        demo_project_id: Optional[str] = None,
        proposal_id: Optional[int] = None,
        proposal_amount: float = 0.0,
        advance_paid: bool = False,
        advance_amount: float = 0.0,
        won: bool = False,
        downstream_revenue: float = 0.0
    ) -> OutcomeTrace:
        """
        Records or updates an end-to-end outcome trace connecting research to revenue.
        """
        stmt = select(OutcomeTrace).where(OutcomeTrace.business_id == business_id)
        trace = (await session.execute(stmt)).scalars().first()

        if not trace:
            trace = OutcomeTrace(
                business_id=business_id,
                lead_source=lead_source,
                initial_service_recommended=initial_service_recommended,
                demo_project_id=demo_project_id,
                proposal_id=proposal_id,
                proposal_amount=proposal_amount,
                advance_paid=advance_paid,
                advance_amount=advance_amount,
                won=won,
                downstream_revenue=downstream_revenue,
                feedback_loop_incorporated=True,
                created_at=datetime.utcnow()
            )
            session.add(trace)
        else:
            trace.demo_project_id = demo_project_id or trace.demo_project_id
            trace.proposal_id = proposal_id or trace.proposal_id
            trace.proposal_amount = max(trace.proposal_amount, proposal_amount)
            trace.advance_paid = advance_paid or trace.advance_paid
            trace.advance_amount = max(trace.advance_amount, advance_amount)
            trace.won = won or trace.won
            trace.downstream_revenue = max(trace.downstream_revenue, downstream_revenue)
            trace.feedback_loop_incorporated = True

        await session.commit()
        await session.refresh(trace)
        return trace

    @classmethod
    async def enforce_commercial_gate(
        cls,
        session: AsyncSession,
        business_id: int
    ) -> bool:
        """
        Strict Commercial Gate Enforcement:
        DEMO READY -> CUSTOMER APPROVES -> PROPOSAL -> ADVANCE PAYMENT -> PRODUCTION BUILD
        Raises CommercialGateViolation if advance or full payment is not verified.
        Enforces minimum floor and 40% advance milestone.
        """
        from app.database.models import Proposal

        # Check active proposal for required advance and minimum contract floor
        prop_stmt = select(Proposal).where(
            Proposal.business_id == business_id,
            Proposal.status != "CANCELLED"
        ).order_by(Proposal.id.desc())
        proposal = (await session.execute(prop_stmt)).scalars().first()

        required_advance = 200.0  # Floor: 40% of $500 minimum service value
        if proposal:
            proposal_total = float(getattr(proposal, "total_value", getattr(proposal, "total_price_usd", 500.0)) or 500.0)
            adv_attr = getattr(proposal, "advance_required", getattr(proposal, "advance_amount", None))
            required_advance = float(adv_attr if adv_attr is not None else (proposal_total * 0.40))

        # Valid confirmed payment statuses across manual confirmation, webhooks, and CEO verifier
        confirmed_statuses = ["PAYMENT_CONFIRMED", "VERIFIED_PAYMENT", "COMPLETED", "PAID", "SETTLED"]

        stmt = select(Payment).where(
            Payment.business_id == business_id,
            Payment.status.in_(confirmed_statuses),
            Payment.payment_type.in_(["ADVANCE", "FULL_PAYMENT", "ADVANCE_DEPOSIT", "MILESTONE"])
        )
        verified_payments = (await session.execute(stmt)).scalars().all()

        total_paid = sum(float(p.amount) for p in verified_payments if p.amount is not None)

        if not verified_payments or total_paid < required_advance or total_paid <= 0.0:
            raise CommercialGateViolation(
                f"Commercial Gate Enforced: Production build is BLOCKED for Business #{business_id}. "
                f"Required advance payment of ${required_advance:,.2f} USD has not been received and verified. "
                f"Current verified payment: ${total_paid:,.2f} USD. "
                f"Required sequence: DEMO READY -> CUSTOMER APPROVES -> PROPOSAL -> ADVANCE PAYMENT -> PRODUCTION BUILD."
            )

        return True


operator_learning_engine = OperatorLearningEngine()
