from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.models import (
    Business, OutreachMessage, OutreachStatus, Reply,
    ReplyClassification, Customer, PipelineStage, Offer, Country, Niche
)

class AnalyticsEngine:
    """
    Computes real-time executive dashboard KPIs, conversion funnels,
    revenue metrics, and channel efficiency indicators.
    """

    async def get_dashboard_metrics(self, session: AsyncSession) -> Dict[str, Any]:
        # 1. Leads Metrics
        total_leads = (await session.execute(select(func.count(Business.id)))).scalar() or 0
        verified_leads = (await session.execute(
            select(func.count(Business.id)).where(Business.verification_status == "VERIFIED")
        )).scalar() or 0
        audited_leads = (await session.execute(
            select(func.count(Business.id)).where(Business.pipeline_stage != PipelineStage.DISCOVERED.value)
        )).scalar() or 0
        qualified_leads = (await session.execute(
            select(func.count(Business.id)).where(Business.pipeline_stage.in_([
                PipelineStage.QUALIFIED.value,
                PipelineStage.OUTREACH_READY.value,
                PipelineStage.APPROVAL.value,
                PipelineStage.CONTACTED.value,
                PipelineStage.REPLIED.value,
                PipelineStage.QUALIFIED_REPLY.value,
                PipelineStage.CALL.value,
                PipelineStage.PROPOSAL.value,
                PipelineStage.WON.value
            ]))
        )).scalar() or 0

        # 2. Outreach Metrics
        outreach_total = (await session.execute(select(func.count(OutreachMessage.id)))).scalar() or 0
        outreach_pending = (await session.execute(
            select(func.count(OutreachMessage.id)).where(OutreachMessage.status == OutreachStatus.PENDING_APPROVAL.value)
        )).scalar() or 0
        outreach_approved = (await session.execute(
            select(func.count(OutreachMessage.id)).where(OutreachMessage.status.in_([OutreachStatus.APPROVED.value, OutreachStatus.SENT.value]))
        )).scalar() or 0
        outreach_sent = (await session.execute(
            select(func.count(OutreachMessage.id)).where(OutreachMessage.status == OutreachStatus.SENT.value)
        )).scalar() or 0

        # 3. Replies & Sales Metrics
        replies_total = (await session.execute(select(func.count(Reply.id)))).scalar() or 0
        replies_positive = (await session.execute(
            select(func.count(Reply.id)).where(Reply.classification.in_([
                ReplyClassification.INTERESTED.value,
                ReplyClassification.MEETING_REQUEST.value,
                ReplyClassification.PRICE_REQUEST.value
            ]))
        )).scalar() or 0

        calls_scheduled = (await session.execute(
            select(func.count(Business.id)).where(Business.pipeline_stage.in_([PipelineStage.CALL.value, PipelineStage.PROPOSAL.value, PipelineStage.WON.value]))
        )).scalar() or 0
        proposals_sent = (await session.execute(
            select(func.count(Business.id)).where(Business.pipeline_stage.in_([PipelineStage.PROPOSAL.value, PipelineStage.WON.value]))
        )).scalar() or 0
        deals_won = (await session.execute(
            select(func.count(Business.id)).where(Business.pipeline_stage == PipelineStage.WON.value)
        )).scalar() or 0
        deals_lost = (await session.execute(
            select(func.count(Business.id)).where(Business.pipeline_stage == PipelineStage.LOST.value)
        )).scalar() or 0

        # 4. Financial & Revenue Metrics
        won_revenue = (await session.execute(select(func.sum(Customer.contract_amount)))).scalar() or 0.0
        avg_deal_size = (won_revenue / deals_won) if deals_won > 0 else 0.0

        # Active pipeline potential value (sum of offers for leads in progress)
        pipeline_val_q = select(func.sum(Offer.recommended_price)).join(Business).where(
            Business.pipeline_stage.in_([
                PipelineStage.QUALIFIED.value,
                PipelineStage.OUTREACH_READY.value,
                PipelineStage.APPROVAL.value,
                PipelineStage.CONTACTED.value,
                PipelineStage.REPLIED.value,
                PipelineStage.QUALIFIED_REPLY.value,
                PipelineStage.CALL.value,
                PipelineStage.PROPOSAL.value
            ])
        )
        pipeline_value = (await session.execute(pipeline_val_q)).scalar() or 0.0

        # 5. Conversion Rates (%)
        lead_to_audited_rate = round((audited_leads / total_leads * 100), 1) if total_leads > 0 else 0.0
        qualification_rate = round((qualified_leads / total_leads * 100), 1) if total_leads > 0 else 0.0
        reply_rate = round((replies_total / outreach_sent * 100), 1) if outreach_sent > 0 else 0.0
        qualified_reply_rate = round((replies_positive / outreach_sent * 100), 1) if outreach_sent > 0 else 0.0
        close_rate = round((deals_won / qualified_leads * 100), 1) if qualified_leads > 0 else 0.0

        # 6. Revenue Breakdown by Country & Niche
        country_rev_q = select(Business.country, func.sum(Customer.contract_amount)).join(Customer).group_by(Business.country)
        rev_by_country = dict((await session.execute(country_rev_q)).all())

        niche_rev_q = select(Business.niche, func.sum(Customer.contract_amount)).join(Customer).group_by(Business.niche)
        rev_by_niche = dict((await session.execute(niche_rev_q)).all())

        return {
            "leads": {
                "total": total_leads,
                "verified": verified_leads,
                "audited": audited_leads,
                "qualified": qualified_leads,
                "qualification_rate_pct": qualification_rate
            },
            "outreach": {
                "total_drafted": outreach_total,
                "pending_approval": outreach_pending,
                "approved": outreach_approved,
                "sent": outreach_sent,
                "approval_rate_pct": round((outreach_approved / outreach_total * 100), 1) if outreach_total > 0 else 0.0
            },
            "sales": {
                "replies_total": replies_total,
                "replies_positive": replies_positive,
                "calls_scheduled": calls_scheduled,
                "proposals_sent": proposals_sent,
                "deals_won": deals_won,
                "deals_lost": deals_lost,
                "reply_rate_pct": reply_rate,
                "qualified_reply_rate_pct": qualified_reply_rate,
                "close_rate_pct": close_rate
            },
            "revenue": {
                "won_revenue_usd": won_revenue,
                "pipeline_value_usd": pipeline_value,
                "average_deal_size_usd": round(avg_deal_size, 2),
                "revenue_by_country": rev_by_country,
                "revenue_by_niche": rev_by_niche
            }
        }

analytics_engine = AnalyticsEngine()
