import math
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from scipy.stats import ks_2samp

from app.core.logging import logger

MIN_SAMPLES_FOR_DRIFT: int = 10

def calculate_psi(
    expected: np.ndarray,
    actual: np.ndarray,
    num_bins: int = 5,
    epsilon: float = 1e-4
) -> float:
    """
    Computes Population Stability Index (PSI) between reference (expected)
    and current (actual) distributions with robust support for disjoint,
    small-sample, and skewed distributions.
    """
    if len(expected) == 0 or len(actual) == 0:
        return 0.0

    all_vals = np.concatenate([expected, actual])
    low, high = float(np.min(all_vals)), float(np.max(all_vals))
    if low == high:
        return 0.0

    # If distributions are completely non-overlapping, population has critically drifted
    if float(np.max(expected)) < float(np.min(actual)) or float(np.max(actual)) < float(np.min(expected)):
        return 2.5

    # Determine quantile bins on expected reference
    quantiles = np.linspace(0, 100, num_bins + 1)
    bin_edges = np.percentile(expected, quantiles)
    bin_edges = np.unique(bin_edges)

    if len(bin_edges) < 2:
        bin_edges = np.linspace(low - 1e-5, high + 1e-5, num_bins + 1)
    else:
        bin_edges[0] = min(bin_edges[0], low) - 1e-5
        bin_edges[-1] = max(bin_edges[-1], high) + 1e-5

    exp_counts, _ = np.histogram(expected, bins=bin_edges)
    act_counts, _ = np.histogram(actual, bins=bin_edges)

    exp_pct = (exp_counts / len(expected)) + epsilon
    act_pct = (act_counts / len(actual)) + epsilon

    exp_pct /= np.sum(exp_pct)
    act_pct /= np.sum(act_pct)

    psi_val = float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))
    return max(0.0, psi_val)

class FeatureDriftMonitor:
    """
    Production drift monitor for numerical and categorical feature distributions.
    Computes PSI and 2-sample Kolmogorov-Smirnov test statistics.
    """

    @staticmethod
    def evaluate_numerical_feature(
        feature_name: str,
        reference_values: List[float],
        current_values: List[float]
    ) -> Dict[str, Any]:
        """
        Calculates PSI and KS test for an individual numerical feature.
        """
        ref_arr = np.array([float(x) for x in reference_values if x is not None and not math.isnan(x)], dtype=float)
        cur_arr = np.array([float(x) for x in current_values if x is not None and not math.isnan(x)], dtype=float)

        if len(ref_arr) < MIN_SAMPLES_FOR_DRIFT or len(cur_arr) < MIN_SAMPLES_FOR_DRIFT:
            return {
                "feature_name": feature_name,
                "status": "INSUFFICIENT_DATA",
                "psi": 0.0,
                "ks_statistic": None,
                "ks_p_value": None,
                "reference_count": len(ref_arr),
                "current_count": len(cur_arr),
                "severity": "NORMAL"
            }

        psi = calculate_psi(ref_arr, cur_arr)
        ks_res = ks_2samp(ref_arr, cur_arr)
        ks_stat = float(ks_res.statistic)
        ks_p = float(ks_res.pvalue)

        # PSI thresholds: <0.10: Normal, 0.10-0.25: Warning, >=0.25: Critical
        if psi >= 0.25:
            severity = "CRITICAL"
            status = "CRITICAL_DRIFT"
        elif psi >= 0.10 or (ks_p < 0.01 and ks_stat > 0.20):
            severity = "WARNING"
            status = "WARNING_DRIFT"
        else:
            severity = "NORMAL"
            status = "NORMAL"

        return {
            "feature_name": feature_name,
            "status": status,
            "severity": severity,
            "psi": round(psi, 4),
            "ks_statistic": round(ks_stat, 4),
            "ks_p_value": round(ks_p, 4),
            "ref_mean": round(float(np.mean(ref_arr)), 2),
            "cur_mean": round(float(np.mean(cur_arr)), 2),
            "ref_std": round(float(np.std(ref_arr)), 2),
            "cur_std": round(float(np.std(cur_arr)), 2),
            "reference_count": len(ref_arr),
            "current_count": len(cur_arr)
        }

    @classmethod
    def evaluate_features(
        cls,
        reference_records: List[Dict[str, Any]],
        current_records: List[Dict[str, Any]],
        feature_names: List[str]
    ) -> Dict[str, Any]:
        """
        Evaluates a suite of features across reference and current datasets.
        """
        if len(reference_records) < MIN_SAMPLES_FOR_DRIFT or len(current_records) < MIN_SAMPLES_FOR_DRIFT:
            return {
                "status": "INSUFFICIENT_DATA",
                "overall_severity": "NORMAL",
                "reference_samples": len(reference_records),
                "current_samples": len(current_records),
                "features": {},
                "critical_count": 0,
                "warning_count": 0,
                "message": f"Need at least {MIN_SAMPLES_FOR_DRIFT} samples in both windows to compute reliable drift."
            }

        feature_reports = {}
        critical_cnt = 0
        warning_cnt = 0

        for feat in feature_names:
            ref_vals = [r.get(feat) for r in reference_records if r.get(feat) is not None]
            cur_vals = [r.get(feat) for r in current_records if r.get(feat) is not None]
            
            rep = cls.evaluate_numerical_feature(feat, ref_vals, cur_vals)
            feature_reports[feat] = rep
            if rep.get("severity") == "CRITICAL":
                critical_cnt += 1
            elif rep.get("severity") == "WARNING":
                warning_cnt += 1

        if critical_cnt > 0:
            overall = "CRITICAL"
            status = "CRITICAL_DRIFT"
        elif warning_cnt >= 2:
            overall = "WARNING"
            status = "WARNING_DRIFT"
        else:
            overall = "NORMAL"
            status = "HEALTHY"

        return {
            "status": status,
            "overall_severity": overall,
            "reference_samples": len(reference_records),
            "current_samples": len(current_records),
            "critical_count": critical_cnt,
            "warning_count": warning_cnt,
            "features": feature_reports
        }

class PredictionDriftMonitor:
    """
    Monitors drift in model output distributions (win probability, expected value, priority).
    """

    @staticmethod
    def evaluate_predictions(
        reference_predictions: List[Dict[str, Any]],
        current_predictions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        ref_count = len(reference_predictions)
        cur_count = len(current_predictions)

        if ref_count < MIN_SAMPLES_FOR_DRIFT or cur_count < MIN_SAMPLES_FOR_DRIFT:
            return {
                "status": "INSUFFICIENT_DATA",
                "reference_count": ref_count,
                "current_count": cur_count,
                "probability_drift": None,
                "priority_shift": None
            }

        # Win probability drift
        ref_probs = np.array([float(p.get("confidence_score") or 0.0) for p in reference_predictions], dtype=float)
        cur_probs = np.array([float(p.get("confidence_score") or 0.0) for p in current_predictions], dtype=float)
        prob_psi = calculate_psi(ref_probs, cur_probs)

        # Priority shifts
        def get_priority_dist(preds: List[Dict[str, Any]]) -> Dict[str, float]:
            counts: Dict[str, int] = {}
            for p in preds:
                pri = p.get("metadata", {}).get("priority") or "LOW"
                counts[pri] = counts.get(pri, 0) + 1
            tot = len(preds) or 1
            return {k: round(v / tot, 3) for k, v in counts.items()}

        ref_dist = get_priority_dist(reference_predictions)
        cur_dist = get_priority_dist(current_predictions)

        status = "NORMAL"
        if prob_psi >= 0.25:
            status = "CRITICAL_DRIFT"
        elif prob_psi >= 0.10:
            status = "WARNING_DRIFT"

        return {
            "status": status,
            "probability_psi": round(prob_psi, 4),
            "ref_mean_prob": round(float(np.mean(ref_probs)), 3),
            "cur_mean_prob": round(float(np.mean(cur_probs)), 3),
            "reference_priority_distribution": ref_dist,
            "current_priority_distribution": cur_dist,
            "reference_count": ref_count,
            "current_count": cur_count
        }

class PerformanceDriftMonitor:
    """
    Monitors degradation in model accuracy, calibration, and win-rate across time windows.
    """

    @staticmethod
    def evaluate_performance_degradation(
        baseline_metrics: Optional[Dict[str, Any]],
        current_metrics: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not baseline_metrics or not current_metrics:
            return {
                "status": "INSUFFICIENT_DATA",
                "severity": "NORMAL",
                "reasons": ["Historical baseline or current evaluation metrics missing."]
            }

        if baseline_metrics.get("status") != "EVALUATION_SUCCESS" or current_metrics.get("status") != "EVALUATION_SUCCESS":
            return {
                "status": "INSUFFICIENT_DATA",
                "severity": "NORMAL",
                "reasons": ["One or both evaluation windows have insufficient ground-truth outcomes."]
            }

        reasons = []
        is_degraded = False

        # 1. ROC-AUC Drop
        base_auc = baseline_metrics.get("classification_metrics", {}).get("roc_auc")
        cur_auc = current_metrics.get("classification_metrics", {}).get("roc_auc")
        if base_auc is not None and cur_auc is not None:
            drop = base_auc - cur_auc
            if drop >= 0.10:
                is_degraded = True
                reasons.append(f"Severe ROC-AUC degradation: dropped {drop:.3f} (from {base_auc:.3f} to {cur_auc:.3f}).")

        # 2. Brier Score (Calibration Error) Increase
        base_brier = baseline_metrics.get("classification_metrics", {}).get("brier_score")
        cur_brier = current_metrics.get("classification_metrics", {}).get("brier_score")
        if base_brier is not None and cur_brier is not None:
            diff = cur_brier - base_brier
            if diff >= 0.08:
                is_degraded = True
                reasons.append(f"Severe calibration degradation: Brier score increased by {diff:.3f} (from {base_brier:.3f} to {cur_brier:.3f}).")

        # 3. Precision / F1 Collapse
        base_f1 = baseline_metrics.get("classification_metrics", {}).get("f1_score", 0.0)
        cur_f1 = current_metrics.get("classification_metrics", {}).get("f1_score", 0.0)
        if base_f1 > 0.30 and cur_f1 < 0.15:
            is_degraded = True
            reasons.append(f"Model F1 score collapsed from {base_f1:.3f} to {cur_f1:.3f}.")

        if is_degraded:
            return {
                "status": "MODEL_DEGRADED",
                "severity": "CRITICAL",
                "reasons": reasons
            }

        return {
            "status": "MODEL_HEALTHY",
            "severity": "NORMAL",
            "reasons": ["Performance metrics remain stable within expected tolerances."]
        }

feature_drift_monitor = FeatureDriftMonitor()
prediction_drift_monitor = PredictionDriftMonitor()
performance_drift_monitor = PerformanceDriftMonitor()
