from typing import Dict, Any, List, Optional
from app.database.models import Business, AuditRun, Country, Niche

FEATURE_NAMES = [
    "performance_score",
    "seo_score",
    "a11y_score",
    "ux_conversion_score",
    "overall_health_score",
    "load_time_seconds",
    "critical_findings_count",
    "high_findings_count",
    "total_findings_count",
    "gdp_per_capita",
    "niche_avg_deal_size",
    "business_density_score",
    "digital_weakness_factor",
    "service_fit_score",
    "has_verified_email",
    "has_phone",
    "has_social_presence",
    "contactability_score"
]

class FeatureStore:
    """
    Standardized feature extraction and transformation layer for
    lead scoring models, expected revenue estimation, and conversion analytics.
    """

    @staticmethod
    def feature_names() -> List[str]:
        return list(FEATURE_NAMES)

    def extract_features(
        self,
        business: Business,
        audit: Optional[AuditRun] = None,
        country: Optional[Country] = None,
        niche: Optional[Niche] = None
    ) -> Dict[str, float]:
        """
        Extracts a clean, normalized tabular feature map for an individual prospect.
        Provides robust defaults if audit telemetry or market entities are missing.
        """
        # 1. Audit Metrics
        perf_score = float((getattr(audit, "performance_score", None) if audit else None) or 50.0)
        seo_score = float((getattr(audit, "seo_score", None) if audit else None) or 50.0)
        a11y_score = float((getattr(audit, "a11y_score", None) if audit else None) or 50.0)
        ux_score = float((getattr(audit, "ux_conversion_score", None) if audit else None) or 50.0)
        health_score = float((getattr(audit, "overall_health_score", None) if audit else None) or 50.0)

        # Findings counting
        critical_cnt = 0
        high_cnt = 0
        total_cnt = 0
        load_time = 3.5
        if audit:
            metrics = getattr(audit, "metrics", {}) or {}
            load_time = float(metrics.get("load_time_seconds") or 3.5)
            # Safely inspect findings without triggering unawaited async lazy loads
            findings = audit.__dict__.get("findings", []) if hasattr(audit, "__dict__") else getattr(audit, "findings", [])
            findings = findings or []
            total_cnt = len(findings)
            for f in findings:
                sev = getattr(f, "severity", "MEDIUM")
                if sev == "CRITICAL":
                    critical_cnt += 1
                elif sev == "HIGH":
                    high_cnt += 1

        # 2. Economic & Niche Metrics
        gdp = float((getattr(country, "gdp_per_capita", None) if country else None) or 65000.0)
        niche_deal = float((getattr(niche, "avg_deal_size", None) if niche else None) or 750.0)
        density = float((getattr(country, "business_density_score", None) if country else None) or 50.0)
        weakness = float((getattr(niche, "digital_weakness_factor", None) if niche else None) or 60.0)
        fit = float((getattr(niche, "service_fit_score", None) if niche else None) or 70.0)

        # 3. Contactability
        has_email = 1.0 if getattr(business, "public_email", None) else 0.0
        is_email_verified = 1.0 if getattr(business, "email_status", "unknown") == "verified" else 0.0
        has_phone = 1.0 if getattr(business, "phone", None) else 0.0
        socials = getattr(business, "social_profiles", {}) or {}
        has_social = 1.0 if len(socials) > 0 else 0.0

        if has_email and is_email_verified:
            contactability = 100.0
        elif has_email:
            contactability = 80.0
        elif has_phone:
            contactability = 50.0
        else:
            contactability = 20.0

        features: Dict[str, float] = {
            "performance_score": round(perf_score, 1),
            "seo_score": round(seo_score, 1),
            "a11y_score": round(a11y_score, 1),
            "ux_conversion_score": round(ux_score, 1),
            "overall_health_score": round(health_score, 1),
            "load_time_seconds": round(load_time, 2),
            "critical_findings_count": float(critical_cnt),
            "high_findings_count": float(high_cnt),
            "total_findings_count": float(total_cnt),
            "gdp_per_capita": round(gdp, 1),
            "niche_avg_deal_size": round(niche_deal, 1),
            "business_density_score": round(density, 1),
            "digital_weakness_factor": round(weakness, 1),
            "service_fit_score": round(fit, 1),
            "has_verified_email": 1.0 if is_email_verified else 0.0,
            "has_phone": has_phone,
            "has_social_presence": has_social,
            "contactability_score": round(contactability, 1)
        }
        return features

    def to_vector(self, features: Dict[str, float]) -> List[float]:
        """Converts a feature map into a stable ordered 1D numerical list."""
        return [float(features.get(k, 0.0)) for k in FEATURE_NAMES]

    def normalize(self, features: Dict[str, float]) -> Dict[str, float]:
        """Scales high-magnitude numeric features (GDP, Deal Size, Load Time) to 0.0-1.0 range."""
        norm = dict(features)
        norm["gdp_per_capita"] = min(1.0, max(0.0, norm.get("gdp_per_capita", 0.0) / 100000.0))
        norm["niche_avg_deal_size"] = min(1.0, max(0.0, norm.get("niche_avg_deal_size", 0.0) / 2000.0))
        norm["load_time_seconds"] = min(1.0, max(0.0, norm.get("load_time_seconds", 0.0) / 10.0))
        for key in ["performance_score", "seo_score", "a11y_score", "ux_conversion_score", "overall_health_score", "contactability_score", "business_density_score", "digital_weakness_factor", "service_fit_score"]:
            norm[key] = min(1.0, max(0.0, norm.get(key, 0.0) / 100.0))
        return norm

feature_store = FeatureStore()
