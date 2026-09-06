import math
from typing import Dict, Any, Tuple, List
from app.database.models import LeadPriority
from app.core.config import settings

class DeterministicScoringModel:
    """
    Calibrated, explainable deterministic baseline lead scoring model.
    Transforms standardized tabular features into a transparent 0-100 commercial score,
    conversion probability P(Win), priority classification, and human-interpretable rationale.
    """

    def __init__(self):
        self.version_tag = "v1.0.0-deterministic-baseline"
        self.model_name = "lead_scoring_baseline"

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Executes deterministic feature scoring and probability calibration.
        """
        perf = features.get("performance_score", 50.0)
        seo = features.get("seo_score", 50.0)
        a11y = features.get("a11y_score", 50.0)
        ux = features.get("ux_conversion_score", 50.0)
        health = features.get("overall_health_score", 50.0)

        # Deficits (100 - score)
        perf_opp = max(0.0, 100.0 - perf)
        seo_opp = max(0.0, 100.0 - seo)
        a11y_opp = max(0.0, 100.0 - a11y)
        ux_opp = max(0.0, 100.0 - ux)
        weakness_opp = max(0.0, 100.0 - health)

        # Economic Ability-to-Pay (0-100)
        gdp = features.get("gdp_per_capita", 65000.0)
        deal_size = features.get("niche_avg_deal_size", 750.0)
        ability_to_pay = min(100.0, max(0.0, (gdp / 80000.0) * 60.0 + (deal_size / 1500.0) * 40.0))

        # Contactability (0-100)
        contactability = features.get("contactability_score", 50.0)
        contact_multiplier = 0.6 + (contactability / 100.0) * 0.4

        # Weighted composite raw score
        w_weakness = getattr(settings, "WEIGHT_WEBSITE_WEAKNESS", 0.25)
        w_seo = getattr(settings, "WEIGHT_SEO_OPPORTUNITY", 0.15)
        w_a11y = getattr(settings, "WEIGHT_A11Y_OPPORTUNITY", 0.10)
        w_perf = getattr(settings, "WEIGHT_PERFORMANCE_OPPORTUNITY", 0.15)
        w_ux = getattr(settings, "WEIGHT_CONVERSION_OPPORTUNITY", 0.15)
        w_atp = getattr(settings, "WEIGHT_ABILITY_TO_PAY", 0.20)

        raw_score = (
            (weakness_opp * w_weakness) +
            (seo_opp * w_seo) +
            (a11y_opp * w_a11y) +
            (perf_opp * w_perf) +
            (ux_opp * w_ux) +
            (ability_to_pay * w_atp)
        )

        final_score = round(min(100.0, max(0.0, raw_score * contact_multiplier)), 1)

        # Priority Categorization
        if final_score >= 85.0:
            priority = LeadPriority.A.value
        elif final_score >= 70.0:
            priority = LeadPriority.B.value
        elif final_score >= 55.0:
            priority = LeadPriority.C.value
        else:
            priority = LeadPriority.LOW.value

        # Sigmoid Calibration for Win Probability P(Win)
        # Centers around score=65 (50% prob at 65), slope scale=14
        logit = (final_score - 65.0) / 14.0
        prob_win = round(1.0 / (1.0 + math.exp(-logit)), 3)
        prob_win = min(0.95, max(0.02, prob_win))

        # Explainable Rationale & Drivers
        drivers: List[str] = []
        if ux_opp >= 50.0:
            drivers.append(f"High conversion friction ({ux_opp:.0f}% deficit)")
        if seo_opp >= 50.0:
            drivers.append(f"Significant SEO upside ({seo_opp:.0f}% deficit)")
        if perf_opp >= 50.0:
            drivers.append(f"Core Web Vitals deficit ({perf_opp:.0f}% deficit)")
        if ability_to_pay >= 70.0:
            drivers.append(f"High buying power index ({ability_to_pay:.0f}/100)")
        if contactability >= 80.0:
            drivers.append("Direct verified business email available")

        breakdown = {
            "website_weakness_opp": round(weakness_opp, 1),
            "seo_opp": round(seo_opp, 1),
            "a11y_opp": round(a11y_opp, 1),
            "performance_opp": round(perf_opp, 1),
            "ux_conversion_opp": round(ux_opp, 1),
            "ability_to_pay": round(ability_to_pay, 1),
            "contactability": round(contactability, 1),
            "contact_multiplier": round(contact_multiplier, 2)
        }

        rationale = (
            f"Baseline Model Score: {final_score}/100 [Priority {priority}, P(Win)={prob_win*100:.1f}%]. "
            f"Key justification: {'; '.join(drivers) if drivers else 'Balanced standard digital opportunity'}."
        )

        return {
            "score": final_score,
            "priority": priority,
            "probability_win": prob_win,
            "breakdown": breakdown,
            "drivers": drivers,
            "rationale": rationale,
            "is_baseline": True,
            "model_name": self.model_name,
            "version_tag": self.version_tag
        }

deterministic_scoring_model = DeterministicScoringModel()
