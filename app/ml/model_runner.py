import os
import math
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    Business, AuditRun, Country, Niche, ModelVersion, ModelPrediction, ModelStatus
)
from app.ml.feature_store import feature_store, FEATURE_NAMES
from app.ml.baseline_scorer import baseline_scorer, BaselineScorer
from app.ml.revenue_model import expected_revenue_model
from app.ml.policy_engine import policy_engine
from app.core.logging import logger

class SchemaValidationError(ValueError):
    """Raised when a feature dictionary fails strict schema validation."""
    pass

class ModelRunner:
    """
    Safe scikit-learn model runner abstraction with strict schema validation,
    deterministic baseline fallback, and immutable audit logging.
    """

    SCHEMA_VERSION: str = "1.0.0"

    def __init__(self):
        self.active_models: Dict[str, Any] = {}
        self.baseline_scorer: BaselineScorer = baseline_scorer
        self.revenue_model = expected_revenue_model
        self.model_health_overrides: Dict[str, str] = {}

    def set_health_override(self, model_name: str, status: Optional[str]) -> None:
        """Sets or clears a manual health override for a model (e.g. 'DEGRADED', 'HEALTHY')."""
        if status is None:
            self.model_health_overrides.pop(model_name, None)
        else:
            self.model_health_overrides[model_name] = status.upper()

    def get_health_status(self, model_name: str) -> str:
        """Returns the current effective health status of a model."""
        if model_name in self.model_health_overrides:
            return self.model_health_overrides[model_name]
        if model_name not in self.active_models:
            return "INSUFFICIENT_DATA"
        return "HEALTHY"

    def validate_feature_schema(self, features: Dict[str, Any]) -> None:
        """
        Strictly validates that all required features are present and are finite numbers.
        Fails closed: never silently invents missing features or accepts NaN/Inf.
        """
        if not isinstance(features, dict):
            raise SchemaValidationError(f"Features must be a dictionary, got {type(features).__name__}.")

        missing = [f for f in FEATURE_NAMES if f not in features]
        if missing:
            raise SchemaValidationError(f"Feature schema validation failed. Missing {len(missing)} required features: {missing}")

        for k in FEATURE_NAMES:
            v = features[k]
            if v is None:
                raise SchemaValidationError(f"Feature '{k}' is None. Silently inventing missing features is strictly prohibited.")
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise SchemaValidationError(f"Feature '{k}' must be numeric (int/float), got {type(v).__name__}: {v}")
            if math.isnan(v) or math.isinf(v):
                raise SchemaValidationError(f"Feature '{k}' has non-finite value: {v}")

    def predict_proba(self, model_name: str, features: Dict[str, float]) -> float:
        """
        Computes calibrated win probability for a given feature dictionary.
        Validates feature schema and fails closed if model is invalid.
        """
        self.validate_feature_schema(features)
        model = self.active_models.get(model_name)
        if model is None:
            raise ValueError(f"No active model found for '{model_name}'.")

        vec = [feature_store.to_vector(features)]
        if not hasattr(model, "predict_proba"):
            raise ValueError(f"Model '{model_name}' does not implement predict_proba.")

        proba = model.predict_proba(vec)
        if len(proba) == 0 or len(proba[0]) < 2:
            raise ValueError(f"Model '{model_name}' returned malformed probability array.")

        p_win = float(proba[0][1])
        if math.isnan(p_win) or math.isinf(p_win):
            raise ValueError(f"Model '{model_name}' produced invalid non-finite probability: {p_win}")

        return min(0.95, max(0.02, p_win))

    def predict(self, model_name: str, features: Dict[str, float]) -> int:
        """
        Computes binary classification (1: Convert, 0: Not Convert).
        Validates feature schema and fails closed if model is invalid.
        """
        self.validate_feature_schema(features)
        model = self.active_models.get(model_name)
        if model is None:
            raise ValueError(f"No active model found for '{model_name}'.")

        vec = [feature_store.to_vector(features)]
        if not hasattr(model, "predict"):
            raise ValueError(f"Model '{model_name}' does not implement predict.")

        pred = model.predict(vec)
        if len(pred) == 0:
            raise ValueError(f"Model '{model_name}' returned empty prediction.")

        return int(pred[0])

    def train_model(
        self,
        samples: List[Dict[str, float]],
        labels: List[int],
        model_name: str = "lead_scoring_model",
        version_tag: str = "v2.0.0-sklearn-logistic",
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Trains a standardized scikit-learn classifier pipeline for lead conversion.
        Validates all training sample schemas before fitting.
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
        import numpy as np

        if len(samples) < 5:
            raise ValueError(f"Insufficient training samples: got {len(samples)}, require at least 5.")
        if len(samples) != len(labels):
            raise ValueError(f"Samples ({len(samples)}) and labels ({len(labels)}) length mismatch.")

        # Strict validation on every training sample
        for i, s in enumerate(samples):
            try:
                self.validate_feature_schema(s)
            except SchemaValidationError as e:
                raise SchemaValidationError(f"Training sample at index {i} failed schema validation: {e}")

        X = [feature_store.to_vector(s) for s in samples]
        y = np.array(labels)

        if len(np.unique(y)) < 2:
            raise ValueError("Training dataset must contain at least two target classes (0 and 1).")

        # Standard pipeline
        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(class_weight="balanced", random_state=42, max_iter=1000))
        ])
        pipe.fit(X, y)
        pipe.version_tag = version_tag

        # Metrics calculation
        y_pred = pipe.predict(X)
        y_proba = pipe.predict_proba(X)[:, 1]

        acc = float(accuracy_score(y, y_pred))
        prec = float(precision_score(y, y_pred, zero_division=0))
        rec = float(recall_score(y, y_pred, zero_division=0))
        try:
            auc = float(roc_auc_score(y, y_proba))
        except Exception:
            auc = 0.5

        metrics = {
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "roc_auc": round(auc, 4),
            "sample_count": len(samples),
            "trained_at": datetime.utcnow().isoformat()
        }

        self.active_models[model_name] = pipe
        logger.info(f"[ModelRunner] Successfully trained '{model_name}' ({version_tag}) with accuracy={acc:.2f}, AUC={auc:.2f}")

        return {
            "model_name": model_name,
            "version_tag": version_tag,
            "metrics": metrics,
            "status": "TRAINED_MODEL"
        }

    def train_baseline_classifier(
        self,
        samples: List[Dict[str, float]],
        labels: List[int],
        version_tag: str = "v2.0.0-sklearn-logistic"
    ) -> Any:
        """
        Backwards-compatible training method for lead conversion classifier pipeline.
        """
        self.train_model(samples, labels, model_name="lead_scoring_model", version_tag=version_tag)
        return self.active_models["lead_scoring_model"]

    async def score_and_evaluate_lead(
        self,
        session: AsyncSession,
        business: Business,
        audit: Optional[AuditRun] = None,
        country: Optional[Country] = None,
        niche: Optional[Niche] = None,
        deal_value_usd: Optional[float] = None,
        custom_features: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Extracts features, runs inference (or baseline fallback), evaluates commercial revenue,
        and logs the prediction record into the database.
        """
        # 1. Feature Extraction & Strict Schema Validation
        if custom_features is not None:
            features = custom_features
        else:
            features = feature_store.extract_features(
                business=business, audit=audit, country=country, niche=niche
            )

        self.validate_feature_schema(features)

        # 2. Model Inference with Cold-Start Safe Fallback
        model_name = "lead_scoring_model"
        active_ml_model = self.active_models.get(model_name)
        health_status = self.get_health_status(model_name)
        is_baseline = True
        version_tag = self.baseline_scorer.VERSION_TAG
        model_status_label = "BASELINE"
        fallback_reason = None

        if health_status == "DEGRADED":
            logger.warning(f"[ModelRunner] ML Model '{model_name}' is DEGRADED. Autonomously routing to baseline heuristic.")
            baseline_res = self.baseline_scorer.predict(features)
            fallback_reason = "MODEL_DEGRADED"
            prediction_res = {
                "score": baseline_res["total_score"],
                "priority": baseline_res["priority"],
                "probability_win": baseline_res["probability_of_conversion"],
                "breakdown": features,
                "drivers": baseline_res["explainability"]["drivers"],
                "rationale": f"[AUTOMATED FALLBACK - MODEL DEGRADED] {baseline_res['explainability']['rationale']}",
                "is_baseline": True,
                "model_name": "lead_scoring_baseline",
                "version_tag": self.baseline_scorer.VERSION_TAG,
                "fallback_reason": fallback_reason
            }
            model_status_label = "DEGRADED_FALLBACK"
        elif active_ml_model is not None:
            try:
                prob = self.predict_proba(model_name, features)
                score = round(prob * 100.0, 1)
                is_baseline = False
                version_tag = getattr(active_ml_model, "version_tag", "v2.0.0-sklearn")
                model_status_label = "TRAINED_MODEL"

                if score >= 85.0:
                    priority = "A"
                elif score >= 70.0:
                    priority = "B"
                elif score >= 55.0:
                    priority = "C"
                else:
                    priority = "LOW"

                prediction_res = {
                    "score": score,
                    "priority": priority,
                    "probability_win": round(prob, 3),
                    "breakdown": features,
                    "drivers": ["ML predictive conversion likelihood"],
                    "rationale": f"ML Model {version_tag} predicted conversion probability {prob * 100:.1f}% (Score: {score}).",
                    "is_baseline": False,
                    "model_name": model_name,
                    "version_tag": version_tag,
                    "fallback_reason": None
                }
            except Exception as ml_err:
                logger.warning(f"[ModelRunner] ML inference failed ({ml_err}). Safely falling back to baseline heuristic.")
                baseline_res = self.baseline_scorer.predict(features)
                fallback_reason = "INFERENCE_ERROR"
                prediction_res = {
                    "score": baseline_res["total_score"],
                    "priority": baseline_res["priority"],
                    "probability_win": baseline_res["probability_of_conversion"],
                    "breakdown": features,
                    "drivers": baseline_res["explainability"]["drivers"],
                    "rationale": baseline_res["explainability"]["rationale"],
                    "is_baseline": True,
                    "model_name": "lead_scoring_baseline",
                    "version_tag": self.baseline_scorer.VERSION_TAG,
                    "fallback_reason": fallback_reason
                }
                model_status_label = "COLD_START"
        else:
            baseline_res = self.baseline_scorer.predict(features)
            fallback_reason = "NO_TRAINED_MODEL"
            prediction_res = {
                "score": baseline_res["total_score"],
                "priority": baseline_res["priority"],
                "probability_win": baseline_res["probability_of_conversion"],
                "breakdown": features,
                "drivers": baseline_res["explainability"]["drivers"],
                "rationale": baseline_res["explainability"]["rationale"],
                "is_baseline": True,
                "model_name": "lead_scoring_baseline",
                "version_tag": self.baseline_scorer.VERSION_TAG,
                "fallback_reason": fallback_reason
            }
            model_status_label = "BASELINE"

        score = prediction_res["score"]
        priority = prediction_res["priority"]
        prob_win = prediction_res["probability_win"]

        # 3. Expected Revenue Evaluation
        effective_deal_value = deal_value_usd or features.get("niche_avg_deal_size", 750.0)
        revenue_eval = self.revenue_model.evaluate_deal_potential(
            probability_win=prob_win,
            proposed_price_usd=effective_deal_value,
            niche_avg_deal_size=features.get("niche_avg_deal_size", 750.0),
            data_source=model_status_label
        )

        # 4. Asynchronous ModelPrediction Persistence
        pred_uuid = f"PRED-{uuid.uuid4().hex[:12].upper()}"

        # Verify or register version in DB if missing
        q_v = select(ModelVersion).where(ModelVersion.version_tag == version_tag)
        existing_v = (await session.execute(q_v)).scalar_one_or_none()
        if not existing_v:
            mv_record = ModelVersion(
                name=model_name,
                version_tag=version_tag,
                model_type="deterministic_baseline" if is_baseline else "scikit_learn",
                parameters={"threshold": 55.0, "schema_version": self.SCHEMA_VERSION},
                training_metrics={"is_baseline": is_baseline, "status": model_status_label},
                status=ModelStatus.ACTIVE.value
            )
            session.add(mv_record)
            await session.flush()

        # Sanitize features for audit persistence (never store raw credentials/passwords)
        sanitized_features = {
            k: v for k, v in features.items()
            if not any(sec in k.lower() for sec in ["secret", "password", "token", "key", "auth"])
        }

        prediction_record = ModelPrediction(
            prediction_id=pred_uuid,
            model_name=model_name,
            model_version=version_tag,
            entity_type="business",
            entity_id=business.id,
            prediction_type="lead_score",
            predicted_value=score,
            confidence_score=prob_win,
            features=sanitized_features,
            is_baseline=is_baseline,
            metadata_json={
                "priority": priority,
                "model_status": model_status_label,
                "schema_version": self.SCHEMA_VERSION,
                "commercial_tier": revenue_eval["commercial_tier"],
                "expected_revenue_usd": revenue_eval["expected_revenue_usd"],
                "drivers": prediction_res["drivers"],
                "rationale": prediction_res["rationale"],
                "fallback_reason": fallback_reason
            }
        )
        session.add(prediction_record)
        await session.flush()

        return {
            "prediction_id": pred_uuid,
            "score": score,
            "priority": priority,
            "probability_win": prob_win,
            "expected_revenue": revenue_eval,
            "breakdown": prediction_res["breakdown"],
            "drivers": prediction_res["drivers"],
            "rationale": prediction_res["rationale"],
            "is_baseline": is_baseline,
            "model_status": model_status_label,
            "version_tag": version_tag,
            "fallback_reason": fallback_reason
        }

model_runner = ModelRunner()
