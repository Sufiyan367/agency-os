import enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.database.models import Business, PipelineStage
from app.outreach.compliance import compliance_guard

class PolicyAction(str, enum.Enum):
    DISCOVERY = "DISCOVERY"
    AUDIT = "AUDIT"
    OFFER_CREATION = "OFFER_CREATION"
    OUTREACH_DISPATCH = "OUTREACH_DISPATCH"
    PROPOSAL_CREATION = "PROPOSAL_CREATION"
    PAYMENT_REQUEST = "PAYMENT_REQUEST"
    PAYMENT_EXECUTION = "PAYMENT_EXECUTION"

@dataclass
class PolicyDecision:
    allowed: bool
    action: str
    reason: str
    violations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocked(self) -> bool:
        return not self.allowed

class PolicyEngine:
    """
    Centralized safety policy engine for the autonomous B2B agency.
    Enforces non-negotiable commercial floors ($500+), channel dry-run simulation locks,
    emergency kill switch, human takeover locks, and compliance suppression rules.
    """

    COMMERCIAL_FLOOR_USD: float = 500.0

    @classmethod
    def get_commercial_floor(cls) -> float:
        return max(getattr(settings, "MINIMUM_SERVICE_VALUE_USD", cls.COMMERCIAL_FLOOR_USD), cls.COMMERCIAL_FLOOR_USD)

    def evaluate_commercial_value(self, amount_usd: float, context: str = "OFFER") -> PolicyDecision:
        """
        Validates whether a pricing amount strictly satisfies the $500+ commercial floor.
        Rejects any offer, quote, proposal, or transaction below $500.
        """
        floor = self.get_commercial_floor()
        violations = []

        if amount_usd < floor:
            violations.append(f"Commercial offer value (${amount_usd:.2f}) falls below the ${floor:.2f} commercial floor.")
            logger.warning(f"[PolicyEngine] Rejected {context}: ${amount_usd:.2f} < ${floor:.2f} floor")
            return PolicyDecision(
                allowed=False,
                action=PolicyAction.OFFER_CREATION.value,
                reason=f"COMMERCIAL_FLOOR_VIOLATION: ${amount_usd:.2f} is below mandatory ${floor:.2f} floor.",
                violations=violations,
                metadata={"amount_usd": amount_usd, "floor": floor, "context": context}
            )

        return PolicyDecision(
            allowed=True,
            action=PolicyAction.OFFER_CREATION.value,
            reason=f"Commercial value (${amount_usd:.2f}) meets or exceeds ${floor:.2f} floor.",
            violations=[],
            metadata={"amount_usd": amount_usd, "floor": floor, "context": context}
        )

    async def evaluate_outreach(
        self,
        session: AsyncSession,
        business: Business,
        offer_price: float,
        channel: str = "EMAIL"
    ) -> PolicyDecision:
        """
        Comprehensive pre-flight evaluation for autonomous outreach dispatch.
        Checks kill switch, human takeover, suppression, contact details, commercial floor, and daily quota.
        """
        violations = []
        floor = self.get_commercial_floor()

        # 1. Kill Switch
        if not getattr(settings, "AUTONOMOUS_AGENT_ENABLED", True):
            violations.append("Emergency kill switch is currently active (AUTONOMOUS_AGENT_ENABLED=False).")

        # 2. Human Takeover Check
        if getattr(business, "human_takeover", False):
            violations.append(f"Human takeover is active for prospect {business.domain}. Automated actions halted.")

        # 3. Commercial Price Floor Check
        if offer_price < floor:
            violations.append(f"Offer price (${offer_price:.2f}) is below mandatory ${floor:.2f} floor.")

        # 4. Genuine Contact Verification (Never fabricate)
        has_contact = bool(business.public_email or business.phone)
        if not has_contact:
            violations.append(f"No verified contact information available for {business.domain} (fabrication prohibited).")

        # 5. Channel Dry-Run Verification
        channel_upper = channel.upper()
        if channel_upper == "EMAIL":
            is_dry_run = getattr(settings, "EMAIL_DRY_RUN", True)
        elif channel_upper == "VOICE":
            is_dry_run = getattr(settings, "VOICE_DRY_RUN", True)
        else:
            is_dry_run = True

        # 6. Suppression / Opt-Out List Check
        is_supp = await compliance_guard.is_suppressed(
            session, email=business.public_email, phone=business.phone, domain=business.domain
        )
        if is_supp:
            violations.append(f"Prospect {business.domain} is on the global suppression/opt-out registry.")

        # 7. Daily Outreach Limit
        can_send = await compliance_guard.can_send_today(session)
        if not can_send:
            violations.append("Daily outreach quota (MAX_OUTREACH_PER_DAY) has been reached.")

        allowed = len(violations) == 0
        reason = "Outreach approved for dispatch." if allowed else f"Outreach blocked: {'; '.join(violations)}"

        return PolicyDecision(
            allowed=allowed,
            action=PolicyAction.OUTREACH_DISPATCH.value,
            reason=reason,
            violations=violations,
            metadata={
                "business_id": business.id,
                "domain": business.domain,
                "channel": channel_upper,
                "is_dry_run": is_dry_run,
                "offer_price": offer_price,
                "floor": floor
            }
        )

    def evaluate_payment(
        self,
        amount_usd: float,
        is_live_requested: bool = False
    ) -> PolicyDecision:
        """
        Validates financial safety gates before any payment processing.
        Prevents live financial charging when payment dry run is active.
        """
        violations = []
        floor = self.get_commercial_floor()

        if amount_usd < floor:
            violations.append(f"Payment amount (${amount_usd:.2f}) is below commercial floor (${floor:.2f}).")

        # Live payment gate check
        payments_enabled = getattr(settings, "PAYMENTS_ENABLED", False)
        payment_dry_run = getattr(settings, "PAYMENT_DRY_RUN", True)

        if is_live_requested:
            if not payments_enabled:
                violations.append("Live payment execution is disabled in system configuration (PAYMENTS_ENABLED=False).")
            if payment_dry_run:
                violations.append("Live payment execution rejected while PAYMENT_DRY_RUN=True.")

        allowed = len(violations) == 0
        reason = "Payment approved." if allowed else f"Payment blocked: {'; '.join(violations)}"

        return PolicyDecision(
            allowed=allowed,
            action=PolicyAction.PAYMENT_EXECUTION.value,
            reason=reason,
            violations=violations,
            metadata={
                "amount_usd": amount_usd,
                "is_live_requested": is_live_requested,
                "payment_dry_run": payment_dry_run,
                "payments_enabled": payments_enabled
            }
        )

    def get_safety_invariants_status(self) -> Dict[str, Any]:
        """Returns the real-time operational status of all platform safety gates."""
        return {
            "commercial_floor_usd": self.get_commercial_floor(),
            "email_dry_run": getattr(settings, "EMAIL_DRY_RUN", True),
            "voice_dry_run": getattr(settings, "VOICE_DRY_RUN", True),
            "payment_dry_run": getattr(settings, "PAYMENT_DRY_RUN", True),
            "payments_enabled": getattr(settings, "PAYMENTS_ENABLED", False),
            "autonomous_agent_enabled": getattr(settings, "AUTONOMOUS_AGENT_ENABLED", True),
            "one_at_a_time_prospecting": getattr(settings, "ONE_AT_A_TIME_PROSPECTING", True),
            "max_outreach_per_day": getattr(settings, "MAX_OUTREACH_PER_DAY", 50)
        }

policy_engine = PolicyEngine()
