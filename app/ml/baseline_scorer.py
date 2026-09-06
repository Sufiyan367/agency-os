import math
from typing import Dict, Any, List, Optional
from app.database.models import LeadPriority
from app.ml.feature_store import FEATURE_NAMES
from app.core.config import settings

class BaselineScorer:
    """
    Deterministic, fully explainable prospect scoring engine.
    Transforms the 18 standardized tabular features from FeatureStore into
    four explicit sub-scores and a weighted total composite score.
    """

    VERSION_TAG = "v1.0.0-baseline-scorer"

    DEFAULT_WEIGHTS = {
        "quality": 0.35,
        "conversion": 0.25,
        "commercial_fit": 0.20,
        "contactability": 0.20
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        # Normalize weights to sum to 1.0
        total_w = sum(self.weights.values())
        if total_w > 0:
            self.weights = {k: v / total_w for k, v in self.weights.items()}

    def score_quality(self, features: Dict[str, float]) -> float:
        """
        Calculates diagnostic deficit / quality score (0-100).
        Higher deficit represents greater upside opportunity for web remediation.
        """
        perf = features.get("performance_score", 50.0)
        seo = features.get("seo_score", 50.0)
        a11y = features.get("a11y_score", 50.0)
        ux = features.get("ux_conversion_score", 50.0)
        health = features.get("overall_health_score", 50.0)
        load_time = features.get("load_time_seconds", 3.5)
        crit_findings = features.get("critical_findings_count", 0.0)

        # Inverted deficit scores (100 - current_score)
        perf_opp = max(0.0, 100.0 - perf)
        seo_opp = max(0.0, 100.0 - seo)
        a11y_opp = max(0.0, 100.0 - a11y)
        ux_opp = max(0.0, 100.0 - ux)
        health_opp = max(0.0, 100.0 - health)
        
        # Load time deficit (over 2.5s is poor)
        load_opp = min(100.0, max(0.0, (load_time - 2.0) * 20.0))
        # Finding severity boost
        finding_boost = min(15.0, crit_findings * 5.0)

        raw_quality = (
            (health_opp * 0.25) +
            (ux_opp * 0.25) +
            (perf_opp * 0.20) +
            (seo_opp * 0.15) +
            (a11y_opp * 0.05) +
            (load_opp * 0.10) +
            finding_boost
        )
        return round(min(100.0, max(0.0, raw_quality)), 1)

    def score_conversion(self, features: Dict[str, float]) -> float:
        """
        Calculates prospect conversion likelihood (0-100) based on
        urgency, digital weakness factor, and local market density.
        """
        weakness = features.get("digital_weakness_factor", 60.0)
        density = features.get("business_density_score", 50.0)
        crit_cnt = features.get("critical_findings_count", 0.0)
        high_cnt = features.get("high_findings_count", 0.0)

        urgency = min(100.0, (crit_cnt * 25.0) + (high_cnt * 10.0))
        
        conv = (
            (weakness * 0.45) +
            (urgency * 0.35) +
            (density * 0.20)
        )
        return round(min(100.0, max(0.0, conv)), 1)

    def score_commercial_fit(self, features: Dict[str, float]) -> float:
        """
        Calculates economic ability-to-pay and service fit (0-100).
        """
        gdp = features.get("gdp_per_capita", 65000.0)
        deal_size = features.get("niche_avg_deal_size", 750.0)
        fit = features.get("service_fit_score", 70.0)

        # Ability to pay normalized against $80k GDP and $1500 deal size
        atp = min(100.0, max(0.0, (gdp / 80000.0) * 55.0 + (deal_size / 1500.0) * 45.0))
        
        commercial = (atp * 0.55) + (fit * 0.45)
        return round(min(100.0, max(0.0, commercial)), 1)

    def score_contactability(self, features: Dict[str, float]) -> float:
        """
        Calculates contact accessibility score (0-100).
        """
        has_verified = features.get("has_verified_email", 0.0)
        has_phone = features.get("has_phone", 0.0)
        has_social = features.get("has_social_presence", 0.0)
        c_score = features.get("contactability_score", 50.0)

        if has_verified > 0.5:
            score = 100.0
        elif c_score >= 80.0:
            score = 85.0
        elif has_phone > 0.5:
            score = 65.0
        elif has_social > 0.5:
            score = 45.0
        else:
            score = max(15.0, c_score * 0.4)
            
        return round(min(100.0, max(0.0, score)), 1)

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Calculates comprehensive deterministic scores, calibrated win probability,
        and human-interpretable rationale.
        """
        q_score = self.score_quality(features)
        conv_score = self.score_conversion(features)
        fit_score = self.score_commercial_fit(features)
        contact_score = self.score_contactability(features)

        # Weighted total score
        w_q = self.weights["quality"]
        w_c = self.weights["conversion"]
        w_f = self.weights["commercial_fit"]
        w_k = self.weights["contactability"]

        raw_total = (
            (q_score * w_q) +
            (conv_score * w_c) +
            (fit_score * w_f) +
            (contact_score * w_k)
        )
        total_score = round(min(100.0, max(0.0, raw_total)), 1)

        # Priority tier
        if total_score >= 85.0:
            priority = LeadPriority.A.value
        elif total_score >= 70.0:
            priority = LeadPriority.B.value
        elif total_score >= 55.0:
            priority = LeadPriority.C.value
        else:
            priority = LeadPriority.LOW.value

        # Sigmoid calibration centered around 62.0 with slope 13.0
        logit = (total_score - 62.0) / 13.0
        p_win = round(1.0 / (1.0 + math.exp(-logit)), 3)
        p_win = min(0.95, max(0.02, p_win))

        # Explainability & Drivers
        drivers: List[str] = []
        if q_score >= 75.0:
            drivers.append(f"Significant website optimization upside (Quality: {q_score}/100)")
        if conv_score >= 70.0:
            drivers.append(f"Strong conversion urgency and market need ({conv_score}/100)")
        if fit_score >= 75.0:
            drivers.append(f"High purchasing power and agency service fit ({fit_score}/100)")
        if contact_score >= 85.0:
            drivers.append("Direct verified contact channel available")
        if features.get("critical_findings_count", 0.0) >= 1.0:
            drivers.append(f"{int(features.get('critical_findings_count', 0.0))} critical audit finding(s) detected")

        if not drivers:
            drivers.append("Moderate composite scoring across standard baseline metrics")

        rationale = (
            f"Baseline score {total_score}/100 ({priority}) computed with "
            f"Quality={q_score}, Conversion={conv_score}, CommercialFit={fit_score}, Contactability={contact_score}. "
            f"Estimated conversion probability: {p_win * 100:.1f}%."
        )

        return {
            "quality_score": q_score,
            "conversion_score": conv_score,
            "commercial_fit_score": fit_score,
            "contactability_score": contact_score,
            "total_score": total_score,
            "priority": priority,
            "probability_of_conversion": p_win,
            "is_baseline": True,
            "model_version": self.VERSION_TAG,
            "explainability": {
                "drivers": drivers,
                "formula": f"total = {w_q:.2f}*quality + {w_c:.2f}*conversion + {w_f:.2f}*fit + {w_k:.2f}*contact",
                "weights": self.weights,
                "rationale": rationale
            }
        }

baseline_scorer = BaselineScorer()
