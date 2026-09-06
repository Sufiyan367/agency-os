"""Pricing Engine Module for Client Intelligence.

Enforces commercial integrity:
- Hard floor of $500 USD (never quotes under $500)
- Target minimum of $1,000+ USD
- Value-grounded tiering based on business scale and recoverable labor
"""
from typing import Dict, Any, List, Optional
from app.client_intelligence.models import (
    BusinessProfile,
    BusinessSizeEstimate,
    BusinessSegment,
    PricingRecommendation,
    ROIEstimate,
    ServiceMatch,
)
from app.client_intelligence.catalog import SERVICE_CATALOG


class PricingEngine:
    """Calculates client-aligned pricing respecting commercial minimums and value tiers."""

    HARD_FLOOR_USD: float = 500.0
    TARGET_MINIMUM_USD: float = 1000.0

    def recommend_pricing(
        self,
        profile: BusinessProfile,
        size_estimate: BusinessSizeEstimate,
        matched_service: ServiceMatch,
        roi_estimate: Optional[ROIEstimate] = None,
    ) -> PricingRecommendation:
        catalog_item = SERVICE_CATALOG.get(matched_service.service_id)
        
        # Base numbers from catalog
        cat_min = catalog_item.pricing_min_usd if catalog_item else self.HARD_FLOOR_USD
        cat_target = catalog_item.recommended_target_price_usd if catalog_item else self.TARGET_MINIMUM_USD
        cat_max = catalog_item.pricing_max_usd if catalog_item else 2000.0

        # Adjust based on segment
        reasoning: List[str] = []
        if size_estimate.segment == BusinessSegment.MICRO:
            # Micro businesses can receive minimum pricing, but target stays at least $1,000 if catalog allows
            rec_price = max(self.HARD_FLOOR_USD, min(cat_target, 1000.0))
            target_price = max(self.TARGET_MINIMUM_USD, cat_target)
            tier_str = "$500–$1,000 (Micro Tier)"
            reasoning.append("Calibrated for lean solo/micro operator with direct owner oversight.")
        elif size_estimate.segment == BusinessSegment.SMALL:
            rec_price = max(1000.0, cat_target)
            target_price = max(1200.0, cat_target * 1.1)
            tier_str = "$1,000–$1,800 (Small Business Tier)"
            reasoning.append("Calibrated for dedicated small operating crew with 4–10 staff.")
        elif size_estimate.segment == BusinessSegment.SMB:
            rec_price = max(1500.0, cat_target * 1.25)
            target_price = max(1800.0, cat_max * 0.9)
            tier_str = "$1,500–$3,000 (SMB Tier)"
            reasoning.append("Calibrated for multi-crew organization with substantial workflow volume.")
        else:
            # Mid-Market or Enterprise
            rec_price = max(2000.0, cat_max)
            target_price = max(2500.0, cat_max * 1.2)
            tier_str = "$2,000–$4,500+ (Mid-Market/Enterprise Tier)"
            reasoning.append("Calibrated for departmental scaling and multi-stakeholder integration.")

        # Commercial floor safety enforcement
        final_rec = max(self.HARD_FLOOR_USD, round(rec_price, 2))
        final_target = max(self.TARGET_MINIMUM_USD, round(target_price, 2))
        final_floor = self.HARD_FLOOR_USD

        # Calculate payback / value multiple
        multiple = 1.5
        if roi_estimate and roi_estimate.monthly_value_expected_usd and roi_estimate.monthly_value_expected_usd > 0:
            monthly_val = roi_estimate.monthly_value_expected_usd
            payback_months = round(final_rec / monthly_val, 1)
            multiple = round((monthly_val * 12) / final_rec, 1)
            reasoning.append(
                f"Expected monthly labor recovery of ${monthly_val:,.0f} achieves full investment payback in ~{payback_months} months."
            )
        else:
            reasoning.append("Investment bounded against conservative operational delivery effort.")

        reasoning.append(f"Commercial policy enforced: minimum floor ${self.HARD_FLOOR_USD:.0f}, target floor ${self.TARGET_MINIMUM_USD:.0f}.")

        return PricingRecommendation(
            recommended_price_usd=final_rec,
            target_price_usd=final_target,
            minimum_price_usd=final_floor,
            pricing_confidence=0.85,
            value_multiple=multiple,
            tier=tier_str,
            reasoning=reasoning,
        )
