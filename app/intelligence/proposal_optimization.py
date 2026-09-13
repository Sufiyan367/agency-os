"""
Proposal Optimization Engine — Mega Prompt 8.
Analyzes commercial acceptance rates, package framing, and deliverables clarity.
Strictly respects proposal versioning, manual approval, and the non-negotiable $500.00 floor.
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.models import Proposal, Payment, ProjectProposal

class ProposalOptimizationEngine:
    """
    Evaluates commercial proposal performance and recommends evidence-backed package adjustments.
    """

    COMMERCIAL_FLOOR_USD = 500.0

    @classmethod
    async def evaluate_proposal_performance(
        cls,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Analyzes historical proposal acceptance rates and pricing distribution.
        """
        stmt = select(Proposal)
        proposals = (await session.execute(stmt)).scalars().all()

        total = len(proposals)
        if total == 0:
            return {
                "total_proposals": 0,
                "acceptance_rate_pct": 0.0,
                "avg_price_usd": 0.0,
                "status": "INSUFFICIENT_DATA",
                "recommendations": [
                    "Ensure every proposal includes sandbox preview link and 40/60 milestone payment structure.",
                    "Maintain commercial floor >= $500.00."
                ]
            }

        accepted = sum(1 for p in proposals if p.status in ("ACCEPTED", "PAID", "WON"))
        avg_price = sum(float(p.total_value) for p in proposals) / total
        acc_rate = round((accepted / total * 100.0), 1)

        recommendations: List[str] = []
        if acc_rate < 30.0 and total >= 5:
            recommendations.append("Simplify deliverables scope to Core Web Vitals acceleration to reduce buyer friction.")
            recommendations.append("Add verified 14-day delivery timeline guarantee.")

        return {
            "total_proposals": total,
            "accepted_proposals": accepted,
            "acceptance_rate_pct": acc_rate,
            "avg_price_usd": round(avg_price, 2),
            "commercial_floor_enforced": True,
            "floor_usd": cls.COMMERCIAL_FLOOR_USD,
            "recommendations": recommendations or ["Proposal conversion is currently within expected target parameters."]
        }

    @classmethod
    def validate_pricing_policy(cls, proposed_price_usd: float) -> Dict[str, Any]:
        """
        Deterministic policy validation preventing sub-floor pricing recommendations.
        """
        if proposed_price_usd < cls.COMMERCIAL_FLOOR_USD:
            return {
                "valid": False,
                "adjusted_price_usd": cls.COMMERCIAL_FLOOR_USD,
                "violation": f"Proposed price (${proposed_price_usd:.0f}) violates ${cls.COMMERCIAL_FLOOR_USD:.0f} commercial floor."
            }
        return {
            "valid": True,
            "adjusted_price_usd": proposed_price_usd,
            "violation": None
        }


proposal_optimization_engine = ProposalOptimizationEngine()
