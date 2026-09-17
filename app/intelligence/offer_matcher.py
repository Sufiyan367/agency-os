"""
Agency OS — Offer Matcher.
Deterministic mapping:
PAIN -> CAPABILITY -> DEMO BLUEPRINT -> PROPOSAL SCOPE
Reuses canonical Solution Capability Catalog without duplicating capability implementations.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.intelligence.capability_catalog import capability_catalog, SolutionCapability


class MatchedOfferPlan(BaseModel):
    """
    Deterministic offer match linking detected pain to solution, demo, and scope.
    """
    detected_pain: str
    capability_id: str
    capability_name: str
    target_price_usd: float
    advance_deposit_usd: float
    turnaround_days: int
    demo_blueprint_type: str
    proposal_scope: List[str]
    delivery_template: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected_pain": self.detected_pain,
            "capability_id": self.capability_id,
            "capability_name": self.capability_name,
            "target_price_usd": self.target_price_usd,
            "advance_deposit_usd": self.advance_deposit_usd,
            "turnaround_days": self.turnaround_days,
            "demo_blueprint_type": self.demo_blueprint_type,
            "proposal_scope": self.proposal_scope,
            "delivery_template": self.delivery_template
        }


class OfferMatcher:
    """
    Maps operational pain points to standardized productized automations.
    """

    # Exact canonical pain-to-capability routing
    PAIN_ROUTING = [
        {
            "keywords": ["missed call", "after hour", "unanswered", "phone backlog", "busy line"],
            "capability_id": "CAP-002-CALL-RECOVERY",
            "detected_pain": "Missed calls and unhandled after-hours client inquiries",
            "demo_blueprint": "voice_simulator",
            "delivery_template": "missed_call_textback_v1"
        },
        {
            "keywords": ["slow response", "delayed lead", "contact form", "intake form", "lead latency", "quote delay"],
            "capability_id": "CAP-001-LEAD-CAPTURE",
            "detected_pain": "Slow inbound lead response and manual form triage",
            "demo_blueprint": "intake_stepper",
            "delivery_template": "lead_intake_automation_v1"
        },
        {
            "keywords": ["repetitive question", "faq", "receptionist", "phone triage", "general inquiry", "customer support"],
            "capability_id": "CAP-003-AI-RECEPTIONIST",
            "detected_pain": "High volume of repetitive inquiries overloading staff",
            "demo_blueprint": "chat_simulator",
            "delivery_template": "ai_receptionist_v1"
        },
        {
            "keywords": ["appointment", "booking friction", "calendar conflict", "rescheduling", "no-show", "scheduling"],
            "capability_id": "CAP-004-APPOINTMENT-AUTOMATION",
            "detected_pain": "Friction in booking appointments and frequent scheduling drop-offs",
            "demo_blueprint": "calendar_slot_sync",
            "delivery_template": "appointment_booking_v1"
        },
        {
            "keywords": ["crm", "manual data entry", "spreadsheet", "lost lead", "pipeline sync", "lead tracking"],
            "capability_id": "CAP-005-CRM-AUTOMATION",
            "detected_pain": "Manual CRM entry and unsynchronized customer data",
            "demo_blueprint": "crm_sync_preview",
            "delivery_template": "crm_data_sync_v1"
        }
    ]

    @classmethod
    def match_pain_to_offer(
        cls,
        pain_text: str,
        niche: Optional[str] = None
    ) -> MatchedOfferPlan:
        """
        Determines the optimal productized automation based on detected pain keywords.
        Defaults to High-Conversion Intake (CAP-001) if no specific pain keyword matches.
        """
        pain_lower = (pain_text or "").lower()
        matched_rule = None

        for rule in cls.PAIN_ROUTING:
            if any(kw in pain_lower for kw in rule["keywords"]):
                matched_rule = rule
                break

        if not matched_rule:
            matched_rule = cls.PAIN_ROUTING[1]  # CAP-001 Lead Capture default

        cap = capability_catalog.get_capability(matched_rule["capability_id"])
        if not cap:
            # Fallback
            cap = capability_catalog.get_capability("CAP-001-LEAD-CAPTURE")

        price = max(500.0, cap.target_price_usd if cap else 850.0)
        advance = round(price * 0.40, 2)

        scope = [
            f"Deploy {cap.name if cap else 'Automated Intake'} system",
            f"Configure 24/7 automated pipeline with SLA < 60 seconds",
            f"Integrate with existing {niche.title() if niche else 'business'} digital touchpoints",
            "Multi-channel alert dispatch and delivery verification"
        ]

        return MatchedOfferPlan(
            detected_pain=matched_rule["detected_pain"],
            capability_id=matched_rule["capability_id"],
            capability_name=cap.name if cap else "High-Conversion Intake & Qualification Flow",
            target_price_usd=price,
            advance_deposit_usd=advance,
            turnaround_days=cap.effort_days if hasattr(cap, "effort_days") else 5,
            demo_blueprint_type=matched_rule["demo_blueprint"],
            proposal_scope=scope,
            delivery_template=matched_rule["delivery_template"]
        )


offer_matcher = OfferMatcher()
