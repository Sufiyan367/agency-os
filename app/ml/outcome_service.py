import enum
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.database.ml_models import Outcome, ModelPrediction
from app.core.logging import logger

class LifecycleEvent(str, enum.Enum):
    PROSPECT_CONTACTED = "PROSPECT_CONTACTED"
    REPLY_RECEIVED = "REPLY_RECEIVED"
    LEAD_QUALIFIED = "LEAD_QUALIFIED"
    PROPOSAL_SENT = "PROPOSAL_SENT"
    DEAL_WON = "DEAL_WON"
    DEAL_LOST = "DEAL_LOST"
    OPT_OUT = "OPT_OUT"
    DISQUALIFIED = "DISQUALIFIED"

WIN_EVENTS = {LifecycleEvent.DEAL_WON.value, "DEAL_WON", "PAYMENT_RECEIVED", "CONTRACT_SIGNED"}
LOSS_EVENTS = {LifecycleEvent.DEAL_LOST.value, "DEAL_LOST", "OPT_OUT", "DISQUALIFIED"}

class OutcomeService:
    """
    Manages recording of real prospect lifecycle events and provides
    temporally-safe joins between ModelPredictions and subsequent observed Outcomes.
    """

    @staticmethod
    async def record_outcome(
        session: AsyncSession,
        entity_type: str,
        entity_id: int,
        event_name: str,
        value: float = 0.0,
        prediction_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        occurred_at: Optional[datetime] = None
    ) -> Outcome:
        """
        Records a real business/lifecycle outcome in the database.
        If prediction_id is omitted, automatically finds the most recent
        prior prediction for this entity to prevent temporal leakage.
        """
        event_time = occurred_at or datetime.utcnow()
        resolved_pred_id = prediction_id

        if not resolved_pred_id:
            # Locate latest prediction for this entity created before or at occurred_at
            q = (
                select(ModelPrediction.prediction_id)
                .where(
                    and_(
                        ModelPrediction.entity_type == entity_type,
                        ModelPrediction.entity_id == entity_id,
                        ModelPrediction.created_at <= event_time
                    )
                )
                .order_by(desc(ModelPrediction.created_at))
                .limit(1)
            )
            res = await session.execute(q)
            resolved_pred_id = res.scalar_one_or_none()

        outcome = Outcome(
            entity_type=entity_type,
            entity_id=entity_id,
            prediction_id=resolved_pred_id,
            event_name=event_name,
            value=float(value or 0.0),
            metadata_json=metadata or {},
            occurred_at=event_time
        )
        session.add(outcome)
        await session.flush()
        logger.info(
            f"[OutcomeService] Recorded outcome {event_name} for {entity_type}:{entity_id} "
            f"(value={value}, linked_pred={resolved_pred_id})"
        )
        return outcome

    @staticmethod
    async def get_prediction_outcome_pairs(
        session: AsyncSession,
        model_version: Optional[str] = None,
        prediction_type: str = "lead_score",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Queries joined (Prediction, Outcome) pairs where outcome.occurred_at >= prediction.created_at.
        Returns frozen pre-prediction feature snapshots, predicted values, and observed ground truth.
        Guarantees zero temporal data leakage.
        """
        query = (
            select(ModelPrediction, Outcome)
            .join(Outcome, ModelPrediction.prediction_id == Outcome.prediction_id)
            .where(
                and_(
                    ModelPrediction.prediction_type == prediction_type,
                    Outcome.occurred_at >= ModelPrediction.created_at
                )
            )
            .order_by(ModelPrediction.created_at.asc(), Outcome.occurred_at.asc())
        )

        if model_version:
            query = query.where(ModelPrediction.model_version == model_version)
        if start_time:
            query = query.where(ModelPrediction.created_at >= start_time)
        if end_time:
            query = query.where(ModelPrediction.created_at <= end_time)

        result = await session.execute(query)
        rows = result.all()

        # Group by prediction_id so multiple subsequent outcomes resolve to a definitive state
        grouped: Dict[str, Dict[str, Any]] = {}
        for pred, outcome in rows:
            pid = pred.prediction_id
            is_win = outcome.event_name in WIN_EVENTS
            is_loss = outcome.event_name in LOSS_EVENTS

            if pid not in grouped:
                grouped[pid] = {
                    "prediction_id": pid,
                    "model_version": pred.model_version,
                    "entity_type": pred.entity_type,
                    "entity_id": pred.entity_id,
                    "prediction_created_at": pred.created_at,
                    "predicted_value": float(pred.predicted_value or 0.0),
                    "confidence_score": float(pred.confidence_score or 0.0),
                    "features": dict(pred.features or {}),
                    "is_baseline": pred.is_baseline,
                    "metadata": dict(pred.metadata_json or {}),
                    "outcomes": [],
                    "is_won": 1 if is_win else (0 if is_loss else None),
                    "actual_value": float(outcome.value or 0.0),
                    "latest_event": outcome.event_name,
                    "latest_outcome_at": outcome.occurred_at
                }
            else:
                entry = grouped[pid]
                if is_win:
                    entry["is_won"] = 1
                    entry["actual_value"] = max(entry["actual_value"], float(outcome.value or 0.0))
                elif is_loss and entry["is_won"] is None:
                    entry["is_won"] = 0
                if outcome.occurred_at >= entry["latest_outcome_at"]:
                    entry["latest_event"] = outcome.event_name
                    entry["latest_outcome_at"] = outcome.occurred_at

            grouped[pid]["outcomes"].append({
                "outcome_id": outcome.id,
                "event_name": outcome.event_name,
                "value": float(outcome.value or 0.0),
                "occurred_at": outcome.occurred_at,
                "metadata": outcome.metadata_json
            })

        return list(grouped.values())

outcome_service = OutcomeService()
