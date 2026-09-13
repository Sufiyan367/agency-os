"""
Sales Intelligence Engine — Mega Prompt 8.
Calculates deal win probability P(Win), expected revenue, stage velocities,
and close risk scores with explicit confidence calibration.
"""
import math
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database.models import Deal, Proposal, Business, Reply
from app.intelligence.models import (
    IntelligenceSignal, SignalType, EpistemicStatus,
    ConfidenceBand
)

class SalesIntelligenceEngine:
    """
    Computes rigorous commercial probabilities and deal risk factors.
    """

    COMMERCIAL_FLOOR_USD = 500.0

    @classmethod
    async def evaluate_opportunity(
        cls,
        session: AsyncSession,
        business_id: int
    ) -> Dict[str, Any]:
        """
        Evaluates commercial viability, win probability, and stage risk for a prospect.
        """
        biz = await session.get(Business, business_id)
        if not biz:
            return {"error": "Business not found", "status": "NOT_FOUND"}

        # 1. Proposal history
        stmt_prop = (
            select(Proposal)
            .where(Proposal.business_id == business_id)
            .order_by(desc(Proposal.created_at))
            .limit(1)
        )
        prop = (await session.execute(stmt_prop)).scalar_one_or_none()

        deal_value = max(cls.COMMERCIAL_FLOOR_USD, float(prop.total_value if prop else getattr(biz, "estimated_deal_size", None) or 750.0))

        # 2. Reply & Engagement History
        stmt_replies = select(Reply).where(Reply.business_id == business_id)
        replies = (await session.execute(stmt_replies)).scalars().all()
        inbound_count = len(replies)
        pos_count = sum(1 for r in replies if r.classification in ("INTERESTED", "MEETING_REQUEST", "POSITIVE"))
        objection_count = sum(1 for r in replies if "OBJECTION" in r.classification)

        # 3. Stage Velocity (Days in current stage)
        days_in_stage = 1.0
        if biz.created_at:
            days_in_stage = max(0.1, (datetime.utcnow() - biz.created_at).total_seconds() / 86400.0)

        # 4. Win Probability Model (Deterministic logistic calibration)
        # Base conversion rate ~15% for qualified B2B leads
        logit = -1.75
        if prop: logit += 1.2
        if pos_count > 0: logit += 1.5
        if inbound_count > 0: logit += 0.8
        if objection_count > 0: logit -= (0.5 * objection_count)
        if days_in_stage > 14.0: logit -= 0.6  # Stagnation penalty

        p_win = round(1.0 / (1.0 + math.exp(-logit)), 3)
        p_win = min(0.95, max(0.02, p_win))

        # 5. Expected Value
        expected_value_usd = round(p_win * deal_value, 2)

        # 6. Close Risk Assessment
        if days_in_stage > 21.0 or objection_count >= 2:
            close_risk = "HIGH"
            risk_reason = "Prolonged inactivity or multiple unresolved commercial objections."
        elif days_in_stage > 10.0 or objection_count == 1:
            close_risk = "MEDIUM"
            risk_reason = "Moderate pipeline stagnation or active inquiry pending."
        else:
            close_risk = "LOW"
            risk_reason = "Healthy velocity and positive engagement signals."

        # Confidence: Higher when multi-turn conversation and proposal data exist
        confidence = 0.85 if prop and inbound_count > 0 else 0.60 if inbound_count > 0 else 0.40
        confidence_band = "HIGH" if confidence >= 0.80 else "MEDIUM" if confidence >= 0.50 else "LOW"

        return {
            "business_id": business_id,
            "deal_value_usd": deal_value,
            "win_probability": p_win,
            "expected_value_usd": expected_value_usd,
            "stage_velocity_days": round(days_in_stage, 1),
            "inbound_count": inbound_count,
            "positive_replies": pos_count,
            "objection_count": objection_count,
            "close_risk": close_risk,
            "risk_reason": risk_reason,
            "confidence": confidence,
            "confidence_band": confidence_band,
            "is_estimate": (confidence < 0.80),
            "epistemic_status": EpistemicStatus.PREDICTION.value
        }


sales_intelligence_engine = SalesIntelligenceEngine()
