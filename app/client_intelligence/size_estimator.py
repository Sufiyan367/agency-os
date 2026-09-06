"""Business Size Estimator Module for Client Intelligence.

Infers business scale and operational tier from observable signals,
website footprint, tech stack depth, and team indicators.
"""
from typing import Dict, Any, List, Optional
from app.client_intelligence.models import (
    BusinessProfile,
    BusinessSizeEstimate,
    BusinessSegment,
)


class BusinessSizeEstimator:
    """Estimates the organizational size and operating scale of a business."""

    def estimate_size(
        self,
        profile: BusinessProfile,
        business: Any = None,
        raw_signals: Optional[Dict[str, Any]] = None,
    ) -> BusinessSizeEstimate:
        signals_detected: List[str] = []
        raw = raw_signals or profile.raw_signals or {}
        
        # Extract observable features
        tooling = [t.lower() for t in (profile.visible_tooling.value if isinstance(profile.visible_tooling.value, list) else [])]
        reviews_info = profile.review_signals.value if isinstance(profile.review_signals.value, dict) else {}
        review_count = reviews_info.get("count", 0) or raw.get("reviews_count", 0)
        channels = profile.contact_channels.value if isinstance(profile.contact_channels.value, list) else []
        maturity = str(profile.operational_maturity.value).lower()
        
        # Check explicit employee count signal if present (e.g. from LinkedIn or directory data)
        explicit_employees = raw.get("employee_count") or raw.get("team_size")
        if explicit_employees is not None:
            try:
                emp_num = int(explicit_employees)
                if emp_num <= 3:
                    signals_detected.append(f"Explicit team size data indicates {emp_num} staff (Micro).")
                    return BusinessSizeEstimate(
                        segment=BusinessSegment.MICRO,
                        confidence=0.9,
                        signals=signals_detected,
                        estimated_employee_range="1–3",
                    )
                elif emp_num <= 10:
                    signals_detected.append(f"Explicit team size data indicates {emp_num} staff (Small).")
                    return BusinessSizeEstimate(
                        segment=BusinessSegment.SMALL,
                        confidence=0.9,
                        signals=signals_detected,
                        estimated_employee_range="4–10",
                    )
                elif emp_num <= 50:
                    signals_detected.append(f"Explicit team size data indicates {emp_num} staff (SMB).")
                    return BusinessSizeEstimate(
                        segment=BusinessSegment.SMB,
                        confidence=0.9,
                        signals=signals_detected,
                        estimated_employee_range="11–50",
                    )
                elif emp_num <= 250:
                    signals_detected.append(f"Explicit team size data indicates {emp_num} staff (Mid-Market).")
                    return BusinessSizeEstimate(
                        segment=BusinessSegment.MID_MARKET,
                        confidence=0.9,
                        signals=signals_detected,
                        estimated_employee_range="51–250",
                    )
                else:
                    signals_detected.append(f"Explicit team size data indicates {emp_num} staff (Enterprise).")
                    return BusinessSizeEstimate(
                        segment=BusinessSegment.ENTERPRISE,
                        confidence=0.9,
                        signals=signals_detected,
                        estimated_employee_range="250+",
                    )
            except (ValueError, TypeError):
                pass

        # Heuristic scoring based on tech tooling and public signals
        enterprise_tech = {"salesforce", "marketo", "workday", "sap", "oracle", "adobe-experience-manager", "demandbase"}
        mid_market_tech = {"hubspot", "segment", "intercom", "greenhouse", "lever", "breezy", "chargebee", "stripe-billing"}
        smb_tech = {"calendly", "acuity", "activecampaign", "mailchimp", "klaviyo", "zoho", "zapier", "make"}
        
        has_enterprise_tech = any(t in enterprise_tech for t in tooling)
        has_mid_market_tech = any(t in mid_market_tech for t in tooling)
        has_smb_tech = any(t in smb_tech for t in tooling)

        if has_enterprise_tech:
            signals_detected.append(f"Enterprise tooling identified in stack: {[t for t in tooling if t in enterprise_tech]}.")
            return BusinessSizeEstimate(
                segment=BusinessSegment.ENTERPRISE,
                confidence=0.85,
                signals=signals_detected,
                estimated_employee_range="250+",
            )

        if has_mid_market_tech:
            signals_detected.append(f"Mid-market departmental software identified: {[t for t in tooling if t in mid_market_tech]}.")
            if review_count > 250 or raw.get("multiple_locations"):
                signals_detected.append("High review volume and/or multi-location footprint detected.")
                return BusinessSizeEstimate(
                    segment=BusinessSegment.MID_MARKET,
                    confidence=0.8,
                    signals=signals_detected,
                    estimated_employee_range="51–250",
                )
            return BusinessSizeEstimate(
                segment=BusinessSegment.SMB,
                confidence=0.75,
                signals=signals_detected,
                estimated_employee_range="15–50",
            )

        # Evaluate SMB vs Small vs Micro
        if review_count > 100 or has_smb_tech or (len(channels) >= 3 and maturity in ("developing", "mature")):
            if review_count > 100:
                signals_detected.append(f"Substantial review volume ({review_count} reviews) indicates sustained operating history.")
            if has_smb_tech:
                signals_detected.append(f"SaaS tooling in place: {[t for t in tooling if t in smb_tech]}.")
            signals_detected.append(f"Multi-channel intake ({', '.join(channels)}) and operational maturity '{maturity}'.")
            return BusinessSizeEstimate(
                segment=BusinessSegment.SMB,
                confidence=0.75,
                signals=signals_detected,
                estimated_employee_range="11–50",
            )

        if review_count > 15 or len(channels) >= 2 or maturity == "developing":
            if review_count > 15:
                signals_detected.append(f"Moderate review volume ({review_count} reviews) suggests small dedicated crew.")
            signals_detected.append(f"Standard local business presence with contact channels: {', '.join(channels)}.")
            return BusinessSizeEstimate(
                segment=BusinessSegment.SMALL,
                confidence=0.75,
                signals=signals_detected,
                estimated_employee_range="4–10",
            )

        # Fallback to MICRO
        signals_detected.append("Minimal tech footprint, low or unverified review count, single-operator profile.")
        return BusinessSizeEstimate(
            segment=BusinessSegment.MICRO,
            confidence=0.7,
            signals=signals_detected,
            estimated_employee_range="1–3",
        )
