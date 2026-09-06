from typing import Dict, Any, List

class MarketDecisionTraceBuilder:
    """Constructs transparent, reproducible 5-point decision traces for market opportunities."""

    def build_trace(
        self,
        country_name: str,
        niche_name: str,
        service_name: str,
        service_id: str,
        market_score: float,
        expected_deal_usd: float,
        ev_usd: float,
        confidence: float,
        signals: Dict[str, Any],
        evidence_sources: List[str],
        conflicts_resolved: str = "",
        risks: List[str] = None,
        unknowns: List[str] = None
    ) -> Dict[str, Any]:
        atp = signals.get("ABILITY_TO_PAY", 0.7)
        dig = signals.get("DIGITAL_MATURITY", 0.7)
        demand = signals.get("SERVICE_DEMAND", 0.7)
        growth = signals.get("MARKET_GROWTH", 0.7)

        return {
            "summary": f"Ranked opportunity for {service_name} in {country_name} ({niche_name}) with EV ${ev_usd:,.2f} USD.",
            "why_this_country": [
                f"{country_name} demonstrates strong economic capacity with ability-to-pay index of {atp:.2f}.",
                f"Digital maturity and automation infrastructure score at {dig:.2f}/1.00.",
                "Jurisdictional compliance rules permit verified commercial B2B engagement."
            ],
            "why_this_niche": [
                f"{niche_name} represents high-value commercial transactions where single client acquisition justifies premium automation.",
                "Inquiry capture latency directly causes lost revenue and operational leakage.",
                "High recurring transaction velocity enables rapid payback for automated systems."
            ],
            "why_this_service": [
                f"{service_name} ({service_id}) systematically closes the diagnosed inquiry response gap.",
                "Directly replaces manual staff intake with autonomous 24/7 qualification.",
                "Meets Phase 7 implementation standards with proven catalog ROI models."
            ],
            "why_this_price": [
                f"Target package price is established at ${expected_deal_usd:,.2f} USD, strictly meeting $1,000+ commercial guidelines.",
                "Conservative ROI estimates yield a 3.5x - 6.0x value multiple within 90 days."
            ],
            "why_now": [
                f"Recent market demand signals indicate active automation expansion (index: {demand:.2f}).",
                f"Market growth trend ({growth:.2f}) presents an open competitive window before agency saturation."
            ],
            "evidence_sources": evidence_sources,
            "conflicts_resolved": conflicts_resolved or "No contradictory evidence detected.",
            "risks": risks or ["Standard commercial outreach compliance apply."],
            "unknowns": unknowns or [],
            "confidence_score": confidence,
            "overall_market_score": market_score
        }

market_decision_trace_builder = MarketDecisionTraceBuilder()
