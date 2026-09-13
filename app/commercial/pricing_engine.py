"""Deterministic Commercial Pricing Engine.

Calculates standardized, policy-driven commercial pricing for Agency OS deliverables.
Guarantees:
- Transparent milestone breakdown: 40% advance deposit, 60% handover balance.
- Commercial floor protection: Never quotes below settings.COMMERCIAL_FLOOR_USD ($500.00).
- Transparent itemization: Base price, complexity addons, milestones.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.core.config import settings


class PricingBreakdown(BaseModel):
    industry: str
    base_price_usd: float
    complexity_addons: List[Dict[str, Any]] = Field(default_factory=list)
    total_addons_usd: float = 0.0
    subtotal_usd: float
    discount_usd: float = 0.0
    total_price_usd: float
    advance_deposit_usd: float  # 40%
    balance_due_usd: float       # 60%
    payment_milestones: List[Dict[str, Any]] = Field(default_factory=list)


class PricingEngine:
    """Calculates deterministic pricing without arbitrary or hallucinated costs."""

    BASE_PRICING_BY_INDUSTRY: Dict[str, float] = {
        "automotive": 1200.0,
        "dental": 1350.0,
        "roofing": 1150.0,
        "hvac": 1250.0,
        "general": 1000.0,
    }

    ADDON_CATALOG: Dict[str, Dict[str, Any]] = {
        "sms_notifications": {
            "title": "Instant SMS Lead Alerts & Customer Confirmations",
            "price_usd": 100.0,
            "category": "COMMUNICATION"
        },
        "calendar_sync": {
            "title": "Two-Way Calendar Real-Time Lock (Google / Outlook)",
            "price_usd": 150.0,
            "category": "INTEGRATION"
        },
        "multilingual_concierge": {
            "title": "Multi-Lingual AI Intake Concierge (EN / ES / AR)",
            "price_usd": 100.0,
            "category": "AI_CAPABILITY"
        },
        "after_hours_triage": {
            "title": "24/7 After-Hours Emergency Routing & Escalation",
            "price_usd": 120.0,
            "category": "OPERATIONS"
        }
    }

    @classmethod
    def calculate_pricing(
        cls,
        industry: str,
        selected_addons: Optional[List[str]] = None,
        discount_usd: float = 0.0,
        custom_base_price: Optional[float] = None
    ) -> PricingBreakdown:
        ind_key = (industry or "general").lower().strip()
        base_price = custom_base_price or cls.BASE_PRICING_BY_INDUSTRY.get(ind_key, 1000.0)

        floor = float(getattr(settings, "COMMERCIAL_FLOOR_USD", 500.0))
        if base_price < floor:
            base_price = floor

        addons_applied: List[Dict[str, Any]] = []
        addons_total = 0.0

        if selected_addons:
            for addon_key in selected_addons:
                if addon_key in cls.ADDON_CATALOG:
                    item = cls.ADDON_CATALOG[addon_key]
                    cost = item["price_usd"]
                    addons_applied.append({
                        "key": addon_key,
                        "title": item["title"],
                        "category": item["category"],
                        "price_usd": cost
                    })
                    addons_total += cost

        subtotal = base_price + addons_total
        disc = max(0.0, min(discount_usd, subtotal * 0.2)) # Max 20% discount policy
        total = max(floor, subtotal - disc)

        # 40% advance milestone deposit, 60% remaining balance
        advance_deposit = round(total * 0.40, 2)
        balance_due = round(total - advance_deposit, 2)

        milestones = [
            {
                "milestone": "MILESTONE_1_DEPOSIT",
                "name": "Initial Project Mobilization & Staging Setup",
                "percentage": 40,
                "amount_usd": advance_deposit,
                "trigger": "Commercial proposal authorization",
                "terms": "Due prior to production environment provisioning"
            },
            {
                "milestone": "MILESTONE_2_HANDOVER",
                "name": "Verified Production Handover & QA Sign-Off",
                "percentage": 60,
                "amount_usd": balance_due,
                "trigger": "Live production verification and credential delivery",
                "terms": "Due strictly upon verified production staging handover"
            }
        ]

        return PricingBreakdown(
            industry=industry,
            base_price_usd=base_price,
            complexity_addons=addons_applied,
            total_addons_usd=addons_total,
            subtotal_usd=subtotal,
            discount_usd=disc,
            total_price_usd=total,
            advance_deposit_usd=advance_deposit,
            balance_due_usd=balance_due,
            payment_milestones=milestones
        )
