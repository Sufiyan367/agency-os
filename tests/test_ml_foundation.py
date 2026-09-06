import pytest
import uuid
from datetime import datetime
from sqlalchemy import select
from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import (
    ModelVersion, ModelPrediction, Experiment, Outcome,
    ModelStatus, ExperimentStatus
)

@pytest.mark.asyncio
async def test_ml_models_table_creation_and_persistence():
    await init_db()
    async with AsyncSessionLocal() as session:
        # 1. Create a ModelVersion
        version_tag = f"v1.0-test-{uuid.uuid4().hex[:6]}"
        mv = ModelVersion(
            name="lead_scoring_model",
            version_tag=version_tag,
            model_type="deterministic_baseline",
            parameters={"threshold": 55.0, "contact_multiplier": 0.4},
            training_metrics={"baseline_accuracy": 0.90},
            status=ModelStatus.ACTIVE.value
        )
        session.add(mv)
        await session.commit()
        await session.refresh(mv)
        assert mv.id is not None
        assert mv.version_tag == version_tag

        # 2. Create an Experiment
        exp_key = f"exp-{uuid.uuid4().hex[:6]}"
        exp = Experiment(
            experiment_key=exp_key,
            name="Lead Scoring Baseline vs GBDT",
            description="A/B testing heuristic scorer against empirical model",
            variants={
                "control": {"model_version": version_tag, "weight": 0.5},
                "treatment": {"model_version": "v2.0-candidate", "weight": 0.5}
            },
            status=ExperimentStatus.ACTIVE.value
        )
        session.add(exp)
        await session.commit()
        await session.refresh(exp)
        assert exp.id is not None
        assert exp.experiment_key == exp_key

        # 3. Create a ModelPrediction
        pred_id = f"PRED-{uuid.uuid4().hex[:8].upper()}"
        features_payload = {
            "performance_score": 45.0,
            "seo_score": 52.0,
            "ability_to_pay": 75.0,
            "gdp_per_capita": 65000.0,
            "has_verified_email": 1
        }
        pred = ModelPrediction(
            prediction_id=pred_id,
            model_name="lead_scoring_model",
            model_version=version_tag,
            entity_type="business",
            entity_id=101,
            prediction_type="lead_score",
            predicted_value=78.5,
            confidence_score=0.88,
            features=features_payload,
            is_baseline=True,
            metadata_json={"niche": "roofing-contractors", "country": "US"}
        )
        session.add(pred)
        await session.commit()
        await session.refresh(pred)
        assert pred.id is not None
        assert pred.prediction_id == pred_id
        assert pred.features["performance_score"] == 45.0
        assert pred.is_baseline is True

        # 4. Record an Outcome tied to prediction
        outcome = Outcome(
            entity_type="business",
            entity_id=101,
            prediction_id=pred_id,
            prediction=pred,
            event_name="DEAL_WON",
            value=750.0,
            metadata_json={"contract_id": "CNT-999"}
        )
        session.add(outcome)
        await session.commit()
        await session.refresh(outcome)
        assert outcome.id is not None
        assert outcome.value == 750.0
        assert outcome.event_name == "DEAL_WON"

    # 5. Verify query relationship and join integrity in clean session
    async with AsyncSessionLocal() as query_session:
        q = select(ModelPrediction).where(ModelPrediction.prediction_id == pred_id)
        saved_pred = (await query_session.execute(q)).scalar_one()
        assert len(saved_pred.outcomes) == 1
        assert saved_pred.outcomes[0].value == 750.0
        assert saved_pred.version_record.name == "lead_scoring_model"
