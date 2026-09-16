"""
Agency OS — Opportunity Engine.
Converts structured research inferences into high-margin commercial software & automation opportunities,
strictly grounded in the Solution Capability Catalog and commercial economic floors.
"""

from typing import Dict, Any, List, Optional
import uuid

from app.intelligence.knowledge_model import ExplainableIntelligence
from app.intelligence.capability_catalog import capability_catalog, SolutionCapability


class OpportunityPacket:
    """
    Commercial opportunity packet ready for outreach, demo generation, and proposal generation.
    """
    def __init__(
        self,
        opportunity_id: str,
        business_id: int,
        domain: str,
        capability: SolutionCapability,
        deal_value_usd: float,
        advance_required_usd: float,
        p_win_estimate: float,
        roi_estimate: Dict[str, Any],
        explainable_summary: ExplainableIntelligence,
        decision_trace: Dict[str, Any]
    ):
        self.opportunity_id = opportunity_id
        self.business_id = business_id
        self.domain = domain
        self.capability = capability
        self.deal_value_usd = deal_value_usd
        self.advance_required_usd = advance_required_usd
        self.p_win_estimate = p_win_estimate
        self.roi_estimate = roi_estimate
        self.explainable_summary = explainable_summary
        self.decision_trace = decision_trace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "business_id": self.business_id,
            "domain": self.domain,
            "capability_id": self.capability.capability_id,
            "capability_name": self.capability.name,
            "deal_value_usd": self.deal_value_usd,
            "advance_required_usd": self.advance_required_usd,
            "p_win_estimate": self.p_win_estimate,
            "roi_estimate": self.roi_estimate,
            "explainable_summary": self.explainable_summary.model_dump(),
            "decision_trace": self.decision_trace
        }


class OpportunityEngine:
    """
    Synthesizes commercial opportunities from structured research findings.
    """

    COMMERCIAL_FLOOR_USD = 500.0

    @classmethod
    def generate_opportunity(
        cls,
        research_result: Dict[str, Any],
        business_profile: Optional[Dict[str, Any]] = None
    ) -> OpportunityPacket:
        """
        Synthesizes a concrete opportunity packet from research analysis.
        """
        biz_id = research_result.get("business_id", 1)
        domain = research_result.get("domain", "example.com")
        recommendations = research_result.get("recommendations", [])
        explainable: ExplainableIntelligence = research_result.get("explainable_summary")

        # Select top recommended capability
        top_rec = recommendations[0] if recommendations else None
        capability = None
        if top_rec:
            capability = capability_catalog.get_capability(top_rec.capability_id)

        if not capability:
            # Default to High-Conversion Intake
            capability = capability_catalog.get_capability("CAP-001-LEAD-CAPTURE")

        # Enforce commercial pricing floor
        target_price = max(cls.COMMERCIAL_FLOOR_USD, capability.target_price_usd)
        advance_required = round(target_price * 0.40, 2)  # Standard 40% advance deposit

        # Calculate estimated ROI
        monthly_labor_saved_usd = 800.0 if capability.complexity_level == "LOW" else 1500.0
        annual_value_usd = monthly_labor_saved_usd * 12.0
        roi_ratio = round(annual_value_usd / target_price, 1)

        p_win = min(0.95, max(0.40, round(explainable.confidence * 0.90, 2)))

        opp_id = f"opp_{uuid.uuid4().hex[:8]}"

        decision_trace = {
            "opportunity_id": opp_id,
            "selected_capability_id": capability.capability_id,
            "pricing_floor_enforced": target_price >= cls.COMMERCIAL_FLOOR_USD,
            "confidence": explainable.confidence,
            "p_win": p_win,
            "roi_ratio": f"{roi_ratio}x",
            "annual_value_usd": annual_value_usd,
            "advance_deposit_percentage": "40%"
        }

        return OpportunityPacket(
            opportunity_id=opp_id,
            business_id=biz_id,
            domain=domain,
            capability=capability,
            deal_value_usd=target_price,
            advance_required_usd=advance_required,
            p_win_estimate=p_win,
            roi_estimate={
                "monthly_savings_usd": monthly_labor_saved_usd,
                "annual_value_usd": annual_value_usd,
                "payback_months": round(target_price / monthly_labor_saved_usd, 1),
                "roi_multiple": roi_ratio
            },
            explainable_summary=explainable,
            decision_trace=decision_trace
        )

    @classmethod
    def generate_portfolio(
        cls,
        research_result: Dict[str, Any],
        business_profile: Optional[Dict[str, Any]] = None
    ) -> List[OpportunityPacket]:
        """
        Synthesizes a full portfolio of ranked commercial opportunities from all recommendations.
        """
        biz_id = research_result.get("business_id", 1)
        domain = research_result.get("domain", "example.com")
        recommendations = research_result.get("recommendations", [])
        explainable: ExplainableIntelligence = research_result.get("explainable_summary")

        portfolio: List[OpportunityPacket] = []
        for rec in recommendations:
            cap = capability_catalog.get_capability(rec.capability_id)
            if not cap:
                continue

            target_price = max(cls.COMMERCIAL_FLOOR_USD, cap.target_price_usd)
            advance_required = round(target_price * 0.40, 2)
            monthly_labor_saved_usd = 800.0 if cap.complexity_level == "LOW" else 1500.0
            annual_value_usd = monthly_labor_saved_usd * 12.0
            roi_ratio = round(annual_value_usd / target_price, 1)
            p_win = min(0.95, max(0.40, round(rec.confidence * 0.90, 2)))

            opp_id = f"opp_{uuid.uuid4().hex[:8]}"
            decision_trace = {
                "opportunity_id": opp_id,
                "selected_capability_id": cap.capability_id,
                "pricing_floor_enforced": target_price >= cls.COMMERCIAL_FLOOR_USD,
                "confidence": rec.confidence,
                "p_win": p_win,
                "roi_ratio": f"{roi_ratio}x",
                "annual_value_usd": annual_value_usd,
                "advance_deposit_percentage": "40%"
            }

            portfolio.append(OpportunityPacket(
                opportunity_id=opp_id,
                business_id=biz_id,
                domain=domain,
                capability=cap,
                deal_value_usd=target_price,
                advance_required_usd=advance_required,
                p_win_estimate=p_win,
                roi_estimate={
                    "monthly_savings_usd": monthly_labor_saved_usd,
                    "annual_value_usd": annual_value_usd,
                    "payback_months": round(target_price / monthly_labor_saved_usd, 1),
                    "roi_multiple": roi_ratio
                },
                explainable_summary=explainable,
                decision_trace=decision_trace
            ))

        if not portfolio:
            # Return at least the single default opportunity
            portfolio.append(cls.generate_opportunity(research_result, business_profile))

        # Sort descending by deal_value * p_win (expected commercial value)
        portfolio.sort(key=lambda o: o.deal_value_usd * o.p_win_estimate, reverse=True)
        return portfolio


opportunity_engine = OpportunityEngine()

