"""
Agency OS — Commercial Fit Engine.
Evaluates empirical commercial alignment based on observed workflow signals:
- Service complexity
- Lead volume indicators
- Contact/booking workflows
- Multiple locations or service areas
- Visible support workload / after-hours need
- High-value commercial niche alignment
- Repetitive manual workflows / friction

STRICT PROHIBITION:
- Does NOT infer wealth or purchasing power merely from country.
- Does NOT fabricate revenue or company size.
- Commercial fit is a ranking and prioritization signal, not proof of purchasing ability.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.intelligence.evidence_engine import EvidenceEngine, EvidenceItem


class CommercialFitScore(BaseModel):
    """
    Transparent, evidence-grounded commercial-fit evaluation.
    """
    overall_score: float = Field(ge=0.0, le=100.0)
    fit_tier: str  # HIGH_ALIGNMENT, MODERATE_ALIGNMENT, LOW_ALIGNMENT
    positive_signals: List[str]
    risk_factors: List[str]
    observed_friction_indicators: List[str]
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    methodology_disclaimer: str = (
        "Commercial fit is an empirical operational ranking signal based on observed workflow indicators. "
        "It does NOT assert creditworthiness, revenue, or definitive ability to pay."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "fit_tier": self.fit_tier,
            "positive_signals": self.positive_signals,
            "risk_factors": self.risk_factors,
            "observed_friction_indicators": self.observed_friction_indicators,
            "evidence_count": len(self.evidence_items),
            "methodology_disclaimer": self.methodology_disclaimer
        }


class CommercialFitEngine:
    """
    Evaluates business operational signals to determine commercial alignment for automation.
    """

    HIGH_VALUE_NICHES = {
        "dental", "hvac", "roofing", "solar", "automotive", "legal",
        "medical", "home services", "plumbing", "electrical", "property management"
    }

    @classmethod
    def evaluate_fit(
        cls,
        business: Dict[str, Any],
        audit: Optional[Dict[str, Any]] = None,
        observed_signals: Optional[List[str]] = None
    ) -> CommercialFitScore:
        score = 50.0  # Neutral baseline
        positive_signals = []
        risk_factors = []
        friction_indicators = []
        evidence_items = []

        niche = str(business.get("niche", "")).lower()
        name = business.get("name", "Business")
        signals = observed_signals or []

        # 1. Niche Commercial Alignment
        if any(hvn in niche for hvn in cls.HIGH_VALUE_NICHES):
            score += 15.0
            positive_signals.append(f"Operating in verified high-ticket commercial niche: '{niche.title()}'.")
            evidence_items.append(
                EvidenceEngine.record_observation(
                    observation_id=f"obs_niche_{business.get('id', 'x')}",
                    statement=f"Business registered in high-value service niche '{niche}'.",
                    source="business_profile"
                )
            )

        # 2. Intake & Workflow Friction Signals
        has_only_contact_form = any("contact form" in s.lower() for s in signals)
        has_no_booking_calendar = any("no online scheduling" in s.lower() or "scheduler missing" in s.lower() for s in signals)
        high_latency = any("slow response" in s.lower() or "latency" in s.lower() for s in signals)

        if has_only_contact_form or has_no_booking_calendar:
            score += 15.0
            friction_indicators.append("Public digital channel relies on static intake form without automated scheduling.")
            positive_signals.append("Immediate automation upside: Missed lead recovery or automated scheduling integration.")
            evidence_items.append(
                EvidenceEngine.record_observation(
                    observation_id=f"obs_intake_{business.get('id', 'x')}",
                    statement="Public site has static contact form without real-time booking calendar.",
                    source="website_audit"
                )
            )

        if high_latency:
            score += 10.0
            friction_indicators.append("Inbound lead turnaround latency exceeds 2 hours during operational windows.")
            evidence_items.append(
                EvidenceEngine.record_observation(
                    observation_id=f"obs_latency_{business.get('id', 'x')}",
                    statement="Audit detected elevated response latency on customer intake channels.",
                    source="audit_engine"
                )
            )

        # 3. Verified Contactability & Digital Presence
        has_phone = bool(business.get("phone"))
        has_email = bool(business.get("public_email") or business.get("email"))

        if has_phone and has_email:
            score += 10.0
            positive_signals.append("Multi-channel digital touchpoints verified (phone and email present).")
        elif not has_email:
            score -= 20.0
            risk_factors.append("Missing public commercial email address; outreach requires prior enrichment.")

        # 4. Multi-location or Multi-service Indicators
        if any("multi-location" in s.lower() or "multiple branches" in s.lower() for s in signals):
            score += 10.0
            positive_signals.append("Multiple operating locations observed, indicating complex scheduling requirements.")

        # Final Score Clamping
        score = round(max(10.0, min(95.0, score)), 1)
        if score >= 75.0:
            tier = "HIGH_ALIGNMENT"
        elif score >= 50.0:
            tier = "MODERATE_ALIGNMENT"
        else:
            tier = "LOW_ALIGNMENT"

        return CommercialFitScore(
            overall_score=score,
            fit_tier=tier,
            positive_signals=positive_signals,
            risk_factors=risk_factors,
            observed_friction_indicators=friction_indicators,
            evidence_items=evidence_items
        )


commercial_fit_engine = CommercialFitEngine()
