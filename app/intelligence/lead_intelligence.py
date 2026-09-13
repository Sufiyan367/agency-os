"""
Lead Intelligence Engine — Mega Prompt 8.
Evaluates 11 empirical dimensions for B2B prospects:
Business Fit, Service Fit, Commercial Fit, Buying Signal, Website Opportunity,
Contactability, Geographic Priority, Industry Priority, Competitive Signal, Recency, Evidence Quality.
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import (
    IntelligenceSignal, SignalType, EpistemicStatus,
    ConfidenceBand, ActionType
)
from app.intelligence.signals import signal_registry
from app.intelligence.features import feature_store
from app.intelligence.cache import intelligence_cache

class LeadIntelligenceEngine:
    """
    Evaluates business opportunities across 11 evidence-grounded dimensions.
    """

    VERSION = "v2.0.0-lead-intelligence"

    @classmethod
    async def evaluate_lead(
        cls,
        session: AsyncSession,
        business_id: int
    ) -> Dict[str, Any]:
        """
        Executes full multi-dimensional evaluation for a business.
        """
        # 1. Feature Extraction
        features = await feature_store.extract_business_features(session, business_id)

        # Check Cache
        cache_key = intelligence_cache.generate_cache_key("business", business_id, "lead_intel", features)
        cached = intelligence_cache.get(cache_key)
        if cached:
            return cached

        # 2. Dimensions Evaluation (Each 0 - 100)

        # (a) Website Opportunity (Deficits in perf, UX, SEO, a11y)
        perf_opp = max(0.0, 100.0 - features["performance_score"])
        ux_opp = max(0.0, 100.0 - features["ux_conversion_score"])
        seo_opp = max(0.0, 100.0 - features["seo_score"])
        a11y_opp = max(0.0, 100.0 - features["a11y_score"])
        website_opp = min(100.0, (perf_opp * 0.35) + (ux_opp * 0.35) + (seo_opp * 0.15) + (a11y_opp * 0.15))

        # (b) Business Fit (Has working site, registered entity, valid domain)
        business_fit = 85.0 if features["has_website"] else 20.0

        # (c) Contactability (Verified email, phone, reachable decision maker)
        contactability = features["contactability_score"]

        # (d) Commercial Fit (Ability to pay based on GDP per capita & Niche deal size)
        gdp_factor = min(1.0, features["gdp_per_capita"] / 80000.0)
        deal_factor = min(1.0, features["niche_avg_deal_size"] / 1500.0)
        commercial_fit = round((gdp_factor * 60.0) + (deal_factor * 40.0), 1)

        # (e) Buying Signal (Inbound inquiries, pricing questions, positive replies)
        buying_signals = 0.0
        if features["inbound_replies_count"] > 0: buying_signals += 40.0
        if features["positive_replies_count"] > 0: buying_signals += 50.0
        buying_signal_score = min(100.0, buying_signals if buying_signals > 0 else 25.0)

        # (f) Geographic Priority (GCC Phase 1 priorities: SA, AE, QA, etc.)
        geo_priority_map = {"SA": 95.0, "AE": 92.0, "QA": 90.0, "KW": 85.0, "BH": 80.0, "OM": 78.0, "US": 85.0}
        geo_priority = geo_priority_map.get(features["country_code"], 70.0)

        # (g) Industry Priority (Automotive, Dental, Roofing, HVAC)
        ind_priority_map = {"Automotive": 95.0, "HVAC": 92.0, "Roofing": 90.0, "Dental": 94.0}
        industry_priority = ind_priority_map.get(features["industry"], 75.0)

        # (h) Competitive Signal
        competitive_signal = 65.0  # Baseline: unautomated local competitor baseline

        # (i) Recency (Freshly audited within 30 days)
        recency = max(10.0, 100.0 - (features["recency_days"] * 2.0))

        # (j) Evidence Quality (Verified screenshots, HTTP 200, contact proofs)
        ev_count = features["verified_evidence_count"]
        evidence_quality = min(100.0, 40.0 + (ev_count * 15.0))

        # (k) Service Fit
        if ux_opp > 60.0:
            rec_service = "High-Converting Website Turnaround"
            service_fit = 90.0
        elif features["industry"] == "Automotive":
            rec_service = "AI Missed-Call & After-Hours Service Booking"
            service_fit = 92.0
        elif features["industry"] == "HVAC":
            rec_service = "AI Emergency Dispatch & Lead Qualifier"
            service_fit = 88.0
        elif features["industry"] == "Dental":
            rec_service = "AI Patient Appointment & Insurance Inquiry Desk"
            service_fit = 91.0
        elif features["industry"] == "Roofing":
            rec_service = "AI Storm Damage Lead Intake & Estimation Scheduling"
            service_fit = 89.0
        else:
            rec_service = "Core Web Vitals & Load Speed Acceleration"
            service_fit = 75.0

        # Weighted Composite Score (0 - 100)
        weights = {
            "website_opp": 0.25,
            "commercial_fit": 0.20,
            "business_fit": 0.10,
            "contactability": 0.15,
            "service_fit": 0.10,
            "buying_signal": 0.05,
            "geo_priority": 0.05,
            "industry_priority": 0.05,
            "evidence_quality": 0.05,
        }

        overall_score = round(
            (website_opp * weights["website_opp"]) +
            (commercial_fit * weights["commercial_fit"]) +
            (business_fit * weights["business_fit"]) +
            (contactability * weights["contactability"]) +
            (service_fit * weights["service_fit"]) +
            (buying_signal_score * weights["buying_signal"]) +
            (geo_priority * weights["geo_priority"]) +
            (industry_priority * weights["industry_priority"]) +
            (evidence_quality * weights["evidence_quality"]),
            1
        )

        # Suppression check
        if features["is_opted_out"]:
            overall_score = 0.0

        # Recommended Channel
        rec_channel = "EMAIL" if features["has_email"] else "WHATSAPP" if features["has_phone"] else "WEB"

        # Recommended Next Action
        if features["is_opted_out"]:
            rec_action = ActionType.NO_ACTION.value
        elif features["positive_replies_count"] > 0:
            rec_action = ActionType.SEND_PROPOSAL.value
        elif features["inbound_replies_count"] > 0:
            rec_action = ActionType.ANSWER_QUESTION.value
        elif contactability < 50.0:
            rec_action = ActionType.RESEARCH.value
        elif overall_score >= 70.0:
            rec_action = ActionType.OUTREACH.value
        else:
            rec_action = ActionType.WAIT.value

        reasons = [
            f"Technical opportunity: {website_opp:.0f}/100 based on Lighthouse & UX audits.",
            f"Commercial viability: {commercial_fit:.0f}/100 in {features['country_code']} ({features['industry']}).",
            f"Contact readiness: {contactability:.0f}/100 with verified evidence ({ev_count} items)."
        ]

        result = {
            "business_id": business_id,
            "overall_score": overall_score,
            "components": {
                "website_opportunity": website_opp,
                "commercial_fit": commercial_fit,
                "business_fit": business_fit,
                "contactability": contactability,
                "service_fit": service_fit,
                "buying_signal": buying_signal_score,
                "geographic_priority": geo_priority,
                "industry_priority": industry_priority,
                "recency": recency,
                "evidence_quality": evidence_quality,
            },
            "confidence": 0.85 if ev_count > 0 else 0.65,
            "confidence_band": "HIGH" if ev_count > 1 else "MEDIUM",
            "recommended_service": rec_service,
            "recommended_channel": rec_channel,
            "recommended_next_action": rec_action,
            "reasons": reasons,
            "version": cls.VERSION
        }

        # Persist canonical signal
        signal = signal_registry.create_signal(
            entity_type="business",
            entity_id=business_id,
            signal_type=SignalType.LEAD_FIT,
            epistemic_status=EpistemicStatus.INFERENCE,
            signal_value=overall_score,
            confidence=result["confidence"],
            source="lead_intelligence_engine",
            evidence=[{"reasons": reasons, "service": rec_service}]
        )
        await signal_registry.persist_signal(session, signal)

        # Cache result
        intelligence_cache.set(cache_key, result, ttl_seconds=1800)
        return result


lead_intelligence_engine = LeadIntelligenceEngine()
