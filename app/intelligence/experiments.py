"""
Controlled Experimentation Framework — Mega Prompt 8.
Manages reversible A/B experiments across outreach copy, subject lines, CTA framing,
and follow-up timing with statistical confidence thresholds.
"""
import uuid
import math
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.ml_models import Experiment, ExperimentStatus

class ExperimentEngine:
    """
    Manages controlled, reversible experiments with statistical validity checks.
    """

    MIN_SAMPLE_THRESHOLD = 30

    @classmethod
    async def create_experiment(
        cls,
        session: AsyncSession,
        experiment_key: str,
        name: str,
        hypothesis: str,
        variants: Dict[str, Any],
        metric: str = "reply_rate"
    ) -> Experiment:
        """Initializes a new controlled experiment."""
        exp = Experiment(
            experiment_key=experiment_key,
            name=name,
            description=hypothesis,
            variants=variants,
            status=ExperimentStatus.ACTIVE.value,
            metrics={"primary_metric": metric, "sample_size": 0, "observations": {}},
            started_at=datetime.utcnow()
        )
        session.add(exp)
        await session.commit()
        return exp

    @classmethod
    async def evaluate_experiment(
        cls,
        session: AsyncSession,
        experiment_key: str
    ) -> Dict[str, Any]:
        """
        Calculates conversion lifts and statistical confidence between variant and control.
        """
        stmt = select(Experiment).where(Experiment.experiment_key == experiment_key)
        exp = (await session.execute(stmt)).scalar_one_or_none()
        if not exp:
            return {"error": "Experiment not found", "status": "NOT_FOUND"}

        metrics = exp.metrics or {}
        obs = metrics.get("observations", {})

        # Control stats
        ctrl = obs.get("control", {"sends": 0, "conversions": 0})
        var = obs.get("variant", {"sends": 0, "conversions": 0})

        ctrl_sends = ctrl.get("sends", 0)
        var_sends = var.get("sends", 0)
        ctrl_conv = ctrl.get("conversions", 0)
        var_conv = var.get("conversions", 0)

        total_sample = ctrl_sends + var_sends
        if total_sample < cls.MIN_SAMPLE_THRESHOLD:
            return {
                "experiment_key": experiment_key,
                "status": "INSUFFICIENT_DATA",
                "sample_size": total_sample,
                "threshold_required": cls.MIN_SAMPLE_THRESHOLD,
                "message": f"Collected {total_sample} observations; need at least {cls.MIN_SAMPLE_THRESHOLD} before evaluating lift.",
                "is_significant": False
            }

        ctrl_rate = (ctrl_conv / ctrl_sends) if ctrl_sends > 0 else 0.0
        var_rate = (var_conv / var_sends) if var_sends > 0 else 0.0

        lift_pct = round(((var_rate - ctrl_rate) / (ctrl_rate if ctrl_rate > 0 else 1.0)) * 100.0, 1)

        # Standard two-proportion Z-test for statistical significance
        pooled_p = (ctrl_conv + var_conv) / total_sample
        se = math.sqrt(pooled_p * (1 - pooled_p) * ((1.0 / ctrl_sends) + (1.0 / var_sends))) if pooled_p > 0 and pooled_p < 1 else 0.001
        z_score = (var_rate - ctrl_rate) / se if se > 0 else 0.0

        # Confidence: p-value from z_score
        is_significant = abs(z_score) >= 1.96  # 95% confidence
        confidence = round(min(0.99, max(0.50, 0.50 + (abs(z_score) / 4.0))), 2)

        return {
            "experiment_key": experiment_key,
            "status": "EVALUATED",
            "sample_size": total_sample,
            "control_conversion_rate": round(ctrl_rate, 3),
            "variant_conversion_rate": round(var_rate, 3),
            "lift_pct": lift_pct,
            "z_score": round(z_score, 2),
            "is_statistically_significant": is_significant,
            "confidence": confidence,
            "recommendation": "PROCEED_WITH_VARIANT" if is_significant and lift_pct > 0 else "MAINTAIN_CONTROL"
        }


experiment_engine = ExperimentEngine()
