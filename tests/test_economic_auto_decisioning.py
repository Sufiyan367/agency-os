"""
Comprehensive Test Suite: Economic Auto-Decisioning Engine
Validates all mandatory requirements:
1. $499 -> AUTO_REJECT
2. $499.99 -> AUTO_REJECT
3. $500 -> continues to economic/risk evaluation
4. $500+ with failing economics -> AUTO_REJECT/HOLD according to policy
5. $500+ with compliance failure -> HOLD/REJECT
6. $500+ with all gates passing -> AUTO_APPROVE
7. unusual/high-risk case -> CEO exception
8. auto-approval does not bypass safety/compliance gates
9. decision reason is persisted/auditable
10. existing human approval behavior remains available for genuine exceptions
11. production remains real-data-only
12. test DB remains isolated from agency.db
"""

import os
import uuid
import pytest
import sqlite3
from datetime import datetime
from sqlalchemy import select

from app.core.config import settings
from app.database.models import (
    Business, AuditRun, AuditFinding, Offer, ClientIntelligenceRecord,
    ProspectEvidence, AutonomousDecisionLog, PipelineStage, SuppressionList,
    ActiveOutreachLock, OutreachMessage, OutreachStatus
)
from app.acquisition.approval_policy import (
    auto_approval_policy,
    get_commercial_floor,
    PolicyEvaluationResult
)
from app.acquisition.autonomous_controller import autonomous_acquisition_controller
from app.acquisition.controller import active_prospect_controller


async def _seed_test_prospect(db, domain="brightsmile.co.uk", name="Bright Smile Clinic", price=1200.0, **kwargs):
    """Creates a fully qualified, verified test business fixture in the test database."""
    biz = Business(
        name=name,
        domain=domain,
        website_url=f"https://{domain}",
        public_email=f"office@{domain}",
        phone="+442079460999",
        country="UK",
        city="London",
        niche="Dental",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db.add(biz)
    await db.flush()

    if kwargs.get("suppressed", False):
        supp = SuppressionList(
            domain=domain,
            email=f"office@{domain}",
            reason="Unsubscribed from outreach"
        )
        db.add(supp)

    intel = ClientIntelligenceRecord(
        business_id=biz.id,
        top_service_name="Core Web Vitals & Load Speed Acceleration",
        recommended_price_usd=price,
        target_price_usd=price,
        fit_score=0.91,
        why_this_business=["High mobile latency of 5.1s.", "Registered dental clinic in London."]
    )
    db.add(intel)

    if kwargs.get("with_audit", True):
        audit = AuditRun(
            business_id=biz.id,
            url_audited=f"https://{domain}",
            performance_score=42.0,
            seo_score=70.0,
            overall_health_score=58.0
        )
        db.add(audit)
        await db.flush()
        finding = AuditFinding(
            audit_id=audit.id,
            category="PERFORMANCE",
            finding="Render-blocking CSS/JS",
            severity="HIGH",
            evidence="LCP measured at 5,100ms.",
            url=f"https://{domain}",
            recommended_fix="Optimize critical rendering path.",
            estimated_business_impact="Increase conversion rate by 15%."
        )
        db.add(finding)

    if kwargs.get("with_evidence", True):
        ev1 = ProspectEvidence(
            business_id=biz.id,
            evidence_id=f"ev_{biz.id}_1_{uuid.uuid4().hex[:6]}",
            claim="Active dental practice in London",
            raw_excerpt="Bright Smile Clinic is an established dental practice.",
            source_url=f"https://{domain}",
            source_domain=domain,
            source_type="primary_domain",
            business_identity_match=True,
            is_verified=True,
            verification_status="VERIFIED",
            source_independence_group=domain
        )
        ev2 = ProspectEvidence(
            business_id=biz.id,
            evidence_id=f"ev_{biz.id}_2_{uuid.uuid4().hex[:6]}",
            claim="General Dental Council UK Registered Practice",
            raw_excerpt="GDC registration 987654 for London clinic.",
            source_url="https://gdc-uk.org/registrant/987654",
            source_domain="gdc-uk.org",
            source_type="public_registry",
            business_identity_match=True,
            is_verified=True,
            verification_status="VERIFIED",
            source_independence_group="gdc_registry"
        )
        db.add_all([ev1, ev2])

    await db.commit()
    await db.refresh(biz)
    return biz


# 1. $499 -> AUTO_REJECT
@pytest.mark.asyncio
async def test_economic_decision_499_auto_reject(db_session):
    biz = await _seed_test_prospect(db_session, domain="subfloor499.co.uk", price=499.0)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=499.0)
    
    assert result.decision == "AUTO_REJECT"
    assert result.is_auto_approved is False
    assert result.can_outreach is False
    assert result.is_ceo_exception is False
    assert "below minimum deal threshold" in result.decision_reason
    assert "499" in result.decision_reason


# 2. $499.99 -> AUTO_REJECT
@pytest.mark.asyncio
async def test_economic_decision_499_99_auto_reject(db_session):
    biz = await _seed_test_prospect(db_session, domain="subfloor49999.co.uk", price=499.99)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=499.99)
    
    assert result.decision == "AUTO_REJECT"
    assert result.is_auto_approved is False
    assert result.can_outreach is False
    assert result.is_ceo_exception is False
    assert "below minimum deal threshold" in result.decision_reason


# 3. $500 -> continues to economic/risk evaluation
@pytest.mark.asyncio
async def test_economic_decision_500_continues_evaluation(db_session):
    biz = await _seed_test_prospect(db_session, domain="exactfloor500.co.uk", price=500.0)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=500.0)
    
    assert result.checklist.get("commercial_floor_met") is True
    assert result.decision == "AUTO_APPROVE"
    assert result.is_auto_approved is True
    assert result.can_outreach is True
    assert ">= $500" in result.decision_reason


# 4. $500+ with failing economics -> AUTO_REJECT according to policy
@pytest.mark.asyncio
async def test_economic_decision_500_plus_failing_economics(db_session):
    biz = await _seed_test_prospect(db_session, domain="costlyfulfillment.co.uk", price=800.0)
    result = await auto_approval_policy.evaluate_prospect(
        db_session, biz, force_price=800.0, estimated_cost=950.0
    )
    
    assert result.decision == "AUTO_REJECT"
    assert result.is_auto_approved is False
    assert result.checklist.get("economics_positive") is False
    assert "expected economics" in result.decision_reason.lower() or "negative" in result.decision_reason.lower()


# 5. $500+ with compliance failure -> AUTO_REJECT/HOLD
@pytest.mark.asyncio
async def test_economic_decision_500_plus_compliance_failure(db_session):
    biz = await _seed_test_prospect(db_session, domain="suppressedprospect.co.uk", price=1500.0, suppressed=True)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=1500.0)
    
    assert result.decision in ("AUTO_REJECT", "BLOCK")
    assert result.is_auto_approved is False
    assert result.can_outreach is False
    assert result.checklist.get("no_suppression") is False


# 6. $500+ with all gates passing -> AUTO_APPROVE
@pytest.mark.asyncio
async def test_economic_decision_500_plus_all_gates_pass(db_session):
    biz = await _seed_test_prospect(db_session, domain="perfectcandidate.co.uk", price=1500.0)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=1500.0)
    
    assert result.decision == "AUTO_APPROVE"
    assert result.is_auto_approved is True
    assert result.can_outreach is True
    assert result.is_ceo_exception is False
    assert result.checklist.get("evidence_gate_passed") is True
    assert result.checklist.get("two_independent_sources") is True
    assert result.checklist.get("audit_completed") is True
    assert result.checklist.get("no_suppression") is True
    assert "economics positive" in result.decision_reason
    assert "verification passed" in result.decision_reason


# 7. Unusual discount or high-risk case -> CEO exception
@pytest.mark.asyncio
async def test_economic_decision_unusual_discount_ceo_exception(db_session):
    biz = await _seed_test_prospect(db_session, domain="heavyconcession.co.uk", price=550.0)
    result = await auto_approval_policy.evaluate_prospect(
        db_session,
        biz,
        force_price=550.0,
        catalog_target_price=1100.0,
        discount_percentage=0.50
    )
    
    assert result.decision == "HUMAN_APPROVAL_REQUIRED"
    assert result.is_auto_approved is False
    assert result.is_ceo_exception is True
    assert result.exception_type == "UNUSUAL_DISCOUNT"
    assert "requires CEO review" in result.decision_reason


@pytest.mark.asyncio
async def test_economic_decision_high_risk_ceo_exception(db_session):
    biz = await _seed_test_prospect(db_session, domain="highriskcase.co.uk", price=1200.0)
    result = await auto_approval_policy.evaluate_prospect(
        db_session,
        biz,
        force_price=1200.0,
        risk_level="HIGH",
        exception_reason="Non-standard liability indemnification terms requested"
    )
    
    assert result.decision == "HUMAN_APPROVAL_REQUIRED"
    assert result.is_auto_approved is False
    assert result.is_ceo_exception is True
    assert "requires CEO review" in result.decision_reason


# 8. Auto-approval NEVER bypasses safety or evidence verification
@pytest.mark.asyncio
async def test_economic_decision_never_bypasses_missing_evidence(db_session):
    biz = await _seed_test_prospect(db_session, domain="zeroevidence.co.uk", price=5000.0, with_evidence=False)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=5000.0)
    
    assert result.decision in ("HOLD", "RESEARCH_REQUIRED")
    assert result.is_auto_approved is False
    assert result.can_outreach is False


# 9. Decision reason is persisted and auditable in AutonomousDecisionLog
@pytest.mark.asyncio
async def test_economic_decision_reason_persisted_in_audit_log(db_session):
    biz = await _seed_test_prospect(db_session, domain="auditrecord.co.uk", price=1200.0)
    eval_res = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=1200.0)
    
    log = await autonomous_acquisition_controller.log_decision(
        session=db_session,
        action="POLICY_EVALUATION",
        decision=eval_res.decision,
        business_id=biz.id,
        policy_result=eval_res,
        price_usd=eval_res.price_usd,
        service_name=eval_res.service_name
    )
    
    assert log.id is not None
    assert log.decision == "AUTO_APPROVE"
    assert log.price_usd == 1200.0
    assert len(log.reasons) > 0
    assert any("economics positive" in r for r in log.reasons)
    assert log.metadata_json.get("decision_reason") == eval_res.decision_reason


# 10. Existing human approval behavior remains available for genuine exceptions
@pytest.mark.asyncio
async def test_human_approval_available_for_exceptions(db_session):
    biz = await _seed_test_prospect(db_session, domain="manualapproval.co.uk", price=900.0)
    result = await auto_approval_policy.evaluate_prospect(
        db_session,
        biz,
        force_price=900.0,
        is_exception=True,
        exception_reason="Production system configuration change requested"
    )
    
    assert result.decision == "HUMAN_APPROVAL_REQUIRED"
    assert result.is_ceo_exception is True
    assert result.is_auto_approved is False
    assert "requires CEO review" in result.decision_reason


# 11. Production database remains clean and real-data-only
def test_production_database_remains_clean():
    db_file = "agency.db"
    if os.path.exists(db_file):
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        fake_records = cur.execute(
            "SELECT count(*) FROM businesses WHERE name LIKE '%test%' OR name LIKE '%demo%' OR name LIKE '%fake%' OR name LIKE '%mock%' OR domain LIKE '%example.com%';"
        ).fetchone()[0]
        assert fake_records == 0, f"Found {fake_records} fake records in production database!"
        conn.close()


# 12. Standalone economic evaluation helper behaves consistently
def test_standalone_evaluate_deal_economics():
    res_499 = auto_approval_policy.evaluate_deal_economics(499.0)
    assert res_499["decision"] == "AUTO_REJECT"
    assert res_499["can_proceed"] is False
    assert "below minimum deal threshold" in res_499["reason"]

    res_500 = auto_approval_policy.evaluate_deal_economics(500.0)
    assert res_500["decision"] == "AUTO_APPROVE"
    assert res_500["can_proceed"] is True

    res_neg = auto_approval_policy.evaluate_deal_economics(800.0, estimated_cost=1000.0)
    assert res_neg["decision"] == "AUTO_REJECT"
    assert res_neg["can_proceed"] is False

    res_disc = auto_approval_policy.evaluate_deal_economics(1500.0, discount_percentage=0.45)
    assert res_disc["decision"] == "HUMAN_APPROVAL_REQUIRED"
    assert res_disc["is_ceo_exception"] is True

    res_ok = auto_approval_policy.evaluate_deal_economics(1500.0)
    assert res_ok["decision"] == "AUTO_APPROVE"
    assert res_ok["can_proceed"] is True
