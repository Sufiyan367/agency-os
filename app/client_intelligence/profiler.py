"""Business Profiler Module for Client Intelligence.

Analyzes raw business attributes, website audit data, and tech stack signals
to produce an evidence-grounded BusinessProfile with confidence levels.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.client_intelligence.models import (
    BusinessProfile,
    InferredField,
)


class BusinessProfiler:
    """Profiles a target business from observable data and audit signals."""

    def profile_business(
        self,
        business: Any,
        audit: Optional[Any] = None,
        raw_signals: Optional[Dict[str, Any]] = None,
    ) -> BusinessProfile:
        signals = raw_signals or {}
        try:
            audit_metrics = getattr(audit, "metrics", {}) or {}
        except Exception:
            audit_metrics = {}
        try:
            tech_stack = getattr(audit, "tech_stack", []) or []
        except Exception:
            tech_stack = []
        try:
            findings = getattr(audit, "findings", []) or []
        except Exception:
            findings = []

        # 1. Industry
        niche = getattr(business, "niche", "") or signals.get("niche", "")
        if niche and niche.strip():
            industry_field = InferredField(
                value=niche.strip(),
                confidence=0.85,
                source="business_metadata",
                notes=f"Identified from discovered niche: {niche.strip()}",
            )
        else:
            industry_field = InferredField(
                value="UNKNOWN",
                confidence=0.1,
                source="missing_metadata",
                notes="No niche metadata available",
            )

        # 2. Location
        city = getattr(business, "city", None) or signals.get("city")
        country = getattr(business, "country", None) or signals.get("country")
        address = getattr(business, "address", None) or signals.get("address")
        loc_parts = [p for p in [city, country] if p]
        if loc_parts:
            loc_val = ", ".join(loc_parts)
            loc_field = InferredField(
                value=loc_val,
                confidence=0.8,
                source="business_record",
                notes=f"Location verified from records: {address or loc_val}",
            )
        else:
            loc_field = InferredField(
                value="UNKNOWN",
                confidence=0.1,
                source="missing_metadata",
                notes="No geographic location detected",
            )

        # 3. Services
        services_list = []
        if niche:
            services_list.append(niche)
        if "services" in signals and isinstance(signals["services"], list):
            services_list.extend(signals["services"])
        services_list = list(dict.fromkeys(services_list))
        if services_list:
            services_field = InferredField(
                value=services_list,
                confidence=0.75,
                source="niche_and_signals",
                notes=f"Key service lines identified: {', '.join(services_list[:3])}",
            )
        else:
            services_field = InferredField(
                value=["General Commercial Services"],
                confidence=0.3,
                source="fallback_general",
                notes="Specific service lines not detailed in discovery",
            )

        # 4. Website Quality
        health_score = getattr(audit, "overall_health_score", None)
        if health_score is not None and health_score > 0:
            quality_field = InferredField(
                value=float(health_score),
                confidence=0.9,
                source="audit_engine",
                notes=f"Calculated from automated audit overall health score: {health_score:.1f}/100",
            )
        else:
            quality_field = InferredField(
                value=50.0,
                confidence=0.2,
                source="default_baseline",
                notes="No formal website audit executed yet; using baseline score",
            )

        # 5. Contact Channels
        channels = []
        if getattr(business, "public_email", None):
            channels.append("email")
        if getattr(business, "phone", None):
            channels.append("phone")
        if getattr(business, "contact_page_url", None):
            channels.append("contact_form")
        
        # Check audit findings/tech_stack for live chat, contact forms
        ts_lower = [t.lower() for t in tech_stack]
        if any(c in ts_lower for c in ["intercom", "drift", "crisp", "tawk.to", "livechat", "hubspot-chat"]):
            channels.append("live_chat")
        if any("form" in f.finding.lower() or "contact" in f.finding.lower() for f in findings if hasattr(f, "finding")):
            if "contact_form" not in channels:
                channels.append("contact_form")

        channels = list(dict.fromkeys(channels))
        if not channels:
            channels = ["email_only_fallback"]
            channels_field = InferredField(
                value=channels,
                confidence=0.4,
                source="fallback",
                notes="No active contact channels confirmed on website",
            )
        else:
            channels_field = InferredField(
                value=channels,
                confidence=0.85,
                source="audit_and_records",
                notes=f"Active contact channels: {', '.join(channels)}",
            )

        # 6. Booking Workflow
        booking_workflow = "none"
        booking_confidence = 0.5
        booking_notes = "No automated booking or calendar integration detected."
        
        has_calendar = any(
            cal in ts_lower for cal in ["calendly", "acuity", "cal.com", "appointlet", "youcanbook.me", "setmore"]
        )
        if has_calendar:
            booking_workflow = "calendar_widget"
            booking_confidence = 0.9
            booking_notes = "Automated appointment scheduling widget detected in tech stack."
        elif "contact_form" in channels:
            booking_workflow = "static_form"
            booking_confidence = 0.75
            booking_notes = "Inquiries received via static web form; manual follow-up required."
        elif "email" in channels:
            booking_workflow = "email_only"
            booking_confidence = 0.8
            booking_notes = "Inquiries directed solely to email address with no structured intake."

        booking_field = InferredField(
            value=booking_workflow,
            confidence=booking_confidence,
            source="tech_stack_and_dom",
            notes=booking_notes,
        )

        # 7. Visible Tooling
        tooling_list = list(tech_stack)
        if tooling_list:
            tooling_field = InferredField(
                value=tooling_list,
                confidence=0.85,
                source="tech_stack_detection",
                notes=f"Detected technologies: {', '.join(tooling_list[:5])}",
            )
        else:
            tooling_field = InferredField(
                value=["Standard Web Stack (Undetected)"],
                confidence=0.3,
                source="audit_observation",
                notes="No distinct third-party SaaS or CRM signatures identified",
            )

        # 8. Review Signals
        review_count = signals.get("reviews_count")
        review_rating = signals.get("rating")
        if review_count is not None or review_rating is not None:
            review_val = {"count": review_count or 0, "rating": review_rating or 0.0}
            review_field = InferredField(
                value=review_val,
                confidence=0.8,
                source="public_reputation_signals",
                notes=f"Public feedback: {review_val.get('count')} reviews ({review_val.get('rating')}★)",
            )
        else:
            review_field = InferredField(
                value="UNKNOWN",
                confidence=0.1,
                source="missing_signals",
                notes="No verified review count or rating scraped",
            )

        # 9. Operational Maturity
        # Heuristic scoring based on tech tooling, contact sophistication, and web health
        maturity_score = 0
        if has_calendar:
            maturity_score += 2
        if len(tooling_list) > 3:
            maturity_score += 2
        if "live_chat" in channels:
            maturity_score += 1
        if health_score and health_score > 70:
            maturity_score += 1
        
        if maturity_score >= 4:
            maturity_str = "mature"
        elif maturity_score >= 2:
            maturity_str = "developing"
        else:
            maturity_str = "nascent"

        maturity_field = InferredField(
            value=maturity_str,
            confidence=0.7,
            source="composite_operational_heuristic",
            notes=f"Evaluated as {maturity_str} based on tech stack depth and workflow automation",
        )

        domain = getattr(business, "domain", "") or signals.get("domain", "unknown-domain.com")
        name = getattr(business, "name", "") or signals.get("name", domain)

        return BusinessProfile(
            business_name=name,
            domain=domain,
            industry=industry_field,
            location=loc_field,
            services=services_field,
            website_quality=quality_field,
            contact_channels=channels_field,
            booking_workflow=booking_field,
            visible_tooling=tooling_field,
            review_signals=review_field,
            operational_maturity=maturity_field,
            raw_signals=signals,
            timestamp=datetime.utcnow(),
        )
