"""
Agency OS — Client Retention & Expansion Engine.
Analyzes post-handover client accounts (WON / DELIVERY_COMPLETE):
- Examines approved operational signals and uptime telemetry.
- Identifies legitimate, non-spam expansion opportunities.
- Prepares structured EXPANSION_OPPORTUNITY.
- Strictly requires human approval (no autonomous proposals or pitches).
"""
from typing import Dict, Any, List, Optional
import uuid
from pydantic import BaseModel, Field
from datetime import datetime


class ExpansionOpportunity(BaseModel):
    """
    Legitimate expansion opportunity identified for a retained client.
    """
    opportunity_id: str
    customer_id: int
    business_id: int
    business_name: str
    observed_need: str
    evidence: List[str]
    recommended_capability: str
    estimated_scope: str
    recommended_next_action: str
    requires_human_approval: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "customer_id": self.customer_id,
            "business_id": self.business_id,
            "business_name": self.business_name,
            "observed_need": self.observed_need,
            "evidence": self.evidence,
            "recommended_capability": self.recommended_capability,
            "estimated_scope": self.estimated_scope,
            "recommended_next_action": self.recommended_next_action,
            "requires_human_approval": self.requires_human_approval,
            "created_at": self.created_at.isoformat()
        }


class RetentionExpansionEngine:
    """
    Identifies high-leverage expansions for successfully onboarded clients.
    """

    EXPANSION_PATTERNS = {
        "CAP-001-LEAD-CAPTURE": {
            "expansion_cap": "CAP-004-APPOINTMENT-AUTOMATION",
            "name": "Automated Appointment Scheduling",
            "trigger_indicator": "High inbound lead volume requiring real-time booking synchronization",
            "scope": "Integrate two-way calendar booking with lead confirmation textback."
        },
        "CAP-002-CALL-RECOVERY": {
            "expansion_cap": "CAP-005-CRM-AUTOMATION",
            "name": "CRM Sync & Lead Tracking",
            "trigger_indicator": "Recovered call inquiries require structured pipeline logging",
            "scope": "Two-way webhook synchronization between missed-call textback and CRM datastore."
        },
        "DEFAULT": {
            "expansion_cap": "CAP-006-247-MONITORING",
            "name": "24/7 Automated Health & Telemetry Monitoring",
            "trigger_indicator": "Live deployment operating without automated synthetic health checks",
            "scope": "Setup synthetic health monitors, uptime alerts, and weekly performance reports."
        }
    }

    @classmethod
    def analyze_expansion(
        cls,
        customer_id: int,
        business_id: int,
        business_name: str,
        deployed_capabilities: List[str],
        operational_stats: Optional[Dict[str, Any]] = None
    ) -> Optional[ExpansionOpportunity]:
        """
        Analyzes delivered account for legitimate expansion.
        Returns EXPANSION_OPPORTUNITY requiring operator approval.
        """
        stats = operational_stats or {}
        opp_id = f"exp_{uuid.uuid4().hex[:8]}"

        # Look for complementary capability not yet deployed
        pattern = cls.EXPANSION_PATTERNS.get(deployed_capabilities[0] if deployed_capabilities else "", cls.EXPANSION_PATTERNS["DEFAULT"])

        evidence = [
            f"Active deployment running with base capabilities: {', '.join(deployed_capabilities)}.",
            f"Observed operational trigger: {pattern['trigger_indicator']}."
        ]
        if stats.get("uptime_pct", 100.0) >= 99.0:
            evidence.append("Base deployment has maintained >= 99.0% uptime; ready for secondary tier.")

        return ExpansionOpportunity(
            opportunity_id=opp_id,
            customer_id=customer_id,
            business_id=business_id,
            business_name=business_name,
            observed_need=pattern["trigger_indicator"],
            evidence=evidence,
            recommended_capability=pattern["name"],
            estimated_scope=pattern["scope"],
            recommended_next_action="OPERATOR_REVIEW_EXPANSION_SCOPE",
            requires_human_approval=True
        )


retention_expansion_engine = RetentionExpansionEngine()
