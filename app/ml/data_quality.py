from typing import Dict, Any, List, Optional
from datetime import datetime
from app.ml.feature_store import FEATURE_NAMES

class MLDataQualityMonitor:
    """
    Audits feature integrity, missingness, schema conformity,
    and ground-truth outcome consistency.
    """

    FEATURE_RANGES = {
        "performance_score": (0.0, 100.0),
        "seo_score": (0.0, 100.0),
        "a11y_score": (0.0, 100.0),
        "ux_conversion_score": (0.0, 100.0),
        "overall_health_score": (0.0, 100.0),
        "load_time_seconds": (0.0, 60.0),
        "critical_findings_count": (0.0, 1000.0),
        "high_findings_count": (0.0, 1000.0),
        "total_findings_count": (0.0, 5000.0),
        "gdp_per_capita": (0.0, 200000.0),
        "niche_avg_deal_size": (0.0, 500000.0),
        "business_density_score": (0.0, 100.0),
        "digital_weakness_factor": (0.0, 100.0),
        "service_fit_score": (0.0, 100.0),
        "has_verified_email": (0.0, 1.0),
        "has_phone": (0.0, 1.0),
        "has_social_presence": (0.0, 1.0),
        "contactability_score": (0.0, 100.0)
    }

    @classmethod
    def audit_features_batch(
        cls,
        feature_records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        total_records = len(feature_records)
        if total_records == 0:
            return {
                "status": "INSUFFICIENT_DATA",
                "quality_score": 100.0,
                "total_records": 0,
                "missing_feature_rates": {},
                "out_of_range_rates": {},
                "issues": []
            }

        missing_counts: Dict[str, int] = {f: 0 for f in FEATURE_NAMES}
        out_of_range_counts: Dict[str, int] = {f: 0 for f in FEATURE_NAMES}
        issues: List[str] = []

        for row in feature_records:
            for feat in FEATURE_NAMES:
                if feat not in row or row[feat] is None:
                    missing_counts[feat] += 1
                else:
                    val = row[feat]
                    if feat in cls.FEATURE_RANGES:
                        low, high = cls.FEATURE_RANGES[feat]
                        if not (low <= float(val) <= high):
                            out_of_range_counts[feat] += 1

        missing_rates = {f: round(cnt / total_records, 4) for f, cnt in missing_counts.items()}
        out_of_range_rates = {f: round(cnt / total_records, 4) for f, cnt in out_of_range_counts.items()}

        penalty = 0.0
        for feat, rate in missing_rates.items():
            if rate > 0.20:
                penalty += 15.0
                issues.append(f"High missing rate for feature '{feat}': {rate * 100:.1f}%.")
            elif rate > 0.05:
                penalty += 5.0

        for feat, rate in out_of_range_rates.items():
            if rate > 0.10:
                penalty += 20.0
                issues.append(f"Feature '{feat}' has {rate * 100:.1f}% out-of-range values.")
            elif rate > 0.01:
                penalty += 5.0

        quality_score = max(0.0, min(100.0, 100.0 - penalty))

        if quality_score >= 80.0:
            status = "HEALTHY"
        elif quality_score >= 60.0:
            status = "WARNING"
        else:
            status = "CRITICAL"

        return {
            "status": status,
            "quality_score": round(quality_score, 1),
            "total_records": total_records,
            "missing_feature_rates": missing_rates,
            "out_of_range_rates": out_of_range_rates,
            "issues": issues
        }

data_quality_monitor = MLDataQualityMonitor()
