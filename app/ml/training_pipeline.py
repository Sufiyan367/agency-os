import os
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database.models import (
    Business, AuditRun, Country, Niche, PipelineStage, Outcome, ModelVersion, ModelStatus
)
from app.ml.feature_store import feature_store, FEATURE_NAMES
from app.ml.model_runner import model_runner
from app.core.logging import logger

class TrainingPipeline:
    """
    Reproducible ML training dataset builder and pipeline runner.
    Prevents target leakage, enforces minimum historical sample thresholds,
    and isolates training vs evaluation datasets.
    """

    MIN_SAMPLES_THRESHOLD: int = 20
    MIN_POSITIVE_SAMPLES: int = 5
    MIN_NEGATIVE_SAMPLES: int = 5

    # Target leakage blacklist: attributes that must NEVER appear in feature vectors
    TARGET_LEAKAGE_BLACKLIST = {
        "pipeline_stage", "replies", "outreach_messages", "payments", "payment_status",
        "deals", "proposals", "outcome_type", "realized_revenue", "is_won", "win",
        "deal_value_won", "sent_count", "reply_classification", "advance_paid"
    }

    def verify_no_target_leakage(self, feature_dict: Dict[str, Any]) -> None:
        """
        Guarantees no post-outreach or downstream outcome attributes leak into the feature set.
        """
        for k in feature_dict.keys():
            k_lower = k.lower()
            if any(black in k_lower for black in self.TARGET_LEAKAGE_BLACKLIST):
                raise ValueError(f"Target leakage violation: Forbidden feature '{k}' detected in training feature set.")

    async def build_dataset_from_db(
        self,
        session: AsyncSession
    ) -> Tuple[List[Dict[str, float]], List[int], List[int]]:
        """
        Extracts pre-outreach features and verified binary conversion outcomes from the database.
        Returns: (samples, labels, business_ids)
        """
        # Fetch businesses in definitive outcome stages
        q = select(Business).where(
            Business.pipeline_stage.in_([
                PipelineStage.WON.value,
                PipelineStage.ADVANCE_PAID.value,
                PipelineStage.COMPLETED.value,
                PipelineStage.LOST.value,
                PipelineStage.REJECTED.value
            ])
        ).order_by(Business.id)

        businesses = (await session.execute(q)).scalars().all()

        samples: List[Dict[str, float]] = []
        labels: List[int] = []
        biz_ids: List[int] = []

        for b in businesses:
            # Determine conversion label (1: Won / Advance Paid, 0: Lost / Rejected)
            is_won = b.pipeline_stage in (
                PipelineStage.WON.value,
                PipelineStage.ADVANCE_PAID.value,
                PipelineStage.COMPLETED.value
            )
            label = 1 if is_won else 0

            # Pre-outreach diagnostic audit
            q_audit = select(AuditRun).where(AuditRun.business_id == b.id).order_by(desc(AuditRun.audited_at))
            audit = (await session.execute(q_audit)).scalars().first()

            # Economic context
            q_country = select(Country).where(Country.code == b.country) if b.country else None
            country = (await session.execute(q_country)).scalar_one_or_none() if q_country is not None else None

            q_niche = select(Niche).where(Niche.name == b.niche) if b.niche else None
            niche = (await session.execute(q_niche)).scalar_one_or_none() if q_niche is not None else None

            features = feature_store.extract_features(
                business=b, audit=audit, country=country, niche=niche
            )

            # Leakage protection audit
            self.verify_no_target_leakage(features)

            samples.append(features)
            labels.append(label)
            biz_ids.append(b.id)

        return samples, labels, biz_ids

    async def run_training(
        self,
        session: AsyncSession,
        version_tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes reproducible model training or falls back safely to COLD_START baseline.
        """
        samples, labels, biz_ids = await self.build_dataset_from_db(session)

        pos_count = sum(labels)
        neg_count = len(labels) - pos_count
        tag = version_tag or f"v2.{datetime.utcnow().strftime('%Y%m%d.%H%M')}-sklearn-lr"

        # Check sample threshold
        if (len(samples) < self.MIN_SAMPLES_THRESHOLD or
            pos_count < self.MIN_POSITIVE_SAMPLES or
            neg_count < self.MIN_NEGATIVE_SAMPLES):
            
            logger.info(
                f"[TrainingPipeline] Insufficient historical data for ML training "
                f"({len(samples)} total, {pos_count} positive, {neg_count} negative). "
                f"Required >= {self.MIN_SAMPLES_THRESHOLD} samples with >= {self.MIN_POSITIVE_SAMPLES} positive. "
                f"Gracefully maintaining COLD_START baseline status."
            )
            return {
                "status": "COLD_START",
                "reason": (
                    f"Insufficient historical conversion data. "
                    f"Available: {len(samples)} samples ({pos_count} won, {neg_count} lost). "
                    f"Minimum required: {self.MIN_SAMPLES_THRESHOLD} total with {self.MIN_POSITIVE_SAMPLES} conversions."
                ),
                "model_mode": "BASELINE",
                "sample_count": len(samples),
                "positive_count": pos_count,
                "negative_count": neg_count,
                "threshold_required": self.MIN_SAMPLES_THRESHOLD
            }

        # Split data cleanly into Train (80%) and Test/Evaluation (20%)
        from sklearn.model_selection import train_test_split
        X_train, X_eval, y_train, y_eval = train_test_split(
            samples, labels, test_size=0.20, random_state=42, stratify=labels
        )

        # Train model pipeline
        train_result = model_runner.train_model(
            samples=X_train,
            labels=y_train,
            version_tag=tag
        )

        # Evaluate on held-out test split
        from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
        y_eval_pred = [model_runner.predict("lead_scoring_model", s) for s in X_eval]
        y_eval_proba = [model_runner.predict_proba("lead_scoring_model", s) for s in X_eval]

        eval_acc = float(accuracy_score(y_eval, y_eval_pred))
        eval_prec = float(precision_score(y_eval, y_eval_pred, zero_division=0))
        eval_rec = float(recall_score(y_eval, y_eval_pred, zero_division=0))
        try:
            eval_auc = float(roc_auc_score(y_eval, y_eval_proba))
        except Exception:
            eval_auc = 0.5

        eval_metrics = {
            "test_accuracy": round(eval_acc, 4),
            "test_precision": round(eval_prec, 4),
            "test_recall": round(eval_rec, 4),
            "test_roc_auc": round(eval_auc, 4),
            "train_samples": len(X_train),
            "eval_samples": len(X_eval)
        }

        # Persist new ModelVersion record in database
        mv = ModelVersion(
            name="lead_scoring_model",
            version_tag=tag,
            model_type="scikit_learn_logistic_pipeline",
            parameters={"class_weight": "balanced", "random_state": 42},
            training_metrics={**train_result["metrics"], **eval_metrics},
            status=ModelStatus.ACTIVE.value
        )
        session.add(mv)
        await session.commit()

        logger.info(f"[TrainingPipeline] Successfully trained and registered '{tag}': Eval Accuracy={eval_acc:.2f}, AUC={eval_auc:.2f}")

        return {
            "status": "TRAINED_MODEL",
            "model_version": tag,
            "train_metrics": train_result["metrics"],
            "evaluation_metrics": eval_metrics,
            "total_samples": len(samples),
            "positive_conversions": pos_count
        }

training_pipeline = TrainingPipeline()
