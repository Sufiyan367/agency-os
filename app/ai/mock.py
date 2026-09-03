from typing import Dict, Any, Optional, List
from app.ai.base import BaseAIProvider
from app.ai.schemas import LeadQualificationResult, OutreachDraftResult, ReplyClassificationResult

class MockAIProvider(BaseAIProvider):
    """
    Deterministic zero-cost mock AI provider for local testing and offline verification.
    Computes realistic qualification and outreach outputs directly from business & audit signals.
    """

    @property
    def provider_name(self) -> str:
        return "mock"

    async def qualify_lead(
        self,
        business_info: Dict[str, Any],
        audit_info: Dict[str, Any],
        reviews_data: Optional[Dict[str, Any]] = None
    ) -> LeadQualificationResult:
        findings = audit_info.get("findings", [])
        overall_health = audit_info.get("overall_health_score", 50.0)
        perf_score = audit_info.get("performance_score", 50.0)
        seo_score = audit_info.get("seo_score", 50.0)
        mobile = audit_info.get("mobile_responsive", True)

        pain_points = []
        if perf_score < 60:
            pain_points.append(f"Slow mobile page load speed (Score: {perf_score:.0f}/100)")
        if seo_score < 60:
            pain_points.append(f"Missing local SEO metadata & title optimization (Score: {seo_score:.0f}/100)")
        if not mobile:
            pain_points.append("Website fails responsive mobile viewport inspection")
        if not pain_points:
            pain_points.append("General digital conversion funnel optimization required")

        # Opportunity scoring logic (Lower website health = Higher opportunity to help)
        digital_deficit = 100.0 - overall_health
        lead_score = round(max(20.0, min(95.0, digital_deficit * 0.7 + 30.0)), 1)

        if lead_score >= 80.0:
            qualification = "HOT"
            intent_level = "HIGH"
            rec_service = "Complete System Health & Diagnostic Audit"
            needs_human = False
            reasoning = (
                f"High-priority local prospect with severe digital deficiencies ({len(pain_points)} critical issues). "
                f"Low health score ({overall_health:.0f}/100) indicates acute customer drop-off."
            )
        elif lead_score >= 60.0:
            qualification = "WARM"
            intent_level = "MEDIUM"
            rec_service = "Seasonal Precision Performance Tune-Up"
            needs_human = False
            reasoning = (
                f"Viable target with moderate website bottlenecks ({perf_score:.0f}/100 speed). "
                "Strong candidate for standard lead recovery sequence."
            )
        elif lead_score >= 40.0:
            qualification = "COLD"
            intent_level = "LOW"
            rec_service = "Smart Climate & Clean Air Duct Sealing Package"
            needs_human = False
            reasoning = "Website health is already acceptable. Low urgency for immediate digital intervention."
        else:
            qualification = "INVALID"
            intent_level = "NONE"
            rec_service = "N/A"
            needs_human = False
            reasoning = "Business website inactive or non-commercial domain."

        return LeadQualificationResult(
            lead_score=lead_score,
            qualification=qualification,
            intent_level=intent_level,
            pain_points=pain_points,
            recommended_service=rec_service,
            reasoning=reasoning,
            confidence=0.92,
            needs_human=needs_human
        )

    async def generate_outreach(
        self,
        business_info: Dict[str, Any],
        audit_info: Dict[str, Any],
        qualification: LeadQualificationResult,
        channel: str = "EMAIL"
    ) -> OutreachDraftResult:
        b_name = business_info.get("name", "Business Owner")
        b_niche = business_info.get("niche", "Local Services")
        primary_issue = qualification.pain_points[0] if qualification.pain_points else "site speed"
        booking_url = business_info.get("booking_url", "https://cal.com/apexcomfort/diagnostic")

        subject = f"Quick technical question regarding {b_name}'s website speed"
        body = (
            f"Hi {b_name} team,\n\n"
            f"While reviewing top-rated {b_niche} providers in your area, I noticed your site is currently flagged for: "
            f"{primary_issue}.\n\n"
            f"For local service searches, Google deprioritizes slow mobile pages, directly impacting calls from homeowners.\n\n"
            f"We put together a short 1-page diagnostic breakdown with exact technical fixes (no cost or pitch).\n\n"
            f"Would it be helpful if I sent that over, or would you prefer a quick 10-minute walkthrough?\n"
            f"Booking calendar: {booking_url}\n\n"
            f"Best regards,\n"
            f"Elena Vance | Growth & Diagnostic Lead"
        )

        return OutreachDraftResult(
            subject=subject,
            body=body,
            channel=channel,
            icebreaker=f"Noticed {primary_issue} on the {business_info.get('domain', 'website')}.",
            cta_url=booking_url
        )

    async def classify_reply(
        self,
        incoming_message: str,
        history: List[Dict[str, str]],
        business_info: Dict[str, Any]
    ) -> ReplyClassificationResult:
        text = incoming_message.lower()

        # Stop words
        if any(w in text for w in ["unsubscribe", "remove me", "stop", "opt out", "do not contact"]):
            return ReplyClassificationResult(
                classification="UNSUBSCRIBE",
                intent_level="NONE",
                confidence=0.99,
                summary="Lead requested unsubscribe / opt-out.",
                suggested_action="STOP_FOLLOWUP",
                needs_human=False
            )
        # Booking / Interested
        elif any(w in text for w in ["book", "calendar", "schedule", "call me", "free tomorrow", "interested", "send the report", "send it"]):
            return ReplyClassificationResult(
                classification="INTERESTED",
                intent_level="HIGH",
                confidence=0.95,
                summary="Lead expressed affirmative interest in call or report.",
                suggested_action="BOOK_CALL",
                needs_human=True
            )
        # Pricing request
        elif any(w in text for w in ["how much", "pricing", "cost", "quote", "rate"]):
            return ReplyClassificationResult(
                classification="PRICE_REQUEST",
                intent_level="HIGH",
                confidence=0.90,
                summary="Lead inquired about pricing.",
                suggested_action="SEND_PRICING",
                needs_human=True
            )
        # Not interested
        elif any(w in text for w in ["not interested", "no thanks", "busy", "already have someone"]):
            return ReplyClassificationResult(
                classification="NOT_INTERESTED",
                intent_level="LOW",
                confidence=0.95,
                summary="Lead declined service.",
                suggested_action="STOP_FOLLOWUP",
                needs_human=False
            )
        # Unknown / complex question
        else:
            return ReplyClassificationResult(
                classification="QUESTION",
                intent_level="MEDIUM",
                confidence=0.80,
                summary="Customer asked a specific question requiring human review.",
                suggested_action="HUMAN_TAKEOVER",
                needs_human=True
            )
