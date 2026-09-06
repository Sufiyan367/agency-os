from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database.ml_models import ModelPrediction, ModelVersion
from app.ml.outcome_service import outcome_service
from app.ml.evaluator import model_evaluator, MIN_OUTCOMES_FOR_EVALUATION, MIN_WINS_FOR_MODELING
from app.ml.drift_monitor import feature_drift_monitor, prediction_drift_monitor
from app.ml.data_quality import data_quality_monitor
from app.ml.feature_store import FEATURE_NAMES
from app.core.logging import logger

class ModelHealthService:
    """
    Computes unified ML system health telemetry, drift states,
    data quality scores, and transparent fallback routing decisions.
    """

    @classmethod
    async def get_model_health(
        cls,
        session: AsyncSession,
        model_name: str = "lead_scoring_model",
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """
        Gathers live telemetry from predictions, outcomes, drift monitors,
        and data quality checks to compute a composite 0-100 health score.
        """
        now = datetime.utcnow()
        start_time = now - timedelta(days=lookback_days)

        # 1. Fetch prediction-outcome pairs for temporal evaluation
        pairs = await outcome_service.get_prediction_outcome_pairs(
            session=session,
            start_time=start_time
        )
        eval_report = model_evaluator.evaluate_predictions(pairs, model_version=model_name)

        # 2. Fetch recent predictions for feature audit and drift
        q_preds = (
            select(ModelPrediction)
            .where(ModelPrediction.created_at >= start_time)
            .order_by(desc(ModelPrediction.created_at))
            .limit(200)
        )
        res_preds = await session.execute(q_preds)
        recent_preds = res_preds.scalars().all()

        features_batch = [p.features for p in recent_preds if p.features]
        dq_report = data_quality_monitor.audit_features_batch(features_batch)

        # 3. Drift Evaluation (Split into reference older half vs current newer half if sufficient)
        drift_report: Dict[str, Any] = {
            "status": "INSUFFICIENT_DATA",
            "overall_severity": "NORMAL",
            "message": "Insufficient prediction volume to evaluate distribution drift."
        }
        pred_drift_report: Dict[str, Any] = {
            "status": "INSUFFICIENT_DATA",
            "probability_psi": None
        }

        if len(recent_preds) >= 20:
            half = len(recent_preds) // 2
            cur_p = [{"confidence_score": p.confidence_score, "metadata": p.metadata_json} for p in recent_preds[:half]]
            ref_p = [{"confidence_score": p.confidence_score, "metadata": p.metadata_json} for p in recent_preds[half:]]
            pred_drift_report = prediction_drift_monitor.evaluate_predictions(ref_p, cur_p)

            cur_f = [p.features for p in recent_preds[:half] if p.features]
            ref_f = [p.features for p in recent_preds[half:] if p.features]
            drift_report = feature_drift_monitor.evaluate_features(ref_f, cur_f, FEATURE_NAMES[:6])

        # 4. Check if a trained scikit-learn model version is active in DB
        q_mv = (
            select(ModelVersion)
            .where(ModelVersion.name == model_name, ModelVersion.status == "ACTIVE")
            .order_by(desc(ModelVersion.created_at))
            .limit(1)
        )
        res_mv = await session.execute(q_mv)
        active_version = res_mv.scalar_one_or_none()

        # 5. Composite Health Computation
        reasons: List[str] = []
        has_active_ml_model = (
            active_version is not None and active_version.model_type != "deterministic_baseline"
        )
        is_cold_start = eval_report.get("status") == "INSUFFICIENT_DATA" or not has_active_ml_model

        if is_cold_start:
            status = "INSUFFICIENT_DATA"
            composite_score = None
            is_fallback_active = True
            active_engine = "deterministic_baseline"
            if not has_active_ml_model:
                reasons.append("Cold-start protection active: No trained ML model deployed. Operating on deterministic baseline.")
            else:
                reasons.append(
                    f"Cold-start protection active: {eval_report['sample_count']}/{MIN_OUTCOMES_FOR_EVALUATION} real outcomes "
                    f"and {eval_report['win_count']}/{MIN_WINS_FOR_MODELING} wins recorded."
                )
            reasons.append("Inference safely routed to deterministic heuristic baseline.")
        else:
            base_score = 100.0

            # Classification & calibration contribution
            brier = eval_report.get("classification_metrics", {}).get("brier_score", 0.10)
            if brier > 0.25:
                base_score -= 25.0
                reasons.append(f"Elevated calibration error (Brier score: {brier:.3f}).")
            elif brier > 0.18:
                base_score -= 10.0

            roc_auc = eval_report.get("classification_metrics", {}).get("roc_auc")
            if roc_auc is not None:
                if roc_auc < 0.60:
                    base_score -= 30.0
                    reasons.append(f"Sub-baseline discriminative power (ROC-AUC: {roc_auc:.3f}).")
                elif roc_auc < 0.70:
                    base_score -= 15.0

            # Drift contribution
            if drift_report.get("overall_severity") == "CRITICAL":
                base_score -= 30.0
                reasons.append("Critical feature population drift detected.")
            elif drift_report.get("overall_severity") == "WARNING":
                base_score -= 15.0
                reasons.append("Moderate feature drift detected.")

            # Data quality contribution
            dq_penalty = (100.0 - dq_report.get("quality_score", 100.0)) * 0.25
            base_score -= dq_penalty
            if dq_penalty > 5.0:
                reasons.append(f"Data quality degradation (Audit score: {dq_report.get('quality_score')}/100).")

            composite_score = round(max(0.0, min(100.0, base_score)), 1)

            if composite_score >= 80.0:
                status = "HEALTHY"
                is_fallback_active = False
                active_engine = "scikit_learn" if active_version and active_version.model_type != "deterministic_baseline" else "deterministic_baseline"
                reasons.append("Model is healthy, well-calibrated, and operating within tolerances.")
            elif composite_score >= 60.0:
                status = "WARNING"
                is_fallback_active = False
                active_engine = "scikit_learn" if active_version and active_version.model_type != "deterministic_baseline" else "deterministic_baseline"
                reasons.append("Model exhibits warning-level variance or mild feature drift.")
            else:
                status = "DEGRADED"
                is_fallback_active = True
                active_engine = "deterministic_baseline"
                reasons.append("Model is degraded. Automated fallback has routed scoring to deterministic baseline.")

        return {
            "status": status,
            "composite_health_score": composite_score,
            "active_scoring_engine": active_engine,
            "is_fallback_active": is_fallback_active,
            "model_name": model_name,
            "evaluated_at": now.isoformat(),
            "evaluation": eval_report,
            "feature_drift": drift_report,
            "prediction_drift": pred_drift_report,
            "data_quality": dq_report,
            "reasons": reasons
        }

model_health_service = ModelHealthService()
