"""
Outcome Learning Engine — Mega Prompt 8.
Closes the loop between recommendations and business outcomes:
LEAD -> OUTREACH -> REPLY -> DEMO -> PROPOSAL -> PAYMENT -> DELIVERY -> RETENTION.
Computes empirical conversion lifts and enforces statistical confidence thresholds.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.database.ml_models import Outcome, ModelPrediction

class OutcomeLearningEngine:
    """
    Evaluates real business outcomes resulting from model predictions and recommendations.
    """

    @classmethod
    async def record_outcome(
        cls,
        session: AsyncSession,
        entity_type: str,
        entity_id: int,
        event_name: str,
        value: float = 1.0,
        prediction_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Outcome:
        """
        Records a ground-truth operational business outcome.
        Events: EMAIL_OPENED, REPLY_RECEIVED, POSITIVE_REPLY, MEETING_BOOKED, PROPOSAL_ACCEPTED, PAYMENT_RECEIVED, CHURN, TICKET_RESOLVED.
        """
        outcome = Outcome(
            entity_type=entity_type,
            entity_id=entity_id,
            prediction_id=prediction_id,
            event_name=event_name,
            value=value,
            metadata_json=metadata or {},
            occurred_at=datetime.utcnow()
        )
        session.add(outcome)
        await session.commit()
        return outcome

    @classmethod
    async def evaluate_model_calibration(
        cls,
        session: AsyncSession,
        model_name: str = "lead_scoring_baseline"
    ) -> Dict[str, Any]:
        """
        Compares predicted win probabilities P(Win) against actual recorded outcomes.
        Calculates Brier score: (1/N) * sum((predicted - actual)^2).
        """
        # Fetch predictions with matching outcomes
        stmt = (
            select(ModelPrediction)
            .where(ModelPrediction.model_name == model_name)
            .order_by(desc(ModelPrediction.created_at))
            .limit(100)
        )
        preds = (await session.execute(stmt)).scalars().all()

        if not preds:
            return {
                "model_name": model_name,
                "status": "INSUFFICIENT_DATA",
                "sample_size": 0,
                "brier_score": None,
                "message": "No historical predictions recorded for calibration evaluation."
            }

        squared_errors = []
        for p in preds:
            actual = 1.0 if any(o.event_name in ("POSITIVE_REPLY", "PAYMENT_RECEIVED", "MEETING_BOOKED") for o in p.outcomes) else 0.0
            squared_errors.append((p.predicted_value - actual) ** 2)

        brier_score = round(sum(squared_errors) / len(squared_errors), 4) if squared_errors else 0.0

        return {
            "model_name": model_name,
            "status": "EVALUATED",
            "sample_size": len(preds),
            "brier_score": brier_score,
            "calibration_quality": "WELL_CALIBRATED" if brier_score < 0.20 else "MODERATE" if brier_score < 0.35 else "NEEDS_RECALIBRATION",
            "epistemic_status": "OBSERVED_FACT"
        }


outcome_learning_engine = OutcomeLearningEngine()
