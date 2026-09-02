from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.models import (
    Business, PipelineStage, PipelineEvent, Customer, Project, Offer, Payment
)
from app.core.logging import logger

VALID_TRANSITIONS = {
    PipelineStage.DISCOVERED.value: [PipelineStage.VERIFIED.value, PipelineStage.LOST.value],
    PipelineStage.VERIFIED.value: [PipelineStage.AUDITED.value, PipelineStage.LOST.value],
    PipelineStage.AUDITED.value: [PipelineStage.QUALIFIED.value, PipelineStage.LOST.value],
    PipelineStage.QUALIFIED.value: [PipelineStage.OUTREACH_READY.value, PipelineStage.APPROVAL.value, PipelineStage.LOST.value],
    PipelineStage.OUTREACH_READY.value: [PipelineStage.APPROVAL.value, PipelineStage.LOST.value],
    PipelineStage.APPROVAL.value: [PipelineStage.CONTACTED.value, PipelineStage.LOST.value],
    PipelineStage.CONTACTED.value: [PipelineStage.REPLIED.value, PipelineStage.QUALIFIED_REPLY.value, PipelineStage.LOST.value],
    PipelineStage.REPLIED.value: [PipelineStage.QUALIFIED_REPLY.value, PipelineStage.CALL.value, PipelineStage.LOST.value],
    PipelineStage.QUALIFIED_REPLY.value: [PipelineStage.CALL.value, PipelineStage.PROPOSAL.value, PipelineStage.LOST.value],
    PipelineStage.CALL.value: [PipelineStage.PROPOSAL.value, PipelineStage.WON.value, PipelineStage.LOST.value],
    PipelineStage.PROPOSAL.value: [PipelineStage.WON.value, PipelineStage.LOST.value],
    PipelineStage.WON.value: [],
    PipelineStage.LOST.value: [PipelineStage.DISCOVERED.value]  # allows reactivation
}

class PipelineManager:
    """
    Manages CRM pipeline stages, state transitions, opportunity tracking,
    and automated customer conversion upon winning deals.
    """

    async def transition_stage(
        self,
        session: AsyncSession,
        business_id: int,
        target_stage: PipelineStage,
        note: str = "",
        deal_value: float = 0.0
    ) -> Business:
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business {business_id} not found.")

        old_stage = biz.pipeline_stage
        biz.pipeline_stage = target_stage.value

        # If deal value is not provided, look up generated offer recommended price
        if deal_value <= 0.0:
            offer_q = select(Offer).where(Offer.business_id == business_id)
            offer = (await session.execute(offer_q)).scalars().first()
            if offer:
                deal_value = offer.recommended_price

        event = PipelineEvent(
            business_id=biz.id,
            from_stage=old_stage,
            to_stage=target_stage.value,
            deal_value=deal_value,
            note=note or f"Stage updated from {old_stage} to {target_stage.value}."
        )
        session.add(event)

        # Handle Deal WON logic: Automatically initialize Customer & Project
        if target_stage == PipelineStage.WON:
            await self._handle_deal_won(session, biz, deal_value)

        await session.commit()
        logger.info(f"Pipeline: {biz.name} moved from {old_stage} -> {target_stage.value} (${deal_value:,.0f})")
        return biz

    async def _handle_deal_won(self, session: AsyncSession, business: Business, amount: float):
        """Provisions Customer record, delivery Project, and simulated payment confirmation."""
        cust_q = select(Customer).where(Customer.business_id == business.id)
        cust = (await session.execute(cust_q)).scalar_one_or_none()
        
        offer_q = select(Offer).where(Offer.business_id == business.id)
        offer = (await session.execute(offer_q)).scalars().first()
        svc_title = offer.title if offer else "Website Turnaround & Optimization"
        deliverables = offer.deliverables if offer else ["Technical audit remediation"]

        if not cust:
            cust = Customer(
                business_id=business.id,
                company_name=business.name,
                contact_email=business.public_email or f"billing@{business.domain}",
                contract_amount=amount,
                onboarding_status="ONBOARDING_ACTIVE"
            )
            session.add(cust)
            await session.flush()

            # Create Delivery Project
            proj = Project(
                customer_id=cust.id,
                title=f"Delivery: {svc_title}",
                service_type=offer.service_type if offer else "Website Optimization",
                status="IN_PROGRESS",
                tasks=[{"task": d, "status": "PENDING", "assigned_to": "Delivery Agent"} for d in deliverables],
                qa_checklist={
                    "staging_verified": False,
                    "production_deployed": False,
                    "client_walkthrough_scheduled": False
                }
            )
            session.add(proj)

            # Record Payment confirmation
            pmt = Payment(
                customer_id=cust.id,
                amount=amount,
                currency="USD",
                status="COMPLETED",
                reference_id=f"INV-{business.id}-{datetime.utcnow().strftime('%Y%m%d')}"
            )
            session.add(pmt)

    async def get_pipeline_summary(self, session: AsyncSession) -> Dict[str, Any]:
        """Calculates stage breakdown, pipeline value, won revenue, and total volume."""
        q = select(Business.pipeline_stage, func.count(Business.id)).group_by(Business.pipeline_stage)
        counts = dict((await session.execute(q)).all())

        # Calculate pipeline total value & won revenue
        won_q = select(func.sum(Customer.contract_amount))
        won_revenue = (await session.execute(won_q)).scalar() or 0.0

        all_stages = [s.value for s in PipelineStage]
        stage_breakdown = {stage: counts.get(stage, 0) for stage in all_stages}

        return {
            "stage_breakdown": stage_breakdown,
            "total_leads": sum(counts.values()),
            "won_revenue": won_revenue,
            "active_pipeline_count": sum(counts.get(s, 0) for s in [
                PipelineStage.QUALIFIED.value,
                PipelineStage.OUTREACH_READY.value,
                PipelineStage.APPROVAL.value,
                PipelineStage.CONTACTED.value,
                PipelineStage.REPLIED.value,
                PipelineStage.QUALIFIED_REPLY.value,
                PipelineStage.CALL.value,
                PipelineStage.PROPOSAL.value
            ])
        }

pipeline_manager = PipelineManager()
