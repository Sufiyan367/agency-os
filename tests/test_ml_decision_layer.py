import pytest
import math
import uuid
from datetime import datetime
from unittest.mock import patch, AsyncMock

from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import (
    Business, AuditRun, Country, Niche, PipelineStage, VerificationStatus,
    ModelPrediction, ModelVersion
)
from app.ml.feature_store import feature_store, FEATURE_NAMES
from app.ml.baseline_scorer import baseline_scorer, BaselineScorer
from app.ml.model_runner import model_runner, ModelRunner, SchemaValidationError
from app.ml.revenue_model import expected_revenue_model, ExpectedRevenueModel
from app.ml.prospect_ranker import prospect_ranker, ProspectRanker
from app.ml.training_pipeline import training_pipeline, TrainingPipeline
from app.core.config import settings

def _get_dummy_features() -> dict:
    """Returns a completely valid 18-feature dictionary."""
    return {
        "performance_score": 45.0,
        "seo_score": 52.0,
        "a11y_score": 60.0,
        "ux_conversion_score": 40.0,
        "overall_health_score": 48.0,
        "load_time_seconds": 4.2,
        "critical_findings_count": 2.0,
        "high_findings_count": 3.0,
        "total_findings_count": 5.0,
        "gdp_per_capita": 68000.0,
        "niche_avg_deal_size": 850.0,
        "business_density_score": 60.0,
        "digital_weakness_factor": 65.0,
        "service_fit_score": 75.0,
        "has_verified_email": 1.0,
        "has_phone": 1.0,
        "has_social_presence": 1.0,
        "contactability_score": 90.0
    }

def test_feature_schema_validation():
    runner = ModelRunner()
    valid_feats = _get_dummy_features()

    # 1. Valid features pass
    runner.validate_feature_schema(valid_feats)

    # 2. Missing feature fails closed
    incomplete_feats = dict(valid_feats)
    del incomplete_feats["performance_score"]
    with pytest.raises(SchemaValidationError) as exc:
        runner.validate_feature_schema(incomplete_feats)
    assert "Missing 1 required features" in str(exc.value)

    # 3. None feature fails closed (never invent missing values)
    none_feats = dict(valid_feats)
    none_feats["seo_score"] = None
    with pytest.raises(SchemaValidationError) as exc:
        runner.validate_feature_schema(none_feats)
    assert "strictly prohibited" in str(exc.value)

    # 4. Non-numeric feature fails closed
    str_feats = dict(valid_feats)
    str_feats["load_time_seconds"] = "4.2s"
    with pytest.raises(SchemaValidationError) as exc:
        runner.validate_feature_schema(str_feats)
    assert "must be numeric" in str(exc.value)

    # 5. Non-finite feature (NaN/Inf) fails closed
    nan_feats = dict(valid_feats)
    nan_feats["ux_conversion_score"] = float("nan")
    with pytest.raises(SchemaValidationError) as exc:
        runner.validate_feature_schema(nan_feats)
    assert "non-finite" in str(exc.value)

    # 6. Non-dict input fails closed
    with pytest.raises(SchemaValidationError):
        runner.validate_feature_schema(["not", "a", "dict"])

def test_deterministic_baseline_scoring():
    scorer = BaselineScorer()
    feats = _get_dummy_features()

    res = scorer.predict(feats)

    # Check that all 5 explicit scores exist
    assert "quality_score" in res
    assert "conversion_score" in res
    assert "commercial_fit_score" in res
    assert "contactability_score" in res
    assert "total_score" in res

    # Verify score ranges 0-100
    assert 0.0 <= res["quality_score"] <= 100.0
    assert 0.0 <= res["conversion_score"] <= 100.0
    assert 0.0 <= res["commercial_fit_score"] <= 100.0
    assert 0.0 <= res["contactability_score"] <= 100.0
    assert 0.0 <= res["total_score"] <= 100.0

    # Verify calibrated probability
    assert 0.02 <= res["probability_of_conversion"] <= 0.95
    assert res["priority"] in ("A", "B", "C", "LOW")

    # Verify explainability
    assert "explainability" in res
    assert len(res["explainability"]["drivers"]) > 0
    assert "quality" in res["explainability"]["formula"]
    assert "rationale" in res["explainability"]

def test_expected_revenue_model_and_commercial_floor():
    rev_model = ExpectedRevenueModel()

    # 1. Above floor ($750 offer)
    eval_above = rev_model.evaluate_deal_potential(
        probability_win=0.60,
        proposed_price_usd=750.0,
        niche_avg_deal_size=750.0,
        data_source="BASELINE"
    )
    assert eval_above["meets_commercial_floor"] is True
    assert eval_above["expected_revenue_usd"] == 450.0  # 0.60 * 750
    assert eval_above["confidence_metadata"]["data_source"] == "BASELINE"
    assert eval_above["confidence_metadata"]["is_uncertain"] is False

    # 2. Below commercial floor ($300 offer) -> strictly clamped and disqualified
    eval_below = rev_model.evaluate_deal_potential(
        probability_win=0.60,
        proposed_price_usd=300.0,
        niche_avg_deal_size=750.0,
        data_source="COLD_START"
    )
    assert eval_below["meets_commercial_floor"] is False
    assert eval_below["commercial_tier"] == "DISQUALIFIED_BELOW_FLOOR"
    assert eval_below["commercial_price_usd"] >= 500.0
    assert eval_below["recommended_price_usd"] >= 500.0
    assert eval_below["confidence_metadata"]["is_uncertain"] is True
    assert eval_below["confidence_metadata"]["data_source"] == "COLD_START"

def test_scikit_learn_model_training_and_inference():
    runner = ModelRunner()
    base_feat = _get_dummy_features()

    # Generate 10 synthetic samples with variations
    samples = []
    labels = []
    for i in range(10):
        s = dict(base_feat)
        s["performance_score"] = float(30 + i * 5)
        s["contactability_score"] = float(50 + i * 5)
        samples.append(s)
        labels.append(1 if i % 2 == 0 else 0)

    # Train model
    res = runner.train_model(
        samples=samples,
        labels=labels,
        model_name="test_model",
        version_tag="v2.0.0-test"
    )
    assert res["status"] == "TRAINED_MODEL"
    assert "metrics" in res
    assert "accuracy" in res["metrics"]

    # Inference: predict & predict_proba
    pred_cls = runner.predict("test_model", base_feat)
    assert pred_cls in (0, 1)

    prob = runner.predict_proba("test_model", base_feat)
    assert 0.02 <= prob <= 0.95

def test_invalid_model_rejection():
    runner = ModelRunner()
    feats = _get_dummy_features()

    # Non-existent model fails closed
    with pytest.raises(ValueError) as exc:
        runner.predict("non_existent_model", feats)
    assert "No active model found" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        runner.predict_proba("non_existent_model", feats)
    assert "No active model found" in str(exc.value)

    # Incomplete features fail closed before prediction
    incomplete = dict(feats)
    del incomplete["seo_score"]
    with pytest.raises(SchemaValidationError):
        runner.predict("non_existent_model", incomplete)

def test_target_leakage_prevention():
    pipeline = TrainingPipeline()

    # Valid feature set passes leakage check
    valid = _get_dummy_features()
    pipeline.verify_no_target_leakage(valid)

    # Leaked post-outreach attributes fail closed
    leaked_1 = dict(valid)
    leaked_1["pipeline_stage"] = "WON"
    with pytest.raises(ValueError) as exc1:
        pipeline.verify_no_target_leakage(leaked_1)
    assert "Target leakage violation" in str(exc1.value)

    leaked_2 = dict(valid)
    leaked_2["payment_status"] = "ADVANCE_PAID"
    with pytest.raises(ValueError) as exc2:
        pipeline.verify_no_target_leakage(leaked_2)
    assert "Target leakage violation" in str(exc2.value)

def test_prospect_ranker_multi_criteria_stability():
    ranker = ProspectRanker()

    # Prospect A: Huge deal value ($10,000 -> expected revenue $1,000) BUT terrible contactability & low quality
    prospect_a = {
        "business_id": 101,
        "name": "High Dollar Low Contact Corp",
        "expected_revenue": 900.0,
        "lead_quality": 20.0,
        "contactability": 15.0,
        "service_fit": 30.0,
        "audit_severity": 10.0
    }

    # Prospect B: Moderate expected revenue ($450.00) BUT verified direct contact & severe audit deficit
    prospect_b = {
        "business_id": 102,
        "name": "Balanced Prime Prospect",
        "expected_revenue": 450.0,
        "lead_quality": 95.0,
        "contactability": 100.0,
        "service_fit": 85.0,
        "audit_severity": 80.0
    }

    ranked = ranker.rank_prospects([prospect_a, prospect_b])

    # Balanced prospect must outrank the low-contact high-revenue trap
    assert ranked[0]["business_id"] == 102
    assert ranked[0]["rank"] == 1
    assert ranked[1]["business_id"] == 101
    assert ranked[1]["rank"] == 2

    # Check human-readable explanation
    assert "Rank #1" in ranked[0]["ranking_explanation"]
    assert "Rank #2" in ranked[1]["ranking_explanation"]

@pytest.mark.asyncio
async def test_cold_start_behavior_and_fallback():
    await init_db()
    async with AsyncSessionLocal() as session:
        # Run training pipeline when database has insufficient conversion outcomes
        # Should return COLD_START rather than fitting a dummy model
        with patch.object(training_pipeline, "build_dataset_from_db", new_callable=AsyncMock) as mock_data:
            mock_data.return_value = (
                [_get_dummy_features() for _ in range(3)],  # only 3 samples
                [1, 0, 0],
                [1, 2, 3]
            )
            result = await training_pipeline.run_training(session)
            assert result["status"] == "COLD_START"
            assert result["model_mode"] == "BASELINE"
            assert "Insufficient historical conversion data" in result["reason"]

@pytest.mark.asyncio
async def test_score_and_evaluate_lead_persistence_and_no_secrets():
    await init_db()
    uid = uuid.uuid4().hex[:6]

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"ML Eval Client {uid}",
            domain=f"mleval-{uid}.com",
            country="US",
            niche="HVAC",
            public_email=f"info@mleval-{uid}.com",
            pipeline_stage=PipelineStage.CONTACTED.value,
            verification_status=VerificationStatus.VERIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Run lead scoring & evaluation
        eval_res = await model_runner.score_and_evaluate_lead(
            session=session,
            business=biz,
            deal_value_usd=650.0
        )

        assert eval_res["score"] > 0.0
        assert eval_res["probability_win"] > 0.0
        assert eval_res["model_status"] in ("BASELINE", "TRAINED_MODEL", "COLD_START")
        assert eval_res["expected_revenue"]["meets_commercial_floor"] is True

        # Verify database ModelPrediction record
        from sqlalchemy import select
        q_pred = select(ModelPrediction).where(
            ModelPrediction.prediction_id == eval_res["prediction_id"]
        )
        pred_db = (await session.execute(q_pred)).scalar_one_or_none()
        assert pred_db is not None
        assert pred_db.entity_id == biz.id
        assert pred_db.prediction_type == "lead_score"
        
        # Verify no secret or credential is stored in features
        for k in pred_db.features.keys():
            assert not any(sec in k.lower() for sec in ["secret", "password", "token", "key", "auth"])

@pytest.mark.asyncio
async def test_ml_api_endpoints():
    from httpx import AsyncClient, ASGITransport
    from app.api.app import app
    from app.core.security import create_session_token

    await init_db()
    uid = uuid.uuid4().hex[:6]

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"API Lead {uid}",
            domain=f"apilead-{uid}.com",
            country="US",
            niche="Plumbing",
            public_email=f"contact@apilead-{uid}.com",
            pipeline_stage=PipelineStage.AUDITED.value,
            verification_status=VerificationStatus.VERIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        lead_id = biz.id

    token = create_session_token("admin", role="admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("agency_session", token)

        # 1. GET /api/ml/status
        resp_status = await client.get("/api/ml/status")
        assert resp_status.status_code == 200
        data_status = resp_status.json()
        assert data_status["status"] == "OPERATIONAL"
        assert data_status["model_mode"] in ("BASELINE", "TRAINED_MODEL")
        assert data_status["commercial_floor_usd"] == 500.0
        assert data_status["safety_gates"]["email_dry_run"] is True

        # 2. GET /api/ml/prospects/ranked
        resp_ranked = await client.get("/api/ml/prospects/ranked?limit=10")
        assert resp_ranked.status_code == 200
        data_ranked = resp_ranked.json()
        assert "ranked_prospects" in data_ranked
        assert len(data_ranked["ranked_prospects"]) > 0
        first = data_ranked["ranked_prospects"][0]
        assert "rank" in first
        assert "composite_score" in first
        assert "ranking_explanation" in first

        # 3. POST /api/ml/predict/{lead_id}
        resp_pred = await client.post(f"/api/ml/predict/{lead_id}")
        assert resp_pred.status_code == 200
        data_pred = resp_pred.json()
        assert "score" in data_pred
        assert "probability_win" in data_pred
        assert "expected_revenue" in data_pred

        # 4. GET /api/leads/{lead_id} includes ml_intelligence
        resp_lead = await client.get(f"/api/leads/{lead_id}")
        assert resp_lead.status_code == 200
        data_lead = resp_lead.json()
        assert "ml_intelligence" in data_lead
        assert data_lead["ml_intelligence"] is not None
        assert data_lead["ml_intelligence"]["model_status"] in ("BASELINE", "TRAINED_MODEL")

        # 5. POST /api/ml/train (triggers training pipeline)
        resp_train = await client.post("/api/ml/train")
        assert resp_train.status_code == 200
        data_train = resp_train.json()
        assert data_train["status"] in ("COLD_START", "TRAINED_MODEL")

