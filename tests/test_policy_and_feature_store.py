import pytest
import uuid
from unittest.mock import patch, AsyncMock
from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import (
    Business, AuditRun, AuditFinding, Country, Niche, PipelineStage, VerificationStatus
)
from app.ml.policy_engine import policy_engine, PolicyAction, PolicyDecision
from app.ml.feature_store import feature_store, FEATURE_NAMES
from app.core.config import settings

@pytest.mark.asyncio
async def test_policy_engine_commercial_floor():
    # 1. Below floor
    d_under = policy_engine.evaluate_commercial_value(499.0)
    assert d_under.allowed is False
    assert d_under.is_blocked is True
    assert "COMMERCIAL_FLOOR_VIOLATION" in d_under.reason

    # 2. Exactly at floor
    d_at = policy_engine.evaluate_commercial_value(500.0)
    assert d_at.allowed is True
    assert d_at.is_blocked is False

    # 3. Above floor
    d_above = policy_engine.evaluate_commercial_value(1200.0)
    assert d_above.allowed is True
    assert d_above.is_blocked is False

@pytest.mark.asyncio
async def test_policy_engine_outreach_evaluations():
    await init_db()
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        id=9901,
        name=f"Policy Test HVAC {uid}",
        domain=f"policytest-{uid}.com",
        public_email=f"info@policytest-{uid}.com",
        phone="+1-512-555-0199",
        pipeline_stage=PipelineStage.AUDITED.value,
        verification_status=VerificationStatus.VERIFIED.value
    )

    async with AsyncSessionLocal() as session:
        # A. Normal valid outreach with >= $500 offer
        with patch("app.outreach.compliance.compliance_guard.is_suppressed", new_callable=AsyncMock, return_value=False), \
             patch("app.outreach.compliance.compliance_guard.can_send_today", new_callable=AsyncMock, return_value=True):
            decision = await policy_engine.evaluate_outreach(session, biz, offer_price=650.0)
            assert decision.allowed is True
            assert "approved" in decision.reason.lower()

        # B. Low-value offer (< $500)
        with patch("app.outreach.compliance.compliance_guard.is_suppressed", new_callable=AsyncMock, return_value=False), \
             patch("app.outreach.compliance.compliance_guard.can_send_today", new_callable=AsyncMock, return_value=True):
            decision_low = await policy_engine.evaluate_outreach(session, biz, offer_price=350.0)
            assert decision_low.allowed is False
            assert any("below mandatory $500" in v for v in decision_low.violations)

        # C. Kill switch active
        with patch.object(settings, "AUTONOMOUS_AGENT_ENABLED", False), \
             patch("app.outreach.compliance.compliance_guard.is_suppressed", new_callable=AsyncMock, return_value=False), \
             patch("app.outreach.compliance.compliance_guard.can_send_today", new_callable=AsyncMock, return_value=True):
            decision_kill = await policy_engine.evaluate_outreach(session, biz, offer_price=750.0)
            assert decision_kill.allowed is False
            assert any("Emergency kill switch is currently active" in v for v in decision_kill.violations)

        # D. Human takeover active
        biz.human_takeover = True
        with patch("app.outreach.compliance.compliance_guard.is_suppressed", new_callable=AsyncMock, return_value=False), \
             patch("app.outreach.compliance.compliance_guard.can_send_today", new_callable=AsyncMock, return_value=True):
            decision_takeover = await policy_engine.evaluate_outreach(session, biz, offer_price=750.0)
            assert decision_takeover.allowed is False
            assert any("Human takeover is active" in v for v in decision_takeover.violations)
        biz.human_takeover = False

        # E. Suppression list match
        with patch("app.outreach.compliance.compliance_guard.is_suppressed", new_callable=AsyncMock, return_value=True), \
             patch("app.outreach.compliance.compliance_guard.can_send_today", new_callable=AsyncMock, return_value=True):
            decision_supp = await policy_engine.evaluate_outreach(session, biz, offer_price=750.0)
            assert decision_supp.allowed is False
            assert any("suppression" in v.lower() for v in decision_supp.violations)

        # F. Missing contact details
        biz_no_contact = Business(
            id=9902,
            name="No Contact Biz",
            domain="nocontact.com",
            public_email=None,
            phone=None
        )
        with patch("app.outreach.compliance.compliance_guard.is_suppressed", new_callable=AsyncMock, return_value=False), \
             patch("app.outreach.compliance.compliance_guard.can_send_today", new_callable=AsyncMock, return_value=True):
            decision_nocontact = await policy_engine.evaluate_outreach(session, biz_no_contact, offer_price=750.0)
            assert decision_nocontact.allowed is False
            assert any("No verified contact information available" in v for v in decision_nocontact.violations)

@pytest.mark.asyncio
async def test_policy_engine_payment_and_invariants():
    # 1. Under floor payment
    d1 = policy_engine.evaluate_payment(amount_usd=250.0)
    assert d1.allowed is False
    assert any("below commercial floor" in v for v in d1.violations)

    # 2. Live payment requested without settings enabled
    with patch.object(settings, "PAYMENTS_ENABLED", False), \
         patch.object(settings, "PAYMENT_DRY_RUN", True):
        d2 = policy_engine.evaluate_payment(amount_usd=750.0, is_live_requested=True)
        assert d2.allowed is False
        assert len(d2.violations) >= 1

    # 3. Valid dry run payment
    d3 = policy_engine.evaluate_payment(amount_usd=750.0, is_live_requested=False)
    assert d3.allowed is True

    # 4. Safety invariants check
    status = policy_engine.get_safety_invariants_status()
    assert status["commercial_floor_usd"] >= 500.0
    assert "email_dry_run" in status
    assert "payment_dry_run" in status
    assert "voice_dry_run" in status

@pytest.mark.asyncio
async def test_feature_store_extraction_and_vectorization():
    biz = Business(
        id=101,
        name="Apex Roofing Dallas",
        domain="apexroofingdallas.com",
        public_email="service@apexroofingdallas.com",
        email_status="verified",
        phone="+1-214-555-0144",
        social_profiles={"facebook": "https://facebook.com/apex"}
    )
    audit = AuditRun(
        id=501,
        business_id=101,
        performance_score=42.0,
        seo_score=58.0,
        a11y_score=64.0,
        ux_conversion_score=45.0,
        overall_health_score=52.0,
        metrics={"load_time_seconds": 4.8}
    )
    country = Country(
        code="US",
        name="United States",
        gdp_per_capita=72000.0,
        business_density_score=65.0
    )
    niche = Niche(
        slug="roofing-contractors",
        name="Roofing Contractors",
        avg_deal_size=950.0,
        digital_weakness_factor=68.0,
        service_fit_score=85.0
    )

    # 1. Extraction with full context
    features = feature_store.extract_features(biz, audit=audit, country=country, niche=niche)
    assert len(features) == len(FEATURE_NAMES)
    assert features["performance_score"] == 42.0
    assert features["seo_score"] == 58.0
    assert features["gdp_per_capita"] == 72000.0
    assert features["niche_avg_deal_size"] == 950.0
    assert features["has_verified_email"] == 1.0
    assert features["has_phone"] == 1.0
    assert features["has_social_presence"] == 1.0
    assert features["contactability_score"] == 100.0

    # 2. Vectorization
    vec = feature_store.to_vector(features)
    assert len(vec) == len(FEATURE_NAMES)
    assert isinstance(vec[0], float)

    # 3. Normalization
    norm = feature_store.normalize(features)
    for k, v in norm.items():
        assert 0.0 <= v <= 1.0, f"Feature {k} with value {v} outside [0.0, 1.0]"

    # 4. Fallback extraction when audit and country/niche are None
    fallback_features = feature_store.extract_features(biz, audit=None, country=None, niche=None)
    assert len(fallback_features) == len(FEATURE_NAMES)
    assert fallback_features["overall_health_score"] == 50.0
    assert fallback_features["gdp_per_capita"] == 65000.0
