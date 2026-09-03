import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.database.models import (
    Business, Customer, Project, Payment, Proposal, Deal, DealAuditTrail,
    PipelineStage, PipelineEvent
)
from app.payments.abstraction import get_payment_provider, BasePaymentProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

class DealClosingService:
    """
    Manages the commercial lifecycle from proposal draft to payment verification,
    advance deposit tracking, delivery activation, and deal won.
    Enforces mandatory operator approval gates and cryptographic webhook verification.
    """

    def __init__(self, payment_provider: Optional[BasePaymentProvider] = None):
        self._provider = payment_provider

    @property
    def provider(self) -> BasePaymentProvider:
        return self._provider or get_payment_provider()

    async def create_proposal(
        self,
        session: AsyncSession,
        business_id: int,
        title: str,
        total_value: float,
        advance_required: float,
        service_type: str = "Website Turnaround & Automation",
        lead_id: Optional[int] = None,
        is_mock: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Proposal:
        """
        Creates a commercial proposal in DRAFT state.
        Enforces the configurable $500+ commercial minimum service threshold (settings.MINIMUM_SERVICE_VALUE_USD).
        """
        min_threshold = settings.MINIMUM_SERVICE_VALUE_USD
        if total_value < min_threshold:
            raise ValueError(
                f"Proposal total value (${total_value:,.2f}) does not meet the "
                f"${min_threshold:,.2f}+ commercial qualification requirement."
            )

        if advance_required > total_value or advance_required <= 0:
            raise ValueError(
                f"Required advance (${advance_required:,.2f}) must be positive and cannot exceed total value (${total_value:,.2f})."
            )

        mock_flag = is_mock if is_mock is not None else (settings.PAYMENT_DRY_RUN or settings.DRY_RUN)

        proposal = Proposal(
            business_id=business_id,
            lead_id=lead_id,
            title=title,
            service_type=service_type,
            total_value=total_value,
            advance_required=advance_required,
            advance_received=0.0,
            remaining_balance=total_value,
            status="DRAFT",
            delivery_status="NOT_STARTED",
            is_mock=mock_flag,
            extra_metadata=metadata or {}
        )
        session.add(proposal)
        await session.flush()

        # Audit Event: Proposal Created
        audit = DealAuditTrail(
            proposal_id=proposal.id,
            business_id=business_id,
            event_type="proposal_created",
            operator="system",
            payload={
                "title": title,
                "total_value": total_value,
                "advance_required": advance_required,
                "service_type": service_type,
                "is_mock": mock_flag
            }
        )
        session.add(audit)
        await session.commit()
        await session.refresh(proposal)

        logger.info(f"[DealClosingService] Created proposal #{proposal.id} for business #{business_id} (${total_value:,.2f})")
        return proposal

    async def approve_proposal(
        self,
        session: AsyncSession,
        proposal_id: int,
        operator: str = "operator"
    ) -> Proposal:
        """
        Mandatory operator approval gate.
        Transitions DRAFT -> APPROVED.
        """
        proposal = await session.get(Proposal, proposal_id)
        if not proposal:
            raise ValueError(f"Proposal #{proposal_id} not found.")

        if proposal.status != "DRAFT":
            raise ValueError(f"Cannot approve proposal #{proposal_id} in '{proposal.status}' state; must be 'DRAFT'.")

        proposal.status = "APPROVED"
        proposal.approved_by = operator
        proposal.approved_at = datetime.utcnow()

        audit = DealAuditTrail(
            proposal_id=proposal.id,
            business_id=proposal.business_id,
            event_type="proposal_approved",
            operator=operator,
            payload={
                "approved_by": operator,
                "approved_at": proposal.approved_at.isoformat(),
                "total_value": proposal.total_value,
                "advance_required": proposal.advance_required
            }
        )
        session.add(audit)
        await session.commit()
        await session.refresh(proposal)

        logger.info(f"[DealClosingService] Operator '{operator}' approved proposal #{proposal.id}")
        return proposal

    async def request_payment_order(
        self,
        session: AsyncSession,
        proposal_id: int,
        payment_type: str = "ADVANCE",
        operator: str = "operator"
    ) -> Dict[str, Any]:
        """
        Generates a gateway payment order for an approved proposal.
        Human approval is strictly verified before proceeding.
        """
        proposal = await session.get(Proposal, proposal_id)
        if not proposal:
            raise ValueError(f"Proposal #{proposal_id} not found.")

        if proposal.status not in ("APPROVED", "PAYMENT_REQUESTED", "ADVANCE_RECEIVED"):
            raise ValueError(
                f"Cannot request payment for proposal #{proposal_id} in '{proposal.status}' state. "
                "Human operator approval is required."
            )

        biz = await session.get(Business, proposal.business_id)
        biz_name = biz.name if biz else f"Business #{proposal.business_id}"
        biz_email = biz.public_email if biz else None

        # Determine charge amount based on payment type
        if payment_type == "ADVANCE":
            charge_amount = proposal.advance_required
        elif payment_type == "FINAL_BALANCE":
            charge_amount = proposal.remaining_balance
        else:  # FULL_PAYMENT
            charge_amount = proposal.remaining_balance

        # Ensure Customer record exists so customer_id satisfies legacy DB constraints
        q_cust = select(Customer).where(Customer.business_id == proposal.business_id)
        cust = (await session.execute(q_cust)).scalars().first()
        if not cust:
            cust = Customer(
                business_id=proposal.business_id,
                company_name=biz_name,
                contact_email=biz_email or f"billing@{biz.domain if biz else 'client.com'}",
                contract_amount=0.0,
                onboarding_status="PENDING_PAYMENT"
            )
            session.add(cust)
            await session.flush()

        # Call payment provider (Mock or Real Razorpay)
        order_res = await self.provider.create_payment_order(
            deal_id=proposal.id,
            proposal_id=proposal.id,
            amount_usd=charge_amount,
            currency="USD",
            payment_type=payment_type,
            customer_name=biz_name,
            customer_email=biz_email,
            metadata={"proposal_title": proposal.title}
        )

        order_id = order_res["order_id"]
        is_mock = order_res.get("is_mock", proposal.is_mock)

        # Transition proposal to PAYMENT_PENDING (never PAID upon creation)
        proposal.status = "PAYMENT_PENDING"
        proposal.payment_requested_at = datetime.utcnow()

        # Persist PaymentRecord
        payment = Payment(
            customer_id=cust.id,
            business_id=proposal.business_id,
            lead_id=proposal.lead_id,
            proposal_id=proposal.id,
            deal_id=proposal.id,
            amount=charge_amount,
            currency="USD",
            payment_type=payment_type,
            status="PAYMENT_PENDING",
            reference_id=order_id,
            provider=self.provider.provider_name,
            razorpay_order_id=order_id,
            is_mock=is_mock,
            extra_metadata=order_res
        )
        session.add(payment)

        # Audit Event: Payment Requested
        audit = DealAuditTrail(
            proposal_id=proposal.id,
            business_id=proposal.business_id,
            event_type="payment_requested",
            operator=operator,
            payload={
                "order_id": order_id,
                "amount": charge_amount,
                "payment_type": payment_type,
                "checkout_url": order_res.get("checkout_url"),
                "is_mock": is_mock
            }
        )
        session.add(audit)
        await session.commit()
        await session.refresh(payment)

        return {
            "status": "ORDER_CREATED",
            "order_id": order_id,
            "checkout_url": order_res.get("checkout_url"),
            "amount": charge_amount,
            "currency": "USD",
            "payment_type": payment_type,
            "proposal_status": proposal.status,
            "is_mock": is_mock
        }

    async def process_payment_webhook(
        self,
        session: AsyncSession,
        payload_bytes: bytes,
        signature: Optional[str],
        event_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cryptographically verifies and idempotently processes Razorpay payment webhook events.
        Transitions PAYMENT_PENDING -> PAID, marks ADVANCE_RECEIVED, unlocks delivery.
        """
        # 1. Cryptographic Signature Verification
        is_valid, reason = self.provider.verify_webhook_signature(payload_bytes, signature)
        if not is_valid:
            logger.error(f"[Webhook] Cryptographic verification failed: {reason}")
            raise ValueError(f"Invalid webhook signature: {reason}")

        event_name = event_dict.get("event", "payment.captured")
        payment_entity = (
            event_dict.get("payload", {})
            .get("payment", {})
            .get("entity", {})
        )
        order_id = payment_entity.get("order_id")
        payment_id = payment_entity.get("id")
        raw_amount = payment_entity.get("amount", 0)
        amount_usd = raw_amount / 100.0 if raw_amount > 1000 else float(raw_amount)

        if not order_id and not payment_id:
            logger.warning("[Webhook] Missing order_id and payment_id in webhook payload.")
            return {"status": "IGNORED", "reason": "Missing identifiers"}

        # 2. Idempotency Check: Look up payment record
        q_pmt = select(Payment).where(
            (Payment.razorpay_order_id == order_id) |
            (Payment.reference_id == order_id) |
            (Payment.razorpay_payment_id == payment_id)
        )
        pmt = (await session.execute(q_pmt)).scalars().first()

        if pmt and pmt.status == "PAID":
            logger.info(f"[Webhook] Payment order '{order_id}' already processed as PAID. Skipping duplicate.")
            return {
                "status": "ALREADY_PROCESSED",
                "order_id": order_id,
                "payment_id": payment_id,
                "amount": pmt.amount
            }

        # 3. Handle Payment Failure
        if event_name in ("payment.failed", "order.failed"):
            if pmt:
                pmt.status = "FAILED"
                session.add(DealAuditTrail(
                    proposal_id=pmt.proposal_id,
                    business_id=pmt.business_id,
                    event_type="payment_failed",
                    payload={"order_id": order_id, "payment_id": payment_id, "amount": amount_usd}
                ))
                await session.commit()
            return {"status": "PAYMENT_FAILED", "order_id": order_id}

        # 4. Handle Successful Payment
        if pmt:
            pmt.status = "PAID"
            pmt.paid_at = datetime.utcnow()
            pmt.razorpay_payment_id = payment_id
            pmt.razorpay_signature = signature
        else:
            # Create payment record if order was generated externally
            pmt = Payment(
                amount=amount_usd,
                currency=payment_entity.get("currency", "USD"),
                payment_type="ADVANCE",
                status="PAID",
                reference_id=order_id or payment_id,
                provider=self.provider.provider_name,
                razorpay_order_id=order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=signature,
                paid_at=datetime.utcnow()
            )
            session.add(pmt)
            await session.flush()

        # 5. Advance Proposal & Financials
        proposal = None
        if pmt.proposal_id:
            proposal = await session.get(Proposal, pmt.proposal_id)

        if proposal:
            proposal.advance_received += pmt.amount
            proposal.remaining_balance = max(0.0, proposal.total_value - proposal.advance_received)

            # Check if fully paid or partial advance
            if proposal.remaining_balance <= 0.0:
                proposal.status = "WON"
                proposal.delivery_status = "READY_TO_START"
                audit_event = "deal_won"
            else:
                proposal.status = "ADVANCE_RECEIVED"
                proposal.delivery_status = "READY_TO_START"
                audit_event = "advance_received"

            # Record Audit Events
            session.add(DealAuditTrail(
                proposal_id=proposal.id,
                business_id=proposal.business_id,
                event_type="payment_succeeded",
                payload={"payment_id": payment_id, "amount": pmt.amount, "currency": pmt.currency}
            ))
            session.add(DealAuditTrail(
                proposal_id=proposal.id,
                business_id=proposal.business_id,
                event_type=audit_event,
                payload={
                    "advance_received": proposal.advance_received,
                    "remaining_balance": proposal.remaining_balance,
                    "total_value": proposal.total_value
                }
            ))
            session.add(DealAuditTrail(
                proposal_id=proposal.id,
                business_id=proposal.business_id,
                event_type="delivery_unlocked",
                payload={"delivery_status": proposal.delivery_status}
            ))

            # Advance CRM Business Pipeline Stage
            biz = await session.get(Business, proposal.business_id)
            if biz:
                old_stage = biz.pipeline_stage
                biz.pipeline_stage = PipelineStage.WON.value if proposal.status == "WON" else "ADVANCE_RECEIVED"
                session.add(PipelineEvent(
                    business_id=biz.id,
                    from_stage=old_stage,
                    to_stage=biz.pipeline_stage,
                    deal_value=pmt.amount,
                    note=f"Payment received ({payment_id}): ${pmt.amount:,.2f} USD. Delivery unlocked."
                ))

            # Provision Customer & Project
            q_cust = select(Customer).where(Customer.business_id == proposal.business_id)
            cust = (await session.execute(q_cust)).scalars().first()
            if not cust:
                cust = Customer(
                    business_id=proposal.business_id,
                    company_name=biz.name if biz else f"Company #{proposal.business_id}",
                    contact_email=biz.public_email if biz else "billing@example.com",
                    contract_amount=pmt.amount,
                    onboarding_status="READY_TO_START"
                )
                session.add(cust)
                await session.flush()
            else:
                cust.contract_amount += pmt.amount
                cust.onboarding_status = "READY_TO_START"

            pmt.customer_id = cust.id

            q_proj = select(Project).where(Project.customer_id == cust.id)
            proj = (await session.execute(q_proj)).scalars().first()
            if not proj:
                proj = Project(
                    customer_id=cust.id,
                    title=f"Delivery Project: {proposal.title}",
                    service_type=proposal.service_type,
                    status="IN_PROGRESS",
                    tasks=[
                        {"task": "Technical Onboarding & Asset Audit", "status": "IN_PROGRESS"},
                        {"task": "Execution & Performance Overhaul", "status": "PENDING"},
                        {"task": "Delivery Verification & Signoff", "status": "PENDING"}
                    ]
                )
                session.add(proj)

        await session.commit()

        logger.info(
            f"[DealClosingService] Successfully verified payment '{payment_id}' for order '{order_id}' "
            f"(${pmt.amount:,.2f}). Proposal status: {proposal.status if proposal else 'N/A'}"
        )

        return {
            "status": "SUCCESS",
            "payment_id": payment_id,
            "order_id": order_id,
            "amount_paid": pmt.amount,
            "proposal_status": proposal.status if proposal else "PAID",
            "remaining_balance": proposal.remaining_balance if proposal else 0.0,
            "delivery_status": proposal.delivery_status if proposal else "READY_TO_START"
        }

    async def get_real_deal_metrics(
        self,
        session: AsyncSession,
        include_mock: bool = False
    ) -> Dict[str, Any]:
        """
        Calculates verified deal metrics strictly derived from database records.
        Filters out drafts, AI estimates, and unverified mock payments from production metrics.
        """
        base_filter = [Proposal.is_mock == False] if not include_mock else []

        # 1. Proposal Counts
        q_open = select(func.count(Proposal.id)).where(Proposal.status.in_(["DRAFT", "APPROVED"]), *base_filter)
        open_proposals = (await session.execute(q_open)).scalar() or 0

        q_pending = select(func.count(Proposal.id)).where(Proposal.status.in_(["PAYMENT_PENDING", "PAYMENT_REQUESTED"]), *base_filter)
        payment_pending = (await session.execute(q_pending)).scalar() or 0

        q_advance = select(func.count(Proposal.id)).where(Proposal.status == "ADVANCE_RECEIVED", *base_filter)
        advance_received_count = (await session.execute(q_advance)).scalar() or 0

        q_won = select(func.count(Proposal.id)).where(Proposal.status == "WON", *base_filter)
        won_deals_count = (await session.execute(q_won)).scalar() or 0

        # 2. Financial Metrics
        # Cash Received: ONLY verified PAID payments
        pmt_filter = [Payment.status == "PAID"]
        if not include_mock:
            pmt_filter.append(Payment.is_mock == False)

        q_cash = select(func.sum(Payment.amount)).where(*pmt_filter)
        cash_received = (await session.execute(q_cash)).scalar() or 0.0

        # Outstanding Balance: remaining balance across active non-cancelled proposals
        q_bal = select(func.sum(Proposal.remaining_balance)).where(
            Proposal.status.in_(["APPROVED", "PAYMENT_PENDING", "ADVANCE_RECEIVED"]),
            *base_filter
        )
        outstanding_balance = (await session.execute(q_bal)).scalar() or 0.0

        # Pipeline Value: approved value not yet fully collected
        # (approved/pending total value + advance_received remaining balance)
        q_pipe_approved = select(func.sum(Proposal.total_value)).where(
            Proposal.status.in_(["APPROVED", "PAYMENT_REQUESTED", "PAYMENT_PENDING"]),
            *base_filter
        )
        pipe_approved = (await session.execute(q_pipe_approved)).scalar() or 0.0

        q_pipe_advance = select(func.sum(Proposal.remaining_balance)).where(
            Proposal.status == "ADVANCE_RECEIVED",
            *base_filter
        )
        pipe_advance = (await session.execute(q_pipe_advance)).scalar() or 0.0
        pipeline_value = pipe_approved + pipe_advance

        return {
            "open_proposals": open_proposals,
            "payment_pending": payment_pending,
            "advance_received_deals": advance_received_count,
            "won_deals": won_deals_count,
            "cash_received_usd": round(cash_received, 2),
            "outstanding_balance_usd": round(outstanding_balance, 2),
            "pipeline_value_usd": round(pipeline_value, 2)
        }

deal_closing_service = DealClosingService()
