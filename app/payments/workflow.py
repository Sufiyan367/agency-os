"""Payment Workflow Coordinator & Anti-Fraud Verification Gate.

Enforces:
- Google Pay first preference.
- Strict anti-fraud: Rejection of screenshot-only, text-only, and AI-inferred payment claims.
- Duplicate transaction reference rejection (replay protection).
- Underpayment rejection.
- Production delivery unlock boundary: Only VERIFIED_PAYMENT triggers production project creation.
"""
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    Business, Customer, Payment, ProjectProposal, CustomerProject,
    PipelineEvent, CommercialProposalStatus
)
from app.payments.abstraction import get_payment_provider
from app.production.pipeline import ProductionPipeline
from app.core.config import settings
from app.core.logging import logger


class PaymentWorkflowCoordinator:
    """Coordinates customer payment requests and trusted verification."""

    @classmethod
    async def issue_proposal_payment_instructions(
        cls,
        session: AsyncSession,
        proposal_id: int,
        provider_name: Optional[str] = None
    ) -> Dict[str, Any]:
        prop = await session.get(ProjectProposal, proposal_id)
        if not prop:
            raise ValueError(f"Proposal #{proposal_id} not found.")

        biz = await session.get(Business, prop.business_id)
        if not biz:
            raise ValueError(f"Business #{prop.business_id} not found.")

        effective_provider = (provider_name or getattr(settings, "PREFERRED_PAYMENT_METHOD", "google_pay")).lower()
        provider = get_payment_provider(effective_provider)

        deposit_amount = float(prop.advance_deposit_usd or 400.0)
        floor = float(getattr(settings, "COMMERCIAL_FLOOR_USD", 500.0))
        # Advance deposit can be a fraction of total price >= $500, but let's ensure valid range
        if prop.total_price_usd < floor:
            raise ValueError(f"Total price ${prop.total_price_usd:,.2f} is below $500 commercial floor.")

        # Ensure Customer record exists
        c_stmt = select(Customer).where(Customer.business_id == biz.id)
        customer = (await session.execute(c_stmt)).scalar_one_or_none()
        if not customer:
            customer = Customer(
                business_id=biz.id,
                company_name=biz.name,
                contact_email=biz.public_email or f"billing@{biz.domain or 'prospect.com'}",
                contract_amount=float(prop.total_price_usd),
                onboarding_status="PENDING_PAYMENT"
            )
            session.add(customer)
            await session.flush()

        instructions = await provider.generate_payment_instructions(
            deal_id=prop.id,
            proposal_id=prop.id,
            amount_usd=deposit_amount,
            currency="USD",
            payment_type="ADVANCE_DEPOSIT",
            customer_name=biz.name,
            customer_email=customer.contact_email
        )

        ref_id = instructions.get("order_id") or instructions.get("reference_id") or f"pay_adv_{prop.id}_{int(datetime.utcnow().timestamp())}"

        # Create or update Payment record
        payment = Payment(
            customer_id=customer.id,
            business_id=biz.id,
            proposal_id=prop.id,
            amount=deposit_amount,
            currency="USD",
            payment_type="ADVANCE_DEPOSIT",
            status="PAYMENT_PENDING",
            reference_id=ref_id,
            provider=provider.provider_name,
            is_mock=(provider.provider_name in ("mock_payment_provider", "dry_run")),
            instructions_sent_at=datetime.utcnow(),
            extra_metadata={
                "proposal_ref": prop.proposal_id,
                "project_id": prop.project_id,
                "instructions": instructions,
                "total_contract_value": prop.total_price_usd,
                "advance_percentage": 40
            }
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)

        logger.info(f"[PaymentWorkflowCoordinator] Issued payment instructions for proposal {prop.proposal_id}: ${deposit_amount:,.2f} via {provider.provider_name}.")
        return {
            "payment_id": payment.id,
            "reference_id": payment.reference_id,
            "provider": payment.provider,
            "amount_usd": payment.amount,
            "currency": payment.currency,
            "instructions": instructions,
            "status": payment.status
        }

    @classmethod
    async def verify_payment(
        cls,
        session: AsyncSession,
        payment_id: int,
        verified_by: str,
        transaction_reference: str,
        amount_received: float,
        source: str = "CEO_VERIFICATION",
        evidence: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Strict payment verification gate. Enforces trusted evidence and anti-fraud."""
        untrusted = ("customer_message", "screenshot", "ai_inference", "manual_claim", "unverified")
        if (source or "").lower().strip() in untrusted:
            raise PermissionError(
                f"Payment confirmation rejected: Source '{source}' is untrusted. "
                f"Delivery CANNOT be unlocked from customer message, screenshot, AI inference, or unverified claims. "
                f"Trusted CEO approval or verified bank reconciliation required."
            )

        if not transaction_reference or len(transaction_reference.strip()) < 3:
            raise ValueError("Invalid or missing transaction reference. Legitimate verification requires bank reference / UTR.")

        # Replay protection: Check for duplicate transaction reference across already verified payments
        dup_stmt = select(Payment).where(
            Payment.id != payment_id,
            Payment.status == "VERIFIED_PAYMENT",
            Payment.extra_metadata["transaction_reference"].as_string() == transaction_reference.strip()
        )
        existing_dup = (await session.execute(dup_stmt)).scalars().first()
        if existing_dup:
            raise ValueError(f"Fraud detected: Transaction reference '{transaction_reference}' has already been verified for payment #{existing_dup.id}.")

        payment = await session.get(Payment, payment_id)
        if not payment:
            raise ValueError(f"Payment #{payment_id} not found.")

        if amount_received < float(payment.amount):
            raise ValueError(f"Underpayment rejected: Received ${amount_received:,.2f} but expected ${payment.amount:,.2f}.")

        # Update payment record
        payment.status = "VERIFIED_PAYMENT"
        payment.paid_at = datetime.utcnow()
        payment.verification_method = source
        payment.verified_by = verified_by
        meta = dict(payment.extra_metadata or {})
        meta["transaction_reference"] = transaction_reference.strip()
        meta["verified_at"] = datetime.utcnow().isoformat()
        meta["evidence"] = evidence or {
            "source": source,
            "verified_by": verified_by,
            "amount_received": amount_received,
            "transaction_reference": transaction_reference.strip()
        }
        payment.extra_metadata = meta

        # Update linked proposal
        prop_id = payment.proposal_id or meta.get("proposal_id")
        prop = None
        project_id = meta.get("project_id")
        if prop_id:
            prop = await session.get(ProjectProposal, prop_id)
            if prop:
                prop.status = CommercialProposalStatus.PROPOSAL_ACCEPTED.value
                prop.accepted_at = datetime.utcnow()
                project_id = project_id or prop.project_id

        # Update customer status
        if payment.customer_id:
            cust = await session.get(Customer, payment.customer_id)
            if cust:
                cust.onboarding_status = "PAYMENT_VERIFIED"

        await session.flush()

        # Hard payment boundary: Unlock production project creation
        prod_project = None
        if project_id:
            prod_project = await ProductionPipeline.initialize_production_project(
                session=session,
                project_id=project_id,
                payment_id=payment.id,
                proposal_id=prop.id if prop else None
            )

        await session.commit()
        await session.refresh(payment)

        logger.info(f"[PaymentWorkflowCoordinator] Payment #{payment.id} VERIFIED by {verified_by}. Production project #{prod_project.id if prod_project else None} initialized.")
        return {
            "payment_id": payment.id,
            "status": "VERIFIED_PAYMENT",
            "amount_received": amount_received,
            "transaction_reference": transaction_reference.strip(),
            "production_project_id": prod_project.id if prod_project else None,
            "delivery_unlocked": True
        }
