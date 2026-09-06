import pytest
import numpy as np
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport

from app.api.app import app
from app.ml.outcome_service import outcome_service, LifecycleEvent
from app.ml.evaluator import (
    ModelEvaluator, MIN_OUTCOMES_FOR_EVALUATION, MIN_WINS_FOR_MODELING, MIN_SAMPLES_FOR_RETRAINING
)
from app.ml.drift_monitor import (
    calculate_psi, feature_drift_monitor, prediction_drift_monitor, performance_drift_monitor
)
from app.ml.data_quality import data_quality_monitor
from app.ml.retraining_policy import retraining_policy
from app.ml.health_service import model_health_service
from app.ml.model_runner import model_runner
from app.database.models import Business, ModelPrediction

@pytest.mark.asyncio
async def test_outcome_recording_and_temporal_join(db_session):
    """
    Validates that real lifecycle outcomes can be recorded and temporally joined
    with prior predictions without data leakage.
    """
    # 1. Create a prospect and record a prediction
    biz = Business(
        name="Apex Industrial Logistics",
        domain="apex-logistics.test",
        country="US",
        niche="Logistics",
        city="Chicago"
    )
    db_session.add(biz)
    await db_session.flush()

    pred_time = datetime.utcnow() - timedelta(days=5)
    pred = ModelPrediction(
        prediction_id="PRED-TEST-APEX-001",
        model_name="lead_scoring_model",
        model_version="v1.0.0-deterministic-heuristic",
        entity_type="business",
        entity_id=biz.id,
        prediction_type="lead_score",
        predicted_value=88.5,
        confidence_score=0.88,
        features={"performance_score": 75.0, "digital_weakness_factor": 60.0},
        is_baseline=True,
        created_at=pred_time
    )
    db_session.add(pred)
    await db_session.flush()

    # 2. Record subsequent lifecycle outcomes
    outcome1 = await outcome_service.record_outcome(
        session=db_session,
        entity_type="business",
        entity_id=biz.id,
        event_name=LifecycleEvent.PROSPECT_CONTACTED.value,
        occurred_at=pred_time + timedelta(days=1)
    )
    assert outcome1.prediction_id == "PRED-TEST-APEX-001"

    outcome2 = await outcome_service.record_outcome(
        session=db_session,
        entity_type="business",
        entity_id=biz.id,
        event_name=LifecycleEvent.DEAL_WON.value,
        value=3500.0,
        occurred_at=pred_time + timedelta(days=3)
    )
    assert outcome2.prediction_id == "PRED-TEST-APEX-001"

    # 3. Retrieve joined pairs and verify no temporal leakage
    pairs = await outcome_service.get_prediction_outcome_pairs(session=db_session)
    matching = [p for p in pairs if p["prediction_id"] == "PRED-TEST-APEX-001"]
    assert len(matching) == 1
    pair = matching[0]
    assert pair["is_won"] == 1
    assert pair["actual_value"] == 3500.0
    assert pair["predicted_value"] == 88.5
    assert pair["features"]["performance_score"] == 75.0


@pytest.mark.asyncio
async def test_cold_start_insufficient_data():
    """
    Ensures cold-start safety: if outcomes < 20 or wins < 5,
    evaluator returns INSUFFICIENT_DATA and NEVER manufactures fake metrics.
    """
    evaluator = ModelEvaluator(min_outcomes=20, min_wins=5)

    # Only 5 samples, 1 win (insufficient)
    sparse_pairs = [
        {"is_won": 1, "confidence_score": 0.85, "actual_value": 1500.0},
        {"is_won": 0, "confidence_score": 0.30, "actual_value": 0.0},
        {"is_won": 0, "confidence_score": 0.40, "actual_value": 0.0},
        {"is_won": 0, "confidence_score": 0.20, "actual_value": 0.0},
        {"is_won": 0, "confidence_score": 0.50, "actual_value": 0.0},
    ]

    report = evaluator.evaluate_predictions(sparse_pairs, model_version="test-model")
    assert report["status"] == "INSUFFICIENT_DATA"
    assert report["classification_metrics"] is None
    assert report["ranking_metrics"] is None
    assert report["sample_count"] == 5
    assert report["win_count"] == 1
    assert len(report["reasons"]) > 0


@pytest.mark.asyncio
async def test_evaluation_metrics_computation():
    """
    Verifies production evaluation calculations (ROC-AUC, F1, Precision@K,
    Brier score, calibration bins, and deal value regression) when sufficient data exists.
    """
    evaluator = ModelEvaluator(min_outcomes=20, min_wins=5)

    # Generate 30 realistic predictions: 10 wins, 20 losses
    pairs = []
    for i in range(30):
        is_win = 1 if i < 10 else 0
        conf = 0.75 + (i % 5) * 0.04 if is_win else 0.20 + (i % 5) * 0.05
        pairs.append({
            "is_won": is_win,
            "confidence_score": conf,
            "predicted_value": conf * 100.0,
            "actual_value": 2500.0 if is_win else 0.0,
            "metadata": {"expected_revenue_usd": 2400.0 if is_win else 0.0}
        })

    report = evaluator.evaluate_predictions(pairs, model_version="v2.0.0-sklearn")
    assert report["status"] == "EVALUATION_SUCCESS"
    assert report["sample_count"] == 30
    assert report["win_count"] == 10

    # Classification
    clf = report["classification_metrics"]
    assert "precision" in clf
    assert "recall" in clf
    assert "f1_score" in clf
    assert "roc_auc" in clf
    assert clf["roc_auc"] > 0.80  # Separation is clean
    assert clf["brier_score"] < 0.20

    # Ranking
    ranking = report["ranking_metrics"]
    assert "top_5" in ranking
    assert ranking["top_5"]["precision_at_k"] >= 0.80
    assert ranking["top_5"]["lift_vs_random"] > 1.5

    # Calibration
    cal = report["calibration_report"]
    assert len(cal["bins"]) == 5

    # Regression
    reg = report["regression_metrics"]
    assert reg is not None
    assert "mae_usd" in reg
    assert "rmse_usd" in reg


def test_feature_drift_psi_and_ks():
    """
    Tests PSI and Kolmogorov-Smirnov distribution drift algorithms.
    """
    np.random.seed(42)
    # 1. Identical distributions -> Normal / No drift
    ref_vals = np.random.normal(loc=50.0, scale=10.0, size=200).tolist()
    cur_vals_normal = np.random.normal(loc=50.0, scale=10.0, size=200).tolist()

    rep_normal = feature_drift_monitor.evaluate_numerical_feature("performance_score", ref_vals, cur_vals_normal)
    assert rep_normal["severity"] == "NORMAL"
    assert rep_normal["psi"] < 0.10

    # 2. Shifted distribution -> Critical drift
    cur_vals_shifted = np.random.normal(loc=85.0, scale=15.0, size=100).tolist()
    rep_shifted = feature_drift_monitor.evaluate_numerical_feature("performance_score", ref_vals, cur_vals_shifted)
    assert rep_shifted["severity"] == "CRITICAL"
    assert rep_shifted["psi"] >= 0.25
    assert rep_shifted["ks_p_value"] < 0.01


def test_prediction_drift_detection():
    """
    Tests PredictionDriftMonitor on probability distribution shifts.
    """
    ref_preds = [{"confidence_score": 0.35, "metadata": {"priority": "C"}} for _ in range(50)]
    cur_preds = [{"confidence_score": 0.85, "metadata": {"priority": "A"}} for _ in range(50)]

    drift_rep = prediction_drift_monitor.evaluate_predictions(ref_preds, cur_preds)
    assert drift_rep["status"] == "CRITICAL_DRIFT"
    assert drift_rep["probability_psi"] > 0.25
    assert drift_rep["current_priority_distribution"]["A"] == 1.0


def test_data_quality_monitor():
    """
    Tests MLDataQualityMonitor on missingness and out-of-bounds anomaly auditing.
    """
    clean_batch = [
        {
            "performance_score": 80.0, "seo_score": 85.0, "a11y_score": 90.0,
            "ux_conversion_score": 75.0, "overall_health_score": 82.0, "load_time_seconds": 2.1,
            "critical_findings_count": 0, "high_findings_count": 1, "total_findings_count": 5,
            "gdp_per_capita": 65000.0, "niche_avg_deal_size": 1500.0, "business_density_score": 80.0,
            "digital_weakness_factor": 45.0, "service_fit_score": 90.0, "has_verified_email": 1.0,
            "has_phone": 1.0, "has_social_presence": 1.0, "contactability_score": 95.0
        }
        for _ in range(20)
    ]
    rep_clean = data_quality_monitor.audit_features_batch(clean_batch)
    assert rep_clean["status"] == "HEALTHY"
    assert rep_clean["quality_score"] == 100.0

    # Degraded batch with missing and negative values
    bad_batch = [
        {"performance_score": -10.0, "seo_score": None} for _ in range(20)
    ]
    rep_bad = data_quality_monitor.audit_features_batch(bad_batch)
    assert rep_bad["status"] in ("WARNING", "CRITICAL")
    assert rep_bad["quality_score"] < 80.0


def test_model_retraining_policy():
    """
    Validates retraining trigger conditions:
    Blocks retraining if outcomes < 30 or wins < 5.
    Recommends retraining on critical drift with sufficient outcomes.
    """
    # 1. Blocked: Insufficient sample size
    sparse_outcomes = [{"is_won": 1} for _ in range(3)]
    dec1 = retraining_policy.evaluate_retraining_trigger(sparse_outcomes)
    assert dec1["decision"] == "INSUFFICIENT_DATA_FOR_RETRAINING"
    assert dec1["retrain_recommended"] is False

    # 2. Triggered: Sufficient samples + Critical Drift
    sufficient_outcomes = [{"is_won": 1 if i < 10 else 0} for i in range(35)]
    drift_critical = {"status": "CRITICAL_DRIFT"}
    dec2 = retraining_policy.evaluate_retraining_trigger(sufficient_outcomes, drift_report=drift_critical)
    assert dec2["decision"] == "RETRAIN_RECOMMENDED"
    assert dec2["retrain_recommended"] is True

    # 3. No retrain: Sufficient samples + Stable
    dec3 = retraining_policy.evaluate_retraining_trigger(sufficient_outcomes, drift_report={"status": "HEALTHY"})
    assert dec3["decision"] == "NO_RETRAIN_NEEDED"
    assert dec3["retrain_recommended"] is False


@pytest.mark.asyncio
async def test_model_runner_automated_baseline_fallback(db_session):
    """
    Proves that when model health is DEGRADED, ModelRunner autonomously
    routes inference to BaselineScorer, logging is_baseline=True and fallback_reason.
    """
    biz = Business(
        name="Fallback Diagnostic Co",
        domain="fallback-diag.test",
        country="US",
        niche="Plumbing",
        city="Dallas"
    )
    db_session.add(biz)
    await db_session.flush()

    # Simulate model degradation override
    model_runner.set_health_override("lead_scoring_model", "DEGRADED")
    try:
        features = {
            "performance_score": 60.0, "seo_score": 65.0, "a11y_score": 70.0,
            "ux_conversion_score": 65.0, "overall_health_score": 65.0, "load_time_seconds": 3.2,
            "critical_findings_count": 1, "high_findings_count": 2, "total_findings_count": 8,
            "gdp_per_capita": 62000.0, "niche_avg_deal_size": 950.0, "business_density_score": 70.0,
            "digital_weakness_factor": 50.0, "service_fit_score": 80.0, "has_verified_email": 1.0,
            "has_phone": 1.0, "has_social_presence": 1.0, "contactability_score": 85.0
        }

        res = await model_runner.score_and_evaluate_lead(
            session=db_session,
            business=biz,
            custom_features=features
        )

        assert res["is_baseline"] is True
        assert res["model_status"] == "DEGRADED_FALLBACK"
        assert res["fallback_reason"] == "MODEL_DEGRADED"
        assert "AUTOMATED FALLBACK" in res["rationale"]
    finally:
        # Clear health override
        model_runner.set_health_override("lead_scoring_model", None)


@pytest.mark.asyncio
async def test_ml_monitoring_api_endpoints():
    """
    Tests all ML monitoring API endpoints return 200 OK and valid schemas.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Health endpoint
        res_health = await ac.get("/api/ml/health")
        assert res_health.status_code == 200
        data_health = res_health.json()
        assert data_health["status"] == "SUCCESS"
        assert "composite_health_score" in data_health["health"]
        assert "active_scoring_engine" in data_health["health"]
        assert "is_fallback_active" in data_health["health"]

        # 2. Evaluation endpoint
        res_eval = await ac.get("/api/ml/evaluation")
        assert res_eval.status_code == 200
        data_eval = res_eval.json()
        assert data_eval["status"] == "SUCCESS"
        assert "status" in data_eval["evaluation"]

        # 3. Drift endpoint
        res_drift = await ac.get("/api/ml/drift")
        assert res_drift.status_code == 200
        data_drift = res_drift.json()
        assert data_drift["status"] == "SUCCESS"
        assert "feature_drift" in data_drift

        # 4. Data Quality endpoint
        res_dq = await ac.get("/api/ml/data-quality")
        assert res_dq.status_code == 200
        data_dq = res_dq.json()
        assert data_dq["status"] == "SUCCESS"
        assert "data_quality" in data_dq

        # 5. Outcome recording endpoint
        payload = {
            "entity_type": "business",
            "entity_id": 9999,
            "event_name": "PROSPECT_CONTACTED",
            "value": 0.0
        }
        res_out = await ac.post("/api/ml/outcomes", json=payload)
        assert res_out.status_code == 200
        assert res_out.json()["status"] == "SUCCESS"

        # 6. Retraining evaluate endpoint
        res_retrain = await ac.post("/api/ml/retraining/evaluate")
        assert res_retrain.status_code == 200
        assert "retraining_policy" in res_retrain.json()
