import math
from datetime import datetime
from typing import Dict, Any, Optional, List
import numpy as np
from sklearn.metrics import (
    precision_score, recall_score, f1_score, accuracy_score,
    roc_auc_score, average_precision_score, brier_score_loss,
    mean_absolute_error, mean_squared_error
)

from app.core.logging import logger

MIN_OUTCOMES_FOR_EVALUATION: int = 20
MIN_WINS_FOR_MODELING: int = 5
MIN_LOSSES_FOR_MODELING: int = 5
MIN_SAMPLES_FOR_RETRAINING: int = 30

class ModelEvaluator:
    """
    Evaluates ML and baseline model performance against real observed outcomes.
    Enforces strict cold-start safety: returns INSUFFICIENT_DATA rather than
    fabricating fake metrics when outcome volume is below statistical thresholds.
    """

    def __init__(
        self,
        min_outcomes: int = MIN_OUTCOMES_FOR_EVALUATION,
        min_wins: int = MIN_WINS_FOR_MODELING,
        min_losses: int = MIN_LOSSES_FOR_MODELING
    ):
        self.min_outcomes = min_outcomes
        self.min_wins = min_wins
        self.min_losses = min_losses

    def evaluate_predictions(
        self,
        pairs: List[Dict[str, Any]],
        model_version: Optional[str] = None,
        classification_threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        Calculates production-grade classification, ranking, and regression evaluation metrics.
        Guarantees that if resolved outcomes < min_outcomes or wins < min_wins,
        status='INSUFFICIENT_DATA' is returned without computing misleading metrics.
        """
        # Filter down to pairs with definitive resolved win/loss status
        labeled = [p for p in pairs if p.get("is_won") is not None]
        total_samples = len(labeled)
        wins = sum(1 for p in labeled if p["is_won"] == 1)
        losses = total_samples - wins

        if total_samples < self.min_outcomes or wins < self.min_wins or losses < self.min_losses:
            reasons = []
            if total_samples < self.min_outcomes:
                reasons.append(
                    f"Insufficient resolved outcomes ({total_samples}/{self.min_outcomes} required)."
                )
            if wins < self.min_wins:
                reasons.append(
                    f"Insufficient positive conversion wins ({wins}/{self.min_wins} required)."
                )
            if losses < self.min_losses:
                reasons.append(
                    f"Insufficient negative/unconverted outcomes ({losses}/{self.min_losses} required for binary discrimination)."
                )
            return {
                "status": "INSUFFICIENT_DATA",
                "model_version": model_version or "unknown",
                "evaluated_at": datetime.utcnow().isoformat(),
                "sample_count": total_samples,
                "win_count": wins,
                "loss_count": losses,
                "min_outcomes_required": self.min_outcomes,
                "min_wins_required": self.min_wins,
                "min_losses_required": self.min_losses,
                "classification_metrics": None,
                "ranking_metrics": None,
                "regression_metrics": None,
                "calibration_report": None,
                "reasons": reasons,
                "message": "Cold-start protection active. Model is safely falling back to deterministic baseline heuristic."
            }

        # Format arrays for sklearn
        y_true = np.array([p["is_won"] for p in labeled], dtype=int)
        
        # Probabilities: Use confidence_score (expected in [0, 1]) or normalize predicted_value / 100
        y_prob = []
        for p in labeled:
            c = float(p.get("confidence_score") or 0.0)
            if c > 1.0:
                c = c / 100.0
            elif c <= 0.0 and float(p.get("predicted_value") or 0.0) > 0.0:
                c = min(1.0, float(p["predicted_value"]) / 100.0)
            y_prob.append(min(1.0, max(0.0, c)))
        y_prob = np.array(y_prob, dtype=float)
        y_pred = (y_prob >= classification_threshold).astype(int)

        # 1. Classification Metrics
        prec = float(precision_score(y_true, y_pred, zero_division=0))
        rec = float(recall_score(y_true, y_pred, zero_division=0))
        f1 = float(f1_score(y_true, y_pred, zero_division=0))
        acc = float(accuracy_score(y_true, y_pred))
        brier = float(brier_score_loss(y_true, y_prob))

        # Safe ROC-AUC & PR-AUC (requires both classes)
        roc_auc = None
        pr_auc = None
        if len(np.unique(y_true)) > 1:
            try:
                roc_auc = float(roc_auc_score(y_true, y_prob))
                pr_auc = float(average_precision_score(y_true, y_prob))
            except Exception as e:
                logger.warning(f"[ModelEvaluator] AUC calculation skipped: {e}")

        # Calibration Bins (5 bins)
        bins = np.linspace(0.0, 1.0, 6)
        calibration_bins = []
        for i in range(len(bins) - 1):
            low, high = bins[i], bins[i+1]
            mask = (y_prob >= low) & (y_prob <= high if i == len(bins) - 2 else y_prob < high)
            bin_count = int(np.sum(mask))
            if bin_count > 0:
                bin_prob_mean = float(np.mean(y_prob[mask]))
                bin_actual_win_rate = float(np.mean(y_true[mask]))
                calibration_error = abs(bin_prob_mean - bin_actual_win_rate)
            else:
                bin_prob_mean = float((low + high) / 2.0)
                bin_actual_win_rate = 0.0
                calibration_error = 0.0

            calibration_bins.append({
                "range": f"[{low:.1f}, {high:.1f})",
                "sample_count": bin_count,
                "mean_predicted_prob": round(bin_prob_mean, 3),
                "actual_win_rate": round(bin_actual_win_rate, 3),
                "calibration_gap": round(calibration_error, 3)
            })

        # 2. Ranking Metrics (@K)
        # Sort indices by descending predicted probability
        sorted_indices = np.argsort(-y_prob)
        y_true_sorted = y_true[sorted_indices]
        total_wins = int(np.sum(y_true))
        overall_win_rate = float(total_wins / total_samples) if total_samples > 0 else 0.0

        # Extract actual deal values for financial ranking evaluation
        actual_values = np.array([float(p.get("actual_value") or 0.0) for p in labeled], dtype=float)
        actual_values_sorted = actual_values[sorted_indices]

        ranking_k = {}
        for k in [5, 10, 20]:
            effective_k = min(k, total_samples)
            if effective_k > 0:
                top_k_wins = int(np.sum(y_true_sorted[:effective_k]))
                prec_at_k = top_k_wins / effective_k
                rec_at_k = (top_k_wins / total_wins) if total_wins > 0 else 0.0
                rev_at_k = float(np.sum(actual_values_sorted[:effective_k]))
                lift_at_k = (prec_at_k / overall_win_rate) if overall_win_rate > 0 else 1.0

                ranking_k[f"top_{k}"] = {
                    "k": effective_k,
                    "precision_at_k": round(prec_at_k, 3),
                    "recall_at_k": round(rec_at_k, 3),
                    "win_rate_at_k": round(prec_at_k, 3),
                    "captured_revenue_usd": round(rev_at_k, 2),
                    "lift_vs_random": round(lift_at_k, 2)
                }

        # 3. Regression / Value Estimation Metrics
        pairs_with_revenue = [
            p for p in labeled
            if float(p.get("actual_value") or 0.0) > 0.0 and p.get("metadata", {}).get("expected_revenue_usd") is not None
        ]
        regression_metrics = None
        if len(pairs_with_revenue) >= 3:
            y_rev_true = np.array([float(p["actual_value"]) for p in pairs_with_revenue])
            y_rev_pred = np.array([float(p["metadata"]["expected_revenue_usd"]) for p in pairs_with_revenue])
            mae = float(mean_absolute_error(y_rev_true, y_rev_pred))
            rmse = float(np.sqrt(mean_squared_error(y_rev_true, y_rev_pred)))
            regression_metrics = {
                "sample_count": len(pairs_with_revenue),
                "mae_usd": round(mae, 2),
                "rmse_usd": round(rmse, 2),
                "mean_actual_value_usd": round(float(np.mean(y_rev_true)), 2),
                "mean_predicted_value_usd": round(float(np.mean(y_rev_pred)), 2)
            }

        return {
            "status": "EVALUATION_SUCCESS",
            "model_version": model_version or "unknown",
            "evaluated_at": datetime.utcnow().isoformat(),
            "sample_count": total_samples,
            "win_count": wins,
            "loss_count": losses,
            "base_win_rate": round(overall_win_rate, 4),
            "classification_metrics": {
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1_score": round(f1, 4),
                "accuracy": round(acc, 4),
                "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
                "pr_auc": round(pr_auc, 4) if pr_auc is not None else None,
                "brier_score": round(brier, 4)
            },
            "ranking_metrics": ranking_k,
            "regression_metrics": regression_metrics,
            "calibration_report": {
                "bins": calibration_bins,
                "brier_score": round(brier, 4)
            },
            "reasons": ["Sufficient ground-truth lifecycle outcomes available for production evaluation."]
        }

model_evaluator = ModelEvaluator()
