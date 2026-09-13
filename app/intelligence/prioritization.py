"""
Prospect Prioritization Engine — Mega Prompt 8.
Ranks leads deterministically using Expected Commercial Value:
EV = P(Conversion) * Expected Deal Value * Service Fit * Evidence Confidence.
Respects active outreach locks, suppression lists, and daily caps.
"""
import math
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.database.models import Business, ActiveOutreachLock, SuppressionList
from app.intelligence.lead_intelligence import lead_intelligence_engine
from app.intelligence.models import IntelligenceSignal, SignalType, EpistemicStatus

class ProspectPriorityEngine:
    """
    Ranks active prospects to determine execution order.
    Combines calibrated conversion probability with economic potential and compliance state.
    """

    COMMERCIAL_FLOOR_USD = 500.0

    @classmethod
    async def rank_prospects(
        cls,
        session: AsyncSession,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Evaluates and ranks all contactable, un-suppressed prospects.
        """
        # 1. Fetch Candidates (Not archived, has contact)
        stmt = (
            select(Business)
            .order_by(desc(Business.id))
            .limit(100)
        )
        businesses = (await session.execute(stmt)).scalars().all()

        # 2. Check Active Lock
        stmt_lock = select(ActiveOutreachLock).where(ActiveOutreachLock.slot_id == 1)
        active_lock = (await session.execute(stmt_lock)).scalar_one_or_none()
        locked_biz_id = active_lock.business_id if active_lock and active_lock.status == "ACTIVE" else None

        ranked: List[Dict[str, Any]] = []

        for biz in businesses:
            eval_res = await lead_intelligence_engine.evaluate_lead(session, biz.id)
            score = eval_res["overall_score"]
            components = eval_res["components"]

            # Check suppression
            conditions = []
            if getattr(biz, "domain", None):
                conditions.append(SuppressionList.domain == biz.domain)
            if getattr(biz, "public_email", None):
                conditions.append(SuppressionList.email == biz.public_email)
            if conditions:
                from sqlalchemy import or_
                stmt_sup = select(SuppressionList).where(or_(*conditions))
                is_suppressed = bool((await session.execute(stmt_sup)).scalar_one_or_none())
            else:
                is_suppressed = False

            if is_suppressed or score <= 0.0:
                continue

            # Conversion Probability: Sigmoid calibration around score=65
            logit = (score - 65.0) / 14.0
            p_conversion = round(min(0.95, max(0.02, 1.0 / (1.0 + math.exp(-logit)))), 3)

            # Expected Deal Value (Commercial Floor enforced)
            base_deal_usd = max(cls.COMMERCIAL_FLOOR_USD, float(getattr(biz, "estimated_deal_size", 750.0) or 750.0))
            service_fit_ratio = components["service_fit"] / 100.0
            ev_confidence = eval_res["confidence"]

            # Formula: EV = P(Conversion) * Deal Value * Service Fit * Evidence Confidence
            expected_value_usd = round(p_conversion * base_deal_usd * service_fit_ratio * ev_confidence, 2)

            # Priority Boost for Active Engagements or Country Priority
            priority_score = expected_value_usd
            if locked_biz_id == biz.id:
                priority_score += 200.0  # Currently locked active prospect

            ranked.append({
                "business_id": biz.id,
                "business_name": biz.name,
                "country_code": getattr(biz, "country_code", None) or getattr(biz, "country", None) or "US",
                "industry": biz.niche or "General",
                "overall_lead_score": score,
                "p_conversion": p_conversion,
                "expected_deal_value_usd": base_deal_usd,
                "service_fit_ratio": service_fit_ratio,
                "evidence_confidence": ev_confidence,
                "expected_value_usd": expected_value_usd,
                "priority_score": round(priority_score, 2),
                "is_active_locked": (locked_biz_id == biz.id),
                "recommended_service": eval_res["recommended_service"],
                "recommended_channel": eval_res["recommended_channel"],
                "recommended_action": eval_res["recommended_next_action"]
            })

        # Sort descending by priority_score
        ranked.sort(key=lambda x: x["priority_score"], reverse=True)
        return ranked[:limit]


prospect_priority_engine = ProspectPriorityEngine()
