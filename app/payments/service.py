from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    Business, Customer, Project, Payment, Offer, PipelineStage, PipelineEvent
)
from app.delivery.onboarding import onboarding_automation
from app.delivery.report_generator import delivery_report_generator
from app.core.config import settings
from app.core.logging import logger

class PaymentService:
    """
    Coordinates payment confirmation, idempotent event handling,
    CRM pipeline advancement to WON, and automated customer onboarding.
    """

    async def confirm_payment_and_onboard(
        self,
        session: AsyncSession,
        business_id: int,
        amount_usd: float,
        reference_id: str,
        payer_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end post-payment workflow:
        1. Checks payment idempotency.
        2. Advances business to WON.
        3. Provisions Customer & Project records.
        4. Generates full onboarding packet & diagnostic delivery report.
        """
        # 1. Idempotency check: Don't double process duplicate payment events
        q_pmt = select(Payment).where(Payment.reference_id == reference_id)
        existing_pmt = (await session.execute(q_pmt)).scalars().first()
        if existing_pmt:
            logger.warning(f"[PaymentService] Duplicate payment event detected for ref '{reference_id}'. Returning existing.")
            cust = await session.get(Customer, existing_pmt.customer_id)
            return {
                "status": "ALREADY_PROCESSED",
                "payment_id": existing_pmt.id,
                "customer_id": cust.id if cust else None,
                "company_name": cust.company_name if cust else "Client"
            }

        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business ID {business_id} not found.")

        # 2. Lookup offer deliverables & package details
        q_offer = select(Offer).where(Offer.business_id == business_id).order_by(Offer.created_at.desc())
        offer = (await session.execute(q_offer)).scalars().first()
        svc_title = offer.title if offer else "Website Turnaround & Optimization"
        deliverables = offer.deliverables if offer else ["Core Web Vitals remediation", "Mobile conversion overhaul", "Schema injection"]

        # 3. Transition business pipeline stage to WON
        old_stage = biz.pipeline_stage
        biz.pipeline_stage = PipelineStage.WON.value

        event = PipelineEvent(
            business_id=biz.id,
            from_stage=old_stage,
            to_stage=PipelineStage.WON.value,
            deal_value=amount_usd,
            note=f"Payment confirmed ({reference_id}): ${amount_usd:,.2f} USD. Deal won."
        )
        session.add(event)

        # Sync ProspectMemory
        from app.database.models import ProspectMemory
        q_mem = select(ProspectMemory).where(ProspectMemory.business_id == biz.id)
        mem = (await session.execute(q_mem)).scalars().first()
        if mem:
            mem.pipeline_stage = PipelineStage.WON.value
            mem.last_interaction = f"Payment confirmed ({reference_id}): ${amount_usd:,.2f} USD. Deal won."
            mem.next_expected_action = "DELIVERY_IN_PROGRESS"
            mem.updated_at = datetime.utcnow()

        # 4. Provision Customer
        q_cust = select(Customer).where(Customer.business_id == business_id)
        cust = (await session.execute(q_cust)).scalars().first()
        if not cust:
            cust = Customer(
                business_id=biz.id,
                company_name=biz.name,
                contact_email=payer_email or biz.public_email or f"contact@{biz.domain}",
                contract_amount=amount_usd,
                onboarding_status="ONBOARDING_INITIALIZED"
            )
            session.add(cust)
            await session.flush()
        else:
            cust.contract_amount += amount_usd

        # 5. Provision Project
        proj = Project(
            customer_id=cust.id,
            title=f"Remediation Project: {svc_title}",
            service_type=offer.service_type if offer else "Website Optimization",
            status="IN_PROGRESS",
            tasks=[{"task": d, "status": "PENDING", "assigned_to": "Digital Agency Tech Lead"} for d in deliverables],
            qa_checklist={
                "staging_verified": False,
                "production_deployed": False,
                "client_walkthrough_scheduled": False
            }
        )
        session.add(proj)

        # 6. Record Payment record
        pmt = Payment(
            customer_id=cust.id,
            amount=amount_usd,
            currency="USD",
            status="COMPLETED",
            reference_id=reference_id
        )
        session.add(pmt)
        await session.commit()

        # 7. Generate Onboarding Packet & Client Diagnostic Audit Report
        onboarding_packet = await onboarding_automation.generate_onboarding_packet(session, cust.id)
        audit_report_len = 0
        try:
            audit_report_md = await delivery_report_generator.generate_audit_report_markdown(session, biz.id)
            audit_report_len = len(audit_report_md)
        except Exception as e:
            logger.info(f"[PaymentService] Diagnostic report skipped (audit not yet recorded): {e}")

        logger.info(f"[PaymentService] Successfully onboarded customer '{cust.company_name}' (${amount_usd:,.2f}). Project created with {len(deliverables)} tasks.")

        return {
            "status": "SUCCESS",
            "business_id": biz.id,
            "customer_id": cust.id,
            "project_id": proj.id,
            "payment_id": pmt.id,
            "amount_paid": amount_usd,
            "reference_id": reference_id,
            "onboarding_packet": onboarding_packet,
            "audit_report_length": audit_report_len
        }

payment_service = PaymentService()
