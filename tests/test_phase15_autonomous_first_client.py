"""
Phase 15 Dedicated Test Suite: Autonomous First-Client Acquisition Engine
Covers all 20 mandatory test requirements:
1. test_floor_under_500_rejected
2. test_500_to_999_requires_human_approval
3. test_1000_plus_auto_approves_if_safe
4. test_high_price_never_bypasses_failed_evidence
5. test_high_price_never_bypasses_missing_audit
6. test_high_price_never_bypasses_unsubscribed_state
7. test_max_active_outreach_strictly_one
8. test_second_prospect_cannot_start_outreach_while_first_active
9. test_completed_lost_deal_frees_outreach_slot
10. test_paid_deal_frees_outreach_slot
11. test_routine_reply_auto_responses
12. test_sensitive_reply_escalates_to_human
13. test_legal_complaint_halts_and_escalates
14. test_fabricated_roi_guarantee_blocked
15. test_fake_payment_cannot_mark_paid
16. test_verified_payment_provisions_client
17. test_emergency_stop_halts_all_operations
18. test_research_only_mode_blocks_real_sending
19. test_restart_recovery_preserves_single_slot_state
20. test_full_autonomous_loop_mock_prospect_to_onboarding
"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import select

from app.core.config import settings
from app.database.models import (
    Business, AuditRun, AuditFinding, Offer, ClientIntelligenceRecord,
    ProspectEvidence, Payment, Customer, Project, ActiveOutreachLock,
    AutonomousDecisionLog, PipelineStage, OutreachStatus, OutreachMessage, SuppressionList
)
from app.acquisition.approval_policy import (
    auto_approval_policy,
    PolicyEvaluationResult,
    contains_prohibited_claims,
    check_outreach_content_safety
)
from app.crm.autonomous_reply_handler import (
    autonomous_reply_handler,
    RoutineCategory,
    EscalationCategory
)
from app.crm.negotiator import (
    commercial_negotiator,
    NegotiationResult
)
from app.sales.payment_flow import (
    payment_workflow_manager,
    PaymentConfirmationResult
)
from app.acquisition.controller import active_prospect_controller
from app.acquisition.autonomous_controller import (
    autonomous_acquisition_controller,
    AutonomousAcquisitionController
)


async def _create_test_business(db, domain="apexroofing.co.uk", name="Apex Roofing Ltd", target_price=1500.0, **kwargs):
    """Helper to create a fully set up, valid test business with audit, intel, and evidence."""
    biz = Business(
        name=name,
        domain=domain,
        website_url=f"https://{domain}",
        public_email=f"contact@{domain}",
        phone="+442079460123",
        country="UK",
        city="London",
        niche="Roofing",
        verification_status="VERIFIED",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    db.add(biz)
    await db.flush()

    # Handle suppression if requested
    if kwargs.get("unsubscribed", False):
        supp = SuppressionList(
            domain=domain,
            email=f"contact@{domain}",
            phone="+442079460123",
            reason="Unsubscribe requested by client"
        )
        db.add(supp)

    # Add ClientIntelligenceRecord
    intel = ClientIntelligenceRecord(
        business_id=biz.id,
        top_service_name="Turnkey Website Optimization",
        recommended_price_usd=target_price,
        target_price_usd=target_price,
        fit_score=0.92,
        why_this_business=["Demonstrated 4.8s mobile LCP bottleneck.", "Verified roofing trade operations in London."]
    )
    db.add(intel)

    # Add AuditRun
    if kwargs.get("with_audit", True):
        audit = AuditRun(
            business_id=biz.id,
            url_audited=f"https://{domain}",
            performance_score=45.0,
            seo_score=68.0,
            overall_health_score=60.0
        )
        db.add(audit)
        await db.flush()
        finding = AuditFinding(
            audit_id=audit.id,
            category="PERFORMANCE",
            finding="Slow Mobile LCP",
            severity="HIGH",
            evidence="LCP measured at 4,800ms.",
            url=f"https://{domain}",
            recommended_fix="Optimize critical rendering path.",
            estimated_business_impact="Increase conversion rate by 15%."
        )
        db.add(finding)

    # Add Evidence items
    if kwargs.get("with_evidence", True):
        ev1 = ProspectEvidence(
            business_id=biz.id,
            evidence_id=f"ev_{biz.id}_1_{uuid.uuid4().hex[:6]}",
            claim="Active roofing business domain in London",
            raw_excerpt="Apex Roofing Ltd is a registered roofing specialist serving Greater London.",
            source_url=f"https://{domain}",
            source_domain=domain,
            source_type="primary_domain",
            business_identity_match=True,
            is_verified=True,
            verification_status="VERIFIED",
            verification_reason="Official company website matched registered name.",
            content_hash="hash_primary_123",
            source_independence_group=domain
        )
        ev2 = ProspectEvidence(
            business_id=biz.id,
            evidence_id=f"ev_{biz.id}_2_{uuid.uuid4().hex[:6]}",
            claim="Registered UK business entity",
            raw_excerpt="Company number 01234567 registered at Companies House.",
            source_url="https://find-and-update.company-information.service.gov.uk/company/01234567",
            source_domain="company-information.service.gov.uk",
            source_type="public_registry",
            business_identity_match=True,
            is_verified=True,
            verification_status="VERIFIED",
            verification_reason="Companies House registry matches registered name and address.",
            content_hash="hash_registry_456",
            source_independence_group="companies_house_gov"
        )
        db.add_all([ev1, ev2])

    await db.commit()
    await db.refresh(biz)
    return biz


# ==============================================================================
# 1. test_floor_under_500_rejected
# ==============================================================================
@pytest.mark.asyncio
async def test_floor_under_500_rejected(db_session):
    biz = await _create_test_business(db_session, domain="lowoffer.co.uk", target_price=450.0)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=450.0)
    
    assert result.decision == "BLOCK"
    assert result.is_auto_approved is False
    assert result.checklist.get("commercial_floor_met") is False
    assert any("commercial floor" in r.lower() for r in result.reasons)


# ==============================================================================
# 2. test_500_to_999_requires_human_approval
# ==============================================================================
@pytest.mark.asyncio
async def test_500_to_999_requires_human_approval(db_session):
    biz = await _create_test_business(db_session, domain="midtier.co.uk", target_price=750.0)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=750.0)
    
    assert result.decision == "HUMAN_APPROVAL_REQUIRED"
    assert result.is_auto_approved is False
    assert result.checklist.get("commercial_floor_met") is True
    assert any("requires human approval" in r.lower() or "manual operator approval" in r.lower() for r in result.reasons)


# ==============================================================================
# 3. test_1000_plus_auto_approves_if_safe
# ==============================================================================
@pytest.mark.asyncio
async def test_1000_plus_auto_approves_if_safe(db_session):
    biz = await _create_test_business(db_session, domain="autosafe.co.uk", target_price=1500.0)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=1500.0)
    
    assert result.decision == "AUTO_APPROVE"
    assert result.is_auto_approved is True
    assert result.can_outreach is True
    assert result.checklist.get("commercial_floor_met") is True
    assert result.checklist.get("evidence_gate_passed") is True
    assert result.checklist.get("two_independent_sources") is True
    assert result.checklist.get("audit_completed") is True


# ==============================================================================
# 4. test_high_price_never_bypasses_failed_evidence
# ==============================================================================
@pytest.mark.asyncio
async def test_high_price_never_bypasses_failed_evidence(db_session):
    # Offer is $5,000, but without independent evidence
    biz = await _create_test_business(db_session, domain="noevidence.co.uk", target_price=5000.0, with_evidence=False)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=5000.0)
    
    assert result.decision in ("BLOCK", "RESEARCH_REQUIRED")
    assert result.is_auto_approved is False
    assert result.checklist.get("evidence_gate_passed") is False
    assert result.checklist.get("two_independent_sources") is False


# ==============================================================================
# 5. test_high_price_never_bypasses_missing_audit
# ==============================================================================
@pytest.mark.asyncio
async def test_high_price_never_bypasses_missing_audit(db_session):
    # Offer is $3,500, but without completed audit
    biz = await _create_test_business(db_session, domain="noaudit.co.uk", target_price=3500.0, with_audit=False)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=3500.0)
    
    assert result.decision in ("BLOCK", "RESEARCH_REQUIRED")
    assert result.is_auto_approved is False
    assert result.checklist.get("audit_completed") is False


# ==============================================================================
# 6. test_high_price_never_bypasses_unsubscribed_state
# ==============================================================================
@pytest.mark.asyncio
async def test_high_price_never_bypasses_unsubscribed_state(db_session):
    # Offer is $10,000, but business is unsubscribed (in SuppressionList)
    biz = await _create_test_business(db_session, domain="unsub.co.uk", target_price=10000.0, unsubscribed=True)
    result = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=10000.0)
    
    assert result.decision == "BLOCK"
    assert result.is_auto_approved is False
    assert result.checklist.get("no_suppression") is False


# ==============================================================================
# 7. test_max_active_outreach_strictly_one
# ==============================================================================
@pytest.mark.asyncio
async def test_max_active_outreach_strictly_one(db_session):
    assert settings.MAX_ACTIVE_OUTREACH_PROSPECTS == 1
    lock = await active_prospect_controller.get_or_create_lock(db_session)
    assert lock.slot_id == 1


# ==============================================================================
# 8. test_second_prospect_cannot_start_outreach_while_first_active
# ==============================================================================
@pytest.mark.asyncio
async def test_second_prospect_cannot_start_outreach_while_first_active(db_session):
    # Ensure lock is IDLE before test
    await active_prospect_controller.release_active_slot(db_session, terminal_reason="MANUAL_RELEASE")

    b1 = await _create_test_business(db_session, domain="first.co.uk", name="First Ltd")
    b2 = await _create_test_business(db_session, domain="second.co.uk", name="Second Ltd")
    
    # Lock first
    status1 = await active_prospect_controller.select_next_prospect(db_session, business_id=b1.id)
    assert status1.is_occupied is True
    assert status1.business_id == b1.id
    
    # Attempting to lock second must raise ValueError
    with pytest.raises(ValueError) as excinfo:
        await active_prospect_controller.select_next_prospect(db_session, business_id=b2.id)
    assert "already occupied" in str(excinfo.value)


# ==============================================================================
# 9. test_completed_lost_deal_frees_outreach_slot
# ==============================================================================
@pytest.mark.asyncio
async def test_completed_lost_deal_frees_outreach_slot(db_session):
    # Ensure lock is IDLE before test
    await active_prospect_controller.release_active_slot(db_session, terminal_reason="MANUAL_RELEASE")

    b1 = await _create_test_business(db_session, domain="lost.co.uk", name="Lost Ltd")
    b2 = await _create_test_business(db_session, domain="next.co.uk", name="Next Ltd")
    
    # Lock b1
    await active_prospect_controller.select_next_prospect(db_session, business_id=b1.id)
    
    # Release with terminal reason LOST
    rel_res = await active_prospect_controller.release_active_slot(db_session, terminal_reason="LOST")
    assert rel_res["released"] is True
    assert rel_res["slot_status"] == "IDLE"
    status_after = await active_prospect_controller.get_active_status(db_session)
    assert status_after.is_occupied is False
    
    # Slot 1 is now available for b2
    status2 = await active_prospect_controller.select_next_prospect(db_session, business_id=b2.id)
    assert status2.is_occupied is True
    assert status2.business_id == b2.id


# ==============================================================================
# 10. test_paid_deal_frees_outreach_slot
# ==============================================================================
@pytest.mark.asyncio
async def test_paid_deal_frees_outreach_slot(db_session):
    # Ensure lock is IDLE before test
    await active_prospect_controller.release_active_slot(db_session, terminal_reason="MANUAL_RELEASE")

    b1 = await _create_test_business(db_session, domain="won.co.uk", name="Won Ltd")
    await active_prospect_controller.select_next_prospect(db_session, business_id=b1.id)
    
    # Release with terminal reason WON
    rel_res = await active_prospect_controller.release_active_slot(db_session, terminal_reason="WON")
    assert rel_res["released"] is True
    assert rel_res["slot_status"] == "IDLE"
    status_after = await active_prospect_controller.get_active_status(db_session)
    assert status_after.is_occupied is False


# ==============================================================================
# 11. test_routine_reply_auto_responses
# ==============================================================================
def test_routine_reply_auto_responses():
    # Price inquiry
    res_price = autonomous_reply_handler.classify_text("How much does this speed optimization cost?")
    assert res_price.category == RoutineCategory.ASKING_PRICE.value
    assert res_price.is_escalation is False
    assert res_price.requires_human_intervention is False

    # Timeline inquiry
    res_time = autonomous_reply_handler.classify_text("What is your turnaround time to complete the work?")
    assert res_time.category == RoutineCategory.ASKING_TIMELINE.value
    assert res_time.is_escalation is False

    # Details inquiry
    res_details = autonomous_reply_handler.classify_text("Could you explain exactly how it works and what changes you make?")
    assert res_details.category in (RoutineCategory.ASKING_DETAILS.value, RoutineCategory.ASKING_HOW_IT_WORKS.value)
    assert res_details.is_escalation is False


# ==============================================================================
# 12. test_sensitive_reply_escalates_to_human
# ==============================================================================
def test_sensitive_reply_escalates_to_human():
    # Complaint
    res_complaint = autonomous_reply_handler.classify_text("This spam is completely unacceptable. Stop contacting us immediately.")
    assert res_complaint.is_escalation is True
    assert res_complaint.requires_human_intervention is True
    assert res_complaint.category == EscalationCategory.COMPLAINT.value

    # Privacy / GDPR
    res_gdpr = autonomous_reply_handler.classify_text("Under GDPR Article 17, remove all my records from your database.")
    assert res_gdpr.is_escalation is True
    assert res_gdpr.category == EscalationCategory.PRIVACY_REQUEST.value


# ==============================================================================
# 13. test_legal_complaint_halts_and_escalates
# ==============================================================================
def test_legal_complaint_halts_and_escalates():
    res_legal = autonomous_reply_handler.classify_text("Our attorney will be filing a formal lawsuit against your company tomorrow morning.")
    assert res_legal.is_escalation is True
    assert res_legal.category == EscalationCategory.LEGAL_THREAT.value
    assert res_legal.requires_human_intervention is True


# ==============================================================================
# 14. test_fabricated_roi_guarantee_blocked
# ==============================================================================
def test_fabricated_roi_guarantee_blocked():
    assert contains_prohibited_claims("We guarantee 500% ROI in 30 days.") is True
    assert contains_prohibited_claims("100% money back guarantee with no risk.") is True
    assert contains_prohibited_claims("Empirical audit showed 4.8s LCP delay.") is False

    # Subject and body safety check
    is_safe, reasons = check_outreach_content_safety(
        "Guaranteed 500% ROI",
        "We guarantee you will double your revenue within 30 days risk-free."
    )
    assert is_safe is False
    assert len(reasons) > 0


# ==============================================================================
# 15. test_fake_payment_cannot_mark_paid
# ==============================================================================
@pytest.mark.asyncio
async def test_fake_payment_cannot_mark_paid(db_session):
    biz = await _create_test_business(db_session, domain="fakepay.co.uk", target_price=1500.0)
    
    # Issue a pending payment request for $1,500
    payment = await payment_workflow_manager.issue_payment_request(
        db_session,
        business_id=biz.id,
        amount_usd=1500.0,
        title="Roofing Website Optimization",
        is_mock=True
    )
    
    # 1. Non-existent payment record
    res_none = await payment_workflow_manager.verify_and_confirm_payment(
        db_session,
        payment_id=999999,
        provider_transaction_id="fake_tx",
        amount_received=1500.0
    )
    assert res_none.is_confirmed is False

    # 2. Mismatched amount ($50 instead of $1,500)
    res_mismatch = await payment_workflow_manager.verify_and_confirm_payment(
        db_session,
        payment_id=payment.id,
        provider_transaction_id="tx_fake_mismatch",
        amount_received=50.0
    )
    assert res_mismatch.is_confirmed is False
    assert "underpayment" in res_mismatch.error_message.lower()

    # Confirm business pipeline_stage was not transitioned to WON
    await db_session.refresh(biz)
    assert biz.pipeline_stage != PipelineStage.WON.value


# ==============================================================================
# 16. test_verified_payment_provisions_client
# ==============================================================================
@pytest.mark.asyncio
async def test_verified_payment_provisions_client(db_session):
    biz = await _create_test_business(db_session, domain="realpay.co.uk", target_price=2500.0)
    
    # Issue valid payment request
    payment = await payment_workflow_manager.issue_payment_request(
        db_session,
        business_id=biz.id,
        amount_usd=2500.0,
        title="Turnkey AI Implementation",
        is_mock=True
    )
    
    # Confirm payment with matched amount
    res = await payment_workflow_manager.verify_and_confirm_payment(
        db_session,
        payment_id=payment.id,
        provider_transaction_id="tx_legit_2500",
        amount_received=2500.0,
        is_simulated_in_test=True
    )
    
    assert res.is_confirmed is True
    assert res.amount_paid == 2500.0
    assert res.pipeline_stage == PipelineStage.WON.value
    assert res.customer_id is not None
    assert res.project_id is not None
    assert res.onboarding_status == "ONBOARDED"
    
    # Verify delivery architecture metadata
    assert res.delivery_architecture["frontend_ui"] == "Stitch"
    assert res.delivery_architecture["model_runtime"] == "Google AI Studio"
    assert res.delivery_architecture["agent_framework"] == "Antigravity"
    assert res.delivery_architecture["backend_hosting"] == "Firebase"

    # Verify business stage updated to WON
    await db_session.refresh(biz)
    assert biz.pipeline_stage == PipelineStage.WON.value


# ==============================================================================
# 17. test_emergency_stop_halts_all_operations
# ==============================================================================
def test_emergency_stop_halts_all_operations():
    ctrl = AutonomousAcquisitionController()
    ctrl.is_running = True
    ctrl.is_paused = False
    
    res = ctrl.emergency_stop()
    assert res["status"] == "KILLED"
    assert ctrl.kill_switch_active is True
    assert ctrl.is_running is False
    assert "EMERGENCY STOP" in ctrl.current_action


# ==============================================================================
# 18. test_research_only_mode_blocks_real_sending
# ==============================================================================
@pytest.mark.asyncio
async def test_research_only_mode_blocks_real_sending(db_session):
    from app.outreach.sender import outreach_sender_adapter
    biz = await _create_test_business(db_session, domain="researchonly.co.uk", target_price=1500.0)
    
    # Create approved outreach message
    msg = OutreachMessage(
        business_id=biz.id,
        status=OutreachStatus.APPROVED.value,
        recipient_email=biz.public_email,
        subject="Empirical Website Findings",
        body="Audit details for researchonly.co.uk"
    )
    db_session.add(msg)
    await db_session.commit()
    
    # Enable RESEARCH_ONLY
    with patch.object(settings, "RESEARCH_ONLY", True):
        with pytest.raises(ValueError) as exc:
            await outreach_sender_adapter.send_approved_message(db_session, msg.id)
        assert "RESEARCH_ONLY mode" in str(exc.value)


# ==============================================================================
# 19. test_restart_recovery_preserves_single_slot_state
# ==============================================================================
@pytest.mark.asyncio
async def test_restart_recovery_preserves_single_slot_state(db_session):
    # Ensure lock is IDLE before test
    await active_prospect_controller.release_active_slot(db_session, terminal_reason="MANUAL_RELEASE")

    biz = await _create_test_business(db_session, domain="restart.co.uk", name="Restart Ltd")
    # Lock slot
    await active_prospect_controller.select_next_prospect(db_session, business_id=biz.id)
    
    # Simulate a new controller call retrieving the existing persistent lock
    slot_status = await active_prospect_controller.get_active_status(db_session)
    
    assert slot_status.is_occupied is True
    assert slot_status.business_id == biz.id
    assert slot_status.business_name == "Restart Ltd"


# ==============================================================================
# 20. test_full_autonomous_loop_mock_prospect_to_onboarding
# ==============================================================================
@pytest.mark.asyncio
async def test_full_autonomous_loop_mock_prospect_to_onboarding(db_session):
    # Ensure lock is IDLE before test
    await active_prospect_controller.release_active_slot(db_session, terminal_reason="MANUAL_RELEASE")

    # 1. Prospect creation & verification
    biz = await _create_test_business(db_session, domain="fullloop.co.uk", name="Full Loop Roofing", target_price=2000.0)
    
    # 2. Single-Slot Lock
    slot = await active_prospect_controller.select_next_prospect(db_session, business_id=biz.id)
    assert slot.is_occupied is True
    
    # 3. Policy Evaluation: $2,000 auto-approved
    policy_res = await auto_approval_policy.evaluate_prospect(db_session, biz, force_price=2000.0)
    assert policy_res.decision == "AUTO_APPROVE"
    assert policy_res.is_auto_approved is True
    
    # 4. Outbound Draft Content Safety Check
    safe, _ = check_outreach_content_safety("Performance Audit for Full Loop Roofing", "Here is our empirical audit of your website.")
    assert safe is True
    
    # 5. Inbound routine reply handling
    reply = autonomous_reply_handler.classify_text("We are interested in this, what is your price?")
    assert reply.category == RoutineCategory.ASKING_PRICE.value
    assert reply.is_escalation is False
    
    # 6. Commercial Negotiation: Client asks for $1,800 counter-offer
    neg = commercial_negotiator.evaluate_counter_offer(1800.0, catalog_target=2000.0)
    assert neg.decision == "ACCEPTED"
    assert neg.can_accept is True
    assert neg.agreed_price_usd == 1800.0
    
    # 7. Issue Payment Request for $1,800
    pay = await payment_workflow_manager.issue_payment_request(
        db_session,
        business_id=biz.id,
        amount_usd=1800.0,
        title="Full Turnkey Optimization",
        is_mock=True
    )
    assert pay.amount == 1800.0
    
    # 8. Legitimate Payment Confirmation & Onboarding
    confirm = await payment_workflow_manager.verify_and_confirm_payment(
        db_session,
        payment_id=pay.id,
        provider_transaction_id="tx_loop_success_1800",
        amount_received=1800.0,
        is_simulated_in_test=True
    )
    assert confirm.is_confirmed is True
    assert confirm.pipeline_stage == PipelineStage.WON.value
    assert confirm.onboarding_status == "ONBOARDED"
    assert confirm.delivery_architecture["frontend_ui"] == "Stitch"
    assert confirm.delivery_architecture["model_runtime"] == "Google AI Studio"
    assert confirm.delivery_architecture["agent_framework"] == "Antigravity"
    assert confirm.delivery_architecture["backend_hosting"] == "Firebase"
    
    # 9. Payment confirmation automatically released the slot with terminal reason WON
    status_after = await active_prospect_controller.get_active_status(db_session)
    assert status_after.is_occupied is False
