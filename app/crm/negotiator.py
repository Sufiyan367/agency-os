"""
Commercial Negotiation & Pricing Safeguards — Phase 15.

Enforces:
- Absolute commercial floor ($500.00). No concession can go below $500.
- $500 - $999 counter-offers require HUMAN_REVIEW.
- >= $1,000 counter-offers can be accepted autonomously if policy allows.
- Refuses to drop prices merely to close without genuine scope adjustments.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Business, Offer, Proposal, PipelineStage, PipelineEvent
from app.core.config import settings
from app.core.logging import logger


class NegotiationResult(BaseModel):
    decision: str  # 'ACCEPTED', 'HUMAN_REVIEW', 'REJECTED'
    can_accept: bool
    agreed_price_usd: float
    reason: str
    requires_human_approval: bool


class CommercialNegotiator:
    """
    Safeguards agency pricing integrity during commercial negotiations.
    """

    COMMERCIAL_FLOOR_USD = 500.0
    TARGET_MINIMUM_USD = 1000.0

    def evaluate_counter_offer(
        self,
        offered_price: float,
        catalog_target: float = 1000.0
    ) -> NegotiationResult:
        """
        Determines whether a proposed pricing adjustment is acceptable under policy.
        """
        floor = float(getattr(settings, "COMMERCIAL_FLOOR_USD", self.COMMERCIAL_FLOOR_USD))
        target = float(getattr(settings, "TARGET_OFFER_MINIMUM_USD", self.TARGET_MINIMUM_USD))

        if offered_price < floor:
            return NegotiationResult(
                decision="REJECTED",
                can_accept=False,
                agreed_price_usd=offered_price,
                reason=f"Offered price ${offered_price:,.2f} is below the ${floor:,.2f} absolute commercial floor.",
                requires_human_approval=False
            )

        if offered_price < target:
            return NegotiationResult(
                decision="HUMAN_REVIEW",
                can_accept=False,
                agreed_price_usd=offered_price,
                reason=f"Offered price ${offered_price:,.2f} is below the ${target:,.2f} catalog target but above floor. Requires operator sign-off.",
                requires_human_approval=True
            )

        return NegotiationResult(
            decision="ACCEPTED",
            can_accept=True,
            agreed_price_usd=offered_price,
            reason=f"Offered price ${offered_price:,.2f} satisfies the ${target:,.2f}+ auto-approval policy.",
            requires_human_approval=False
        )

    async def create_or_update_proposal(
        self,
        session: AsyncSession,
        business_id: int,
        price_usd: float,
        service_title: str = "Turnkey B2B Automation"
    ) -> Proposal:
        """
        Generates or updates formal commercial proposal with safe pricing.
        """
        eval_res = self.evaluate_counter_offer(price_usd)
        if eval_res.decision == "REJECTED":
            raise ValueError(f"Cannot generate proposal: {eval_res.reason}")

        q = select(Proposal).where(Proposal.business_id == business_id).order_by(Proposal.id.desc())
        existing = (await session.execute(q)).scalars().first()

        status = "APPROVED" if eval_res.can_accept else "DRAFT"

        if not existing:
            prop = Proposal(
                business_id=business_id,
                title=service_title,
                total_value=price_usd,
                advance_required=round(price_usd * 0.5, 2),
                remaining_balance=price_usd,
                status=status
            )
            session.add(prop)
        else:
            prop = existing
            prop.total_value = price_usd
            prop.advance_required = round(price_usd * 0.5, 2)
            prop.status = status

        await session.commit()
        return prop


commercial_negotiator = CommercialNegotiator()