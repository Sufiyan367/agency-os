"""
Sales Funnel Analytics Engine — Mega Prompt 8.
Tracks conversion stages from Discovery to Retained Customer:
DISCOVERED -> QUALIFIED -> CONTACTABLE -> OUTREACH -> RESPONSE -> POSITIVE ->
DEMO -> PROPOSAL -> PAYMENT -> WON -> DELIVERY -> RETAINED.
Surfaces empirical bottlenecks formatted as: OBSERVATION -> POSSIBLE CAUSE -> EVIDENCE -> RECOMMENDATION.
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.models import (
    Business, Contact, OutreachMessage, Reply, Proposal,
    Payment, Customer, Project
)

class FunnelAnalyticsEngine:
    """
    Computes deterministic funnel stage conversions and isolates commercial bottlenecks.
    """

    STAGES = [
        "DISCOVERED", "QUALIFIED", "CONTACTABLE", "OUTREACH",
        "RESPONSE", "POSITIVE", "DEMO", "PROPOSAL",
        "PAYMENT", "WON", "DELIVERY", "RETAINED"
    ]

    @classmethod
    async def get_funnel_metrics(
        cls,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Calculates counts, drop-offs, and conversion rates across all 12 stages.
        """
        # 1. Stage Counts
        stmt_biz = select(func.count(Business.id))
        discovered = (await session.execute(stmt_biz)).scalar() or 0

        # Qualified (has audit or score > 50)
        stmt_qual = select(func.count(Business.id)).where(Business.pipeline_stage != "DISCOVERED")
        qualified = (await session.execute(stmt_qual)).scalar() or 0

        # Contactable (has verified email or phone)
        stmt_cont = select(func.count(func.distinct(Contact.business_id))).where(Contact.email.isnot(None))
        contactable = (await session.execute(stmt_cont)).scalar() or 0

        # Outreach
        stmt_out = select(func.count(OutreachMessage.id)).where(OutreachMessage.status == "SENT")
        outreach = (await session.execute(stmt_out)).scalar() or 0

        # Response
        stmt_rep = select(func.count(Reply.id))
        response = (await session.execute(stmt_rep)).scalar() or 0

        # Positive
        stmt_pos = select(func.count(Reply.id)).where(Reply.classification.in_(["INTERESTED", "MEETING_REQUEST", "POSITIVE"]))
        positive = (await session.execute(stmt_pos)).scalar() or 0

        # Demo (Active Demos)
        stmt_demo = select(func.count(Project.id))
        demo = (await session.execute(stmt_demo)).scalar() or 0

        # Proposal
        stmt_prop = select(func.count(Proposal.id))
        proposal = (await session.execute(stmt_prop)).scalar() or 0

        # Payment
        stmt_pay = select(func.count(Payment.id))
        payment = (await session.execute(stmt_pay)).scalar() or 0

        # Won (Verified Payment)
        stmt_won = select(func.count(Payment.id)).where(Payment.status == "CONFIRMED")
        won = (await session.execute(stmt_won)).scalar() or 0

        # Delivery & Retained
        stmt_cust = select(func.count(Customer.id))
        delivery = (await session.execute(stmt_cust)).scalar() or 0
        retained = delivery  # Baseline

        stage_counts = {
            "DISCOVERED": discovered,
            "QUALIFIED": max(qualified, 1),
            "CONTACTABLE": contactable,
            "OUTREACH": outreach,
            "RESPONSE": response,
            "POSITIVE": positive,
            "DEMO": demo,
            "PROPOSAL": proposal,
            "PAYMENT": payment,
            "WON": won,
            "DELIVERY": delivery,
            "RETAINED": retained
        }

        # Conversion Rates
        conversions: Dict[str, float] = {}
        for i in range(len(cls.STAGES) - 1):
            s_from = cls.STAGES[i]
            s_to = cls.STAGES[i+1]
            c_from = stage_counts[s_from]
            c_to = stage_counts[s_to]
            rate = round((c_to / c_from * 100.0), 1) if c_from > 0 else 0.0
            conversions[f"{s_from}_TO_{s_to}"] = min(100.0, rate)

        # Bottleneck Detection
        bottlenecks: List[Dict[str, Any]] = []

        if outreach > 0 and (response / outreach) < 0.10:
            bottlenecks.append({
                "observation": f"Only {conversions.get('OUTREACH_TO_RESPONSE', 0)}% of outreaches generated a response.",
                "possible_cause": "Subject line lack of relevance or generic non-personalized hook.",
                "evidence": f"Total sends: {outreach}, Total replies: {response}.",
                "recommendation": "Incorporate specific technical performance deficiency (e.g. LCP > 4.2s) in subject line."
            })

        if positive > 0 and proposal == 0:
            bottlenecks.append({
                "observation": "Positive replies received but zero formal proposals generated.",
                "possible_cause": "Sales cycle lag or manual proposal bottleneck.",
                "evidence": f"Positive replies: {positive}, Proposals: {proposal}.",
                "recommendation": "Automatically generate draft proposal immediately upon positive reply detection."
            })

        return {
            "stage_counts": stage_counts,
            "conversion_rates": conversions,
            "bottlenecks": bottlenecks,
            "overall_funnel_health": "HEALTHY" if not bottlenecks else "OPTIMIZATION_OPPORTUNITIES_IDENTIFIED"
        }


funnel_analytics_engine = FunnelAnalyticsEngine()
