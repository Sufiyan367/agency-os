"""
Decision Engine for Autonomous Revenue Agent.
Evaluates current state, metrics, commercial threshold, and safety flags to determine next action.
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.agents.state_machine import ProspectState


class DecisionResult(BaseModel):
    decision: str
    target_state: ProspectState
    reason: str
    confidence: float
    next_action: str
    should_pause: bool = False
    requires_human: bool = False


class DecisionEngine:
    """Evaluates business rules and evidence before allowing any state progression."""

    @staticmethod
    def evaluate_discovery(business_name: str, has_domain: bool, has_phone: bool) -> DecisionResult:
        if not has_domain and not has_phone:
            return DecisionResult(
                decision="SKIP",
                target_state=ProspectState.SKIPPED,
                reason="No verifiable standalone digital footprint or phone number observed.",
                confidence=0.99,
                next_action="Advance to next prospective business.",
                should_pause=False
            )
        return DecisionResult(
            decision="PROCEED",
            target_state=ProspectState.AUDIT,
            reason="Observed viable standalone business identity. Ready for technical audit.",
            confidence=0.95,
            next_action="Execute automated technical performance and mobile UX diagnostic."
        )

    @staticmethod
    def evaluate_commercial_qualification(
        estimated_min_value: float,
        commercial_floor: float = 500.0,
        buyer_score: float = 0.0,
        opp_score: float = 0.0
    ) -> DecisionResult:
        if estimated_min_value < commercial_floor:
            return DecisionResult(
                decision="SKIP",
                target_state=ProspectState.SKIPPED,
                reason=f"Estimated deal value (${estimated_min_value:,.0f}) is below commercial floor (${commercial_floor:,.0f}).",
                confidence=0.98,
                next_action="Skip prospect to protect agency economics."
            )

        if opp_score < 40.0:
            return DecisionResult(
                decision="SKIP",
                target_state=ProspectState.SKIPPED,
                reason="Opportunity score insufficient for profitable agency turnaround.",
                confidence=0.90,
                next_action="Skip prospect."
            )

        return DecisionResult(
            decision="QUALIFIED",
            target_state=ProspectState.CONTACT_DISCOVERY,
            reason=f"Passed $500+ commercial floor (${estimated_min_value:,.0f} est) with Buyer Score {buyer_score:.1f}.",
            confidence=0.92,
            next_action="Scan for verified public business contact channels."
        )

    @staticmethod
    def evaluate_contact_channel(email: Optional[str], phone: Optional[str], voice_enabled: bool) -> DecisionResult:
        if email and "@" in email:
            return DecisionResult(
                decision="SELECT_EMAIL",
                target_state=ProspectState.OUTREACH_PREP,
                reason=f"Found verified public business domain email: {email}",
                confidence=0.95,
                next_action="Draft evidence-grounded outreach email."
            )
        if phone and voice_enabled:
            return DecisionResult(
                decision="SELECT_VOICE",
                target_state=ProspectState.OUTREACH_PREP,
                reason=f"Found verified business phone: {phone}. Voice calling enabled.",
                confidence=0.88,
                next_action="Prepare conversational voice call script."
            )
        return DecisionResult(
            decision="SKIP",
            target_state=ProspectState.SKIPPED,
            reason="No verified public business email or enabled voice channel available. Refusing fabrication.",
            confidence=0.99,
            next_action="Skip prospect."
        )
