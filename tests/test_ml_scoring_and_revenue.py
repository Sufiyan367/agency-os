import pytest
import uuid
from sqlalchemy import select
from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import (
    Business, AuditRun, Country, Niche, ModelPrediction, ModelVersion
)
from app.ml.scoring_model import deterministic_scoring_model
from app.ml.revenue_model import expected_revenue_model
from app.ml.model_runner import model_runner
from app.ml.feature_store import feature_store

@pytest.mark.asyncio
async def test_deterministic_scoring_model_evaluation():
    # 1. High opportunity prospect (severe performance & conversion deficits, high capacity)
    features_high = {
        "performance_score": 25.0,
        "seo_score": 30.0,
        "a11y_score": 40.0,
        "ux_conversion_score": 20.0,
        "overall_health_score": 30.0,
        "gdp_per_capita": 85000.0,
        "niche_avg_deal_size": 1200.0,
        "contactability_score": 100.0
    }
    res_high = deterministic_scoring_model.predict(features_high)
    assert res_high["score"] >= 70.0
    assert res_high["priority"] in ("A", "B")
    assert res_high["probability_win"] > 0.50
    assert res_high["is_baseline"] is True
    assert len(res_high["drivers"]) > 0
    assert "High conversion friction" in res_high["rationale"] or "Core Web Vitals deficit" in res_high["rationale"]

    # 2. Low opportunity prospect (already optimized, low capacity)
    features_low = {
        "performance_score": 95.0,
        "seo_score": 90.0,
        "a11y_score": 95.0,
        "ux_conversion_score": 90.0,
        "overall_health_score": 92.0,
        "gdp_per_capita": 30000.0,
        "niche_avg_deal_size": 400.0,
        "contactability_score": 20.0
    }
    res_low = deterministic_scoring_model.predict(features_low)
    assert res_low["score"] < 50.0
    assert res_low["priority"] == "LOW"
    assert res_low["probability_win"] < 0.30

@pytest.mark.asyncio
async def test_expected_revenue_model_evaluations():
    # 1. Below floor price ($350)
    rev_under = expected_revenue_model.evaluate_deal_potential(
        probability_win=0.70, proposed_price_usd=350.0
    )
    assert rev_under["meets_commercial_floor"] is False
    assert rev_under["commercial_tier"] == "DISQUALIFIED_BELOW_FLOOR"
    assert rev_under["commercial_price_usd"] == 500.0  # Clamped to floor
    assert rev_under["expected_revenue_usd"] == round(0.70 * 500.0, 2)

    # 2. High-value deal ($1200, 60% win prob)
    rev_high = expected_revenue_model.evaluate_deal_potential(
        probability_win=0.60, proposed_price_usd=1200.0
    )
    assert rev_high["meets_commercial_floor"] is True
    assert rev_high["commercial_tier"] == "TIER_1_HIGH_VALUE"
    assert rev_high["expected_revenue_usd"] == 720.0
    assert rev_high["expected_profit_usd"] == round(720.0 * 0.75, 2)
    assert rev_high["roe_index"] >= 50.0

@pytest.mark.asyncio
async def test_model_runner_cold_start_and_prediction_logging():
    await init_db()
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name=f"ML Runner Test Plumbing {uid}",
        domain=f"mlrunner-{uid}.com",
        country="US",
        niche="plumbing-services",
        public_email=f"contact@mlrunner-{uid}.com",
        email_status="verified",
        phone="+1-512-555-0188"
    )
    audit = AuditRun(
        url_audited=f"https://mlrunner-{uid}.com",
        performance_score=35.0,
        seo_score=45.0,
        a11y_score=50.0,
        ux_conversion_score=30.0,
        overall_health_score=40.0,
        metrics={"load_time_seconds": 4.5}
    )
    country = Country(code="US", name="United States", gdp_per_capita=70000.0)
    niche = Niche(slug="plumbing-services", name="Plumbing", avg_deal_size=850.0)

    async with AsyncSessionLocal() as session:
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        audit.business_id = biz.id
        session.add(audit)
        await session.commit()

        # Execute scoring via model_runner
        result = await model_runner.score_and_evaluate_lead(
            session=session,
            business=biz,
            audit=audit,
            country=country,
            niche=niche,
            deal_value_usd=850.0
        )
        assert result["score"] >= 50.0
        assert result["is_baseline"] is True
        assert result["expected_revenue"]["meets_commercial_floor"] is True
        assert result["expected_revenue"]["commercial_price_usd"] == 850.0

        # Verify prediction record was persisted in database
        pred_id = result["prediction_id"]
        q = select(ModelPrediction).where(ModelPrediction.prediction_id == pred_id)
        saved_pred = (await session.execute(q)).scalar_one_or_none()
        assert saved_pred is not None
        assert saved_pred.entity_id == biz.id
        assert saved_pred.is_baseline is True
        assert saved_pred.predicted_value == result["score"]
        assert saved_pred.features["performance_score"] == 35.0

@pytest.mark.asyncio
async def test_model_runner_sklearn_training_and_inference():
    await init_db()
    # 1. Create synthetic training samples
    samples = []
    labels = []
    # Class 0: low opportunity (fast, perfect SEO, low deal size)
    for _ in range(6):
        samples.append({
            "performance_score": 95.0,
            "seo_score": 90.0,
            "a11y_score": 95.0,
            "ux_conversion_score": 90.0,
            "overall_health_score": 92.0,
            "load_time_seconds": 1.5,
            "critical_findings_count": 0.0,
            "high_findings_count": 0.0,
            "total_findings_count": 1.0,
            "gdp_per_capita": 35000.0,
            "niche_avg_deal_size": 400.0,
            "business_density_score": 30.0,
            "digital_weakness_factor": 20.0,
            "service_fit_score": 30.0,
            "has_verified_email": 0.0,
            "has_phone": 1.0,
            "has_social_presence": 0.0,
            "contactability_score": 50.0
        })
        labels.append(0)

    # Class 1: high opportunity (slow, severe deficits, verified email, high deal size)
    for _ in range(6):
        samples.append({
            "performance_score": 25.0,
            "seo_score": 30.0,
            "a11y_score": 35.0,
            "ux_conversion_score": 20.0,
            "overall_health_score": 28.0,
            "load_time_seconds": 5.5,
            "critical_findings_count": 4.0,
            "high_findings_count": 5.0,
            "total_findings_count": 12.0,
            "gdp_per_capita": 80000.0,
            "niche_avg_deal_size": 1200.0,
            "business_density_score": 75.0,
            "digital_weakness_factor": 80.0,
            "service_fit_score": 85.0,
            "has_verified_email": 1.0,
            "has_phone": 1.0,
            "has_social_presence": 1.0,
            "contactability_score": 100.0
        })
        labels.append(1)

    # 2. Train scikit-learn model
    v_tag = f"v2.0.0-test-{uuid.uuid4().hex[:6]}"
    trained_pipe = model_runner.train_baseline_classifier(samples, labels, version_tag=v_tag)
    assert trained_pipe is not None
    assert "lead_scoring_model" in model_runner.active_models

    # 3. Predict with trained model
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name=f"ML Inference Biz {uid}",
        domain=f"mlinference-{uid}.com",
        country="US",
        niche="roofing-contractors",
        public_email=f"ceo@mlinference-{uid}.com",
        email_status="verified",
        phone="+1-512-555-0177"
    )
    async with AsyncSessionLocal() as session:
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        res = await model_runner.score_and_evaluate_lead(session=session, business=biz)
        assert res["is_baseline"] is False
        assert res["version_tag"] == v_tag
        assert "ML Model" in res["rationale"]

    # Reset active models back to cold start baseline
    model_runner.active_models.clear()
