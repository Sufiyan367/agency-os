from typing import Dict, Any, List, Optional
from app.ml.evaluator import MIN_SAMPLES_FOR_RETRAINING, MIN_WINS_FOR_MODELING

class ModelRetrainingPolicy:
    """
    Evaluates whether retraining of the prospect scoring model is justified
    based on real outcome volume, statistical significance, and drift signals.
    Prevents degenerate training on insufficient or uncalibrated data.
    """

    def __init__(
        self,
        min_samples: int = MIN_SAMPLES_FOR_RETRAINING,
        min_wins: int = MIN_WINS_FOR_MODELING,
        min_losses: int = 5
    ):
        self.min_samples = min_samples
        self.min_wins = min_wins
        self.min_losses = min_losses

    def evaluate_retraining_trigger(
        self,
        resolved_outcomes: List[Dict[str, Any]],
        drift_report: Optional[Dict[str, Any]] = None,
        performance_report: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        labeled = [p for p in resolved_outcomes if p.get("is_won") is not None]
        sample_count = len(labeled)
        win_count = sum(1 for p in labeled if p["is_won"] == 1)
        loss_count = sample_count - win_count

        # 1. Gate: Sample volume check
        if sample_count < self.min_samples or win_count < self.min_wins or loss_count < self.min_losses:
            blockers = []
            if sample_count < self.min_samples:
                blockers.append(
                    f"Sample size {sample_count} is below retraining threshold ({self.min_samples} required)."
                )
            if win_count < self.min_wins:
                blockers.append(
                    f"Positive conversion wins ({win_count}) below threshold ({self.min_wins} required)."
                )
            if loss_count < self.min_losses:
                blockers.append(
                    f"Negative conversion losses ({loss_count}) below threshold ({self.min_losses} required for binary discrimination)."
                )
            return {
                "decision": "INSUFFICIENT_DATA_FOR_RETRAINING",
                "retrain_recommended": False,
                "sample_count": sample_count,
                "win_count": win_count,
                "loss_count": loss_count,
                "min_samples_required": self.min_samples,
                "min_wins_required": self.min_wins,
                "min_losses_required": self.min_losses,
                "min_wins_required": self.min_wins,
                "triggers": [],
                "blockers": blockers
            }

        # 2. Trigger check: Is there drift or performance degradation?
        triggers = []
        if drift_report:
            if drift_report.get("status") == "CRITICAL_DRIFT":
                triggers.append("Critical feature population drift detected.")
            elif drift_report.get("status") == "WARNING_DRIFT":
                triggers.append("Moderate feature drift detected across multiple features.")

        if performance_report:
            if performance_report.get("status") == "MODEL_DEGRADED":
                triggers.extend(performance_report.get("reasons", ["Observed model degradation."]))

        # Also trigger if substantial fresh outcomes exist
        if sample_count >= self.min_samples * 2:
            triggers.append(f"Substantial fresh training volume available ({sample_count} verified outcomes).")

        if triggers:
            return {
                "decision": "RETRAIN_RECOMMENDED",
                "retrain_recommended": True,
                "sample_count": sample_count,
                "win_count": win_count,
                "triggers": triggers,
                "blockers": []
            }

        return {
            "decision": "NO_RETRAIN_NEEDED",
            "retrain_recommended": False,
            "sample_count": sample_count,
            "win_count": win_count,
            "triggers": [],
            "blockers": ["Current model is stable and operating within statistical tolerance."]
        }

retraining_policy = ModelRetrainingPolicy()
