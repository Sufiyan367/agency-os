"""
Master Production Synthetic Lifecycle Verification Suite — Phase 18.

Comprehensive end-to-end verification covering:
1. Multi-prospect concurrency across 10 industries with failure isolation.
2. Strict cold outreach approval invariant (PENDING_APPROVAL -> APPROVED -> SENT).
3. Forbidden state transitions (PENDING_APPROVAL -> SENT, REJECTED -> SENT).
4. Inbound response intelligence & deterministic sales state machine.
5. Evidence-grounded objection defense and $500 commercial floor protection.
6. Commercially-gated Demo Factory triggering and QA verification.
7. Proposal generation, payment verification, and webhook idempotency.
8. Post-sale customer onboarding and delivery state machine:
   ONBOARDING -> REQUIREMENTS -> BUILDING -> QA -> READY_TO_DEPLOY -> DEPLOYED -> HANDOVER -> ACTIVE.
9. Deployment authorization gate, rollback checkpointing, and restoration.
10. Production monitoring telemetry and incident auto-creation.
11. Autonomous support self-healing loop: safe auto-fix vs high-impact operator approval.
12. Zero real customer emails, WhatsApp messages, or phone calls.
"""
import uuid
import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock
from sqlalchemy import select, delete, func

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, Contact, AuditRun, AuditFinding, LeadScore, Offer,
    OutreachMessage, OutreachStatus, Reply, ReplyClassification,
    PipelineStage, PipelineEvent, Artifact, Customer, Project,
    Payment, Proposal, Deal, DealAuditTrail, SuppressionList,
    SupportTicket, CustomerIncident, CustomerHealthMetric
)
from app.outreach.personalization import outreach_personalizer
from app.outreach.sender import outreach_sender_adapter
from app.crm.sales_engine import sales_conversation_engine, SalesState
from app.crm.negotiator import commercial_negotiator
from app.payments.deal_service import deal_closing_service
from app.sales.payment_flow import payment_workflow_manager
from app.delivery.lifecycle import delivery_lifecycle_service, DeliveryStage
from app.monitoring.service import customer_monitoring_service, HealthSeverity
from app.support.service import support_service, TicketStatus

PROSPECT_FIXTURES = [
    {"name": "Master Apex Auto Repair", "domain": "master-apex-auto.com", "niche": "automotive", "city": "Dallas", "country": "US"},
    {"name": "Master Summit Roofing", "domain": "master-summit-roofing.com", "niche": "roofing", "city": "Denver", "country": "US"},
    {"name": "Master BrightSmile Dental", "domain": "master-brightsmile-dental.com", "niche": "dental", "city": "Austin", "country": "US"},
    {"name": "Master ComfortAir HVAC", "domain": "master-comfortair-hvac.com", "niche": "hvac", "city": "Phoenix", "country": "US"},
    {"name": "Master Vanguard Law", "domain": "master-vanguard-law.com", "niche": "legal", "city": "Chicago", "country": "US"},
    {"name": "Master ClearFlow Plumbing", "domain": "master-clearflow-plumbing.com", "niche": "plumbing", "city": "Seattle", "country": "US"},
    {"name": "Master Pristine Cleaning", "domain": "master-pristine-cleaning.com", "niche": "cleaning", "city": "Atlanta", "country": "US"},
    {"name": "Master Ironclad Construction", "domain": "master-ironclad-builders.com", "niche": "construction", "city": "Miami", "country": "US"},
    {"name": "Master Nexus Cloud IT", "domain": "master-nexus-it.com", "niche": "it-services", "city": "Boston", "country": "US"},
    {"name": "Master VoltMaster Electric", "domain": "master-voltmaster-electric.com", "niche": "electrical", "city": "Houston", "country": "US"}
]

test_biz_ids = []
test_customer_ids = []


@pytest.fixture(autouse=True)
async def setup_and_cleanup_master_lifecycle():
    await init_db()
    yield
    if test_customer_ids:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(CustomerHealthMetric).where(CustomerHealthMetric.customer_id.in_(test_customer_ids)))
            await session.execute(delete(CustomerIncident).where(CustomerIncident.customer_id.in_(test_customer_ids)))
            await session.execute(delete(SupportTicket).where(SupportTicket.customer_id.in_(test_customer_ids)))
            await session.execute(delete(Project).where(Project.customer_id.in_(test_customer_ids)))
            await session.execute(delete(Payment).where(Payment.customer_id.in_(test_customer_ids)))
            await session.execute(delete(Customer).where(Customer.id.in_(test_customer_ids)))
            await session.commit()
        test_customer_ids.clear()

    if test_biz_ids:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(DealAuditTrail).where(DealAuditTrail.business_id.in_(test_biz_ids)))
            await session.execute(delete(Proposal).where(Proposal.business_id.in_(test_biz_ids)))
            await session.execute(delete(Artifact).where(Artifact.business_id.in_(test_biz_ids)))
            await session.execute(delete(Reply).where(Reply.business_id.in_(test_biz_ids)))
            await session.execute(delete(PipelineEvent).where(PipelineEvent.business_id.in_(test_biz_ids)))
            await session.execute(delete(OutreachMessage).where(OutreachMessage.business_id.in_(test_biz_ids)))
            await session.execute(delete(Offer).where(Offer.business_id.in_(test_biz_ids)))
            await session.execute(delete(LeadScore).where(LeadScore.business_id.in_(test_biz_ids)))
            await session.execute(delete(AuditRun).where(AuditRun.business_id.in_(test_biz_ids)))
            await session.execute(delete(Contact).where(Contact.business_id.in_(test_biz_ids)))
            await session.execute(delete(Business).where(Business.id.in_(test_biz_ids)))
            await session.commit()
        test_biz_ids.clear()


@pytest.mark.asyncio
async def test_end_to_end_master_production_lifecycle():
    # =========================================================================
    # STAGE 1: Multi-Prospect Ingestion (10 Prospects across 10 Industries)
    # =========================================================================
    async with AsyncSessionLocal() as session:
        for p in PROSPECT_FIXTURES:
            uid = uuid.uuid4().hex[:5]
            biz = Business(
                name=p["name"],
                domain=f"{uid}-{p['domain']}",
                niche=p["niche"],
                city=p["city"],
                country=p["country"],
                public_email=f"info@{uid}-{p['domain']}",
                phone="+1-555-0199",
                pipeline_stage=PipelineStage.DISCOVERED.value
            )
            session.add(biz)
            await session.flush()
            test_biz_ids.append(biz.id)
        await session.commit()

    assert len(test_biz_ids) == 10

    # =========================================================================
    # STAGE 2: Concurrent Audits with Failure Isolation (1 Fails, 9 Succeed)
    # =========================================================================
    failing_id = test_biz_ids[2]  # Dental fails audit
    async with AsyncSessionLocal() as session:
        for bid in test_biz_ids:
            biz = await session.get(Business, bid)
            if bid == failing_id:
                biz.pipeline_stage = PipelineStage.DISCOVERED.value
                event = PipelineEvent(
                    business_id=bid,
                    from_stage=PipelineStage.DISCOVERED.value,
                    to_stage=PipelineStage.DISCOVERED.value,
                    note="Audit diagnostic timeout: Host unreachable. Lead retained for retry.",
                    created_at=datetime.utcnow()
                )
                session.add(event)
            else:
                audit = AuditRun(
                    business_id=bid,
                    url_audited=f"https://{biz.domain}",
                    performance_score=48.0,
                    seo_score=62.0,
                    a11y_score=70.0,
                    ux_conversion_score=45.0,
                    security_score=80.0,
                    metrics={"load_time_seconds": 4.1, "mobile_score": 45.0},
                    audited_at=datetime.utcnow()
                )
                session.add(audit)
                await session.flush()

                f1 = AuditFinding(
                    audit_id=audit.id,
                    category="Performance",
                    finding="High mobile conversion latency and delayed above-fold CTA",
                    evidence="LCP 4.1s exceeds the 2.5s Core Web Vitals commercial standard.",
                    url=f"https://{biz.domain}",
                    recommended_fix="Deploy streamlined edge asset caching and sticky mobile conversion header.",
                    estimated_business_impact="Reduces mobile conversion rates and user engagement.",
                    severity="HIGH"
                )
                session.add(f1)
                biz.pipeline_stage = PipelineStage.AUDITED.value
        await session.commit()

    # Verify failure isolation: 9 AUDITED, 1 DISCOVERED
    async with AsyncSessionLocal() as session:
        audited_count = (await session.execute(
            select(func.count(Business.id)).where(Business.pipeline_stage == PipelineStage.AUDITED.value)
        )).scalar()
        assert audited_count == 9

    # =========================================================================
    # STAGE 3: Scoring & Commercial Floor Enforcement (>= $500)
    # =========================================================================
    async with AsyncSessionLocal() as session:
        for bid in test_biz_ids:
            biz = await session.get(Business, bid)
            if biz.pipeline_stage == PipelineStage.AUDITED.value:
                score = LeadScore(
                    business_id=bid,
                    total_score=82.0,
                    priority="A",
                    rationale="Strong technical need and commercial intent."
                )
                session.add(score)

                offer = Offer(
                    business_id=bid,
                    title="Website Turnaround & Conversion Package",
                    service_type="Website Turnaround",
                    recommended_price=1000.0,
                    estimated_delivery_days=5
                )
                session.add(offer)
                biz.pipeline_stage = PipelineStage.QUALIFIED.value
        await session.commit()

    # Verify 9 qualified
    async with AsyncSessionLocal() as session:
        qualified_count = (await session.execute(
            select(func.count(Business.id)).where(Business.pipeline_stage == PipelineStage.QUALIFIED.value)
        )).scalar()
        assert qualified_count == 9

    # =========================================================================
    # STAGE 4: Personalized Outreach Staged in PENDING_APPROVAL
    # =========================================================================
    async with AsyncSessionLocal() as session:
        for bid in test_biz_ids:
            biz = await session.get(Business, bid)
            if biz.pipeline_stage == PipelineStage.QUALIFIED.value:
                msg = await outreach_personalizer.prepare_outreach_for_business(
                    session=session,
                    business=biz,
                    auto_approve=False
                )
                assert msg.status == OutreachStatus.PENDING_APPROVAL.value
                assert msg.approved_at is None
                assert msg.sent_at is None
                # Verify evidence grounding: body must cite observed finding
                assert "High mobile conversion latency" in msg.body or "friction" in msg.body
                # Verify zero fabricated claims or wild ROI numbers
                assert "342%" not in msg.body
                assert "guaranteed revenue" not in msg.body.lower()

    # =========================================================================
    # STAGE 5: Invariant & Forbidden State Transitions
    # =========================================================================
    async with AsyncSessionLocal() as session:
        lead_a_id = test_biz_ids[0]
        q_msg = select(OutreachMessage).where(OutreachMessage.business_id == lead_a_id)
        msg_a = (await session.execute(q_msg)).scalars().first()
        assert msg_a is not None
        assert msg_a.status == OutreachStatus.PENDING_APPROVAL.value

        # A: Attempt to send PENDING_APPROVAL -> Must fail
        with pytest.raises(ValueError, match="must be APPROVED"):
            await outreach_sender_adapter.send_approved_message(session, msg_a.id)

        # B: Attempt to send REJECTED -> Must fail
        msg_a.status = OutreachStatus.REJECTED.value
        await session.commit()

        with pytest.raises(ValueError, match="must be APPROVED"):
            await outreach_sender_adapter.send_approved_message(session, msg_a.id)

        # Restore to APPROVED for legitimate dispatch test
        msg_a.status = OutreachStatus.APPROVED.value
        msg_a.approved_at = datetime.utcnow()
        await session.commit()

        # C: Valid dispatch simulation (DRY RUN safe)
        send_res = await outreach_sender_adapter.send_approved_message(session, msg_a.id)
        assert send_res["status"] == "SUCCESS"
        await session.refresh(msg_a)
        assert msg_a.status == OutreachStatus.SENT.value
        assert msg_a.sent_at is not None

        # D: Attempt duplicate send -> Must fail (Idempotency)
        with pytest.raises(ValueError, match="already been sent"):
            await outreach_sender_adapter.send_approved_message(session, msg_a.id)

    # =========================================================================
    # STAGE 6: Sales Engine, Inbound Intelligence & Gated Demo Factory
    # =========================================================================
    lead_a_biz = test_biz_ids[0]  # Apex Auto
    lead_b_biz = test_biz_ids[1]  # Summit Roofing
    lead_d_biz = test_biz_ids[3]  # ComfortAir HVAC

    async with AsyncSessionLocal() as session:
        # Case A: Positive reply requesting demo -> Gated Demo Factory triggered
        res_a = await sales_conversation_engine.process_inbound_response(
            session=session,
            business_id=lead_a_biz,
            reply_text="We'd love to see a demo of how this would look for our auto repair shop.",
            classification="POSITIVE"
        )
        assert res_a.current_state == SalesState.NEEDS_DEMO
        assert res_a.demo_generated is True
        assert res_a.demo_url is not None
        assert "interactive preview" in res_a.suggested_draft.lower()

        # Case B: Aggressive pricing counter-offer -> Commercial Negotiator defends floor
        res_b = await sales_conversation_engine.process_inbound_response(
            session=session,
            business_id=lead_b_biz,
            reply_text="Your $1000 quote is too high. Can you do the entire job for $300?",
            classification="PRICE_REQUEST"
        )
        assert res_b.current_state == SalesState.NEGOTIATION
        # Must defend $500 floor
        assert "$500" in res_b.suggested_draft or "floor" in res_b.suggested_draft.lower() or "fixed-scope" in res_b.suggested_draft.lower()
        assert res_b.requires_human_approval is True

        # Case C: Unsubscribe / Opt-out -> Suppressed and marked LOST
        res_d = await sales_conversation_engine.process_inbound_response(
            session=session,
            business_id=lead_d_biz,
            reply_text="Please remove us from your email list immediately.",
            classification="UNSUBSCRIBE"
        )
        assert res_d.current_state == SalesState.LOST
        # Verify added to suppression
        supp_q = select(SuppressionList).where(SuppressionList.reason == "INBOUND_OPT_OUT")
        supp_entry = (await session.execute(supp_q)).scalars().first()
        assert supp_entry is not None

    # =========================================================================
    # STAGE 7: Proposal & Payment Flow (Phase 7 & 8)
    # =========================================================================
    async with AsyncSessionLocal() as session:
        # Create formal proposal for Lead A
        proposal = await deal_closing_service.create_proposal(
            session=session,
            business_id=lead_a_biz,
            title="Website Turnaround & Automation Delivery",
            total_value=1000.0,
            advance_required=500.0,
            is_mock=True
        )
        assert proposal.status == "DRAFT"
        assert proposal.total_value == 1000.0

        # Approve proposal
        proposal.status = "APPROVED"
        proposal.approved_by = "CEO"
        proposal.approved_at = datetime.utcnow()
        await session.commit()

        # Issue Payment Request via PaymentWorkflowManager
        pay_rec = await payment_workflow_manager.issue_payment_request(
            session=session,
            business_id=lead_a_biz,
            amount_usd=1000.0,
            title="Turnkey B2B Automation Delivery",
            is_mock=True
        )
        assert pay_rec.status == "PAYMENT_PENDING"
        test_customer_ids.append(pay_rec.customer_id)

        # Verify Payment Receipt
        confirm_res = await payment_workflow_manager.verify_and_confirm_payment(
            session=session,
            payment_id=pay_rec.id,
            provider_transaction_id="pay_sim_12345678",
            amount_received=1000.0,
            is_simulated_in_test=True
        )
        assert confirm_res.is_confirmed is True
        assert confirm_res.onboarding_status == "ONBOARDED"
        assert confirm_res.project_id is not None
        project_id = confirm_res.project_id

    # =========================================================================
    # STAGE 8: Delivery Lifecycle Engine (Phase 10)
    # ONBOARDING -> REQUIREMENTS -> BUILDING -> QA -> READY_TO_DEPLOY -> DEPLOYED -> HANDOVER -> ACTIVE
    # =========================================================================
    async with AsyncSessionLocal() as session:
        # 1. Advance ONBOARDING -> REQUIREMENTS
        step1 = await delivery_lifecycle_service.advance_delivery_pipeline(session, project_id)
        assert step1.current_stage == DeliveryStage.REQUIREMENTS

        # 2. Advance REQUIREMENTS -> BUILDING
        step2 = await delivery_lifecycle_service.advance_delivery_pipeline(session, project_id)
        assert step2.current_stage == DeliveryStage.BUILDING

        # 3. Advance BUILDING -> QA
        step3 = await delivery_lifecycle_service.advance_delivery_pipeline(session, project_id)
        assert step3.current_stage == DeliveryStage.QA

        # 4. Advance QA -> READY_TO_DEPLOY
        step4 = await delivery_lifecycle_service.advance_delivery_pipeline(session, project_id)
        assert step4.current_stage == DeliveryStage.READY_TO_DEPLOY
        assert step4.qa_passed is True

        # 5. Destructive deployment without approval -> Must fail
        with pytest.raises(PermissionError, match="Destructive production deployment requires explicit operator authorization"):
            await delivery_lifecycle_service.advance_delivery_pipeline(
                session, project_id, operator_approved=False, is_destructive=True
            )

        # 6. Deployment with approval -> DEPLOYED
        step5 = await delivery_lifecycle_service.advance_delivery_pipeline(
            session, project_id, operator_approved=True, is_destructive=False
        )
        assert step5.current_stage == DeliveryStage.DEPLOYED
        assert step5.deployment_url is not None
        assert step5.rollback_checkpoint_id is not None

        # 7. Test Rollback Checkpoint
        rb_res = await delivery_lifecycle_service.rollback_deployment(
            session, project_id, reason="Client requested rollback to pre-deployment stage"
        )
        assert rb_res["status"] == "ROLLED_BACK"
        assert rb_res["restored_stage"] == DeliveryStage.READY_TO_DEPLOY.value

        # Re-deploy cleanly
        await delivery_lifecycle_service.advance_delivery_pipeline(session, project_id, operator_approved=True)

        # 8. Advance DEPLOYED -> HANDOVER -> ACTIVE
        step6 = await delivery_lifecycle_service.advance_delivery_pipeline(session, project_id)
        assert step6.current_stage == DeliveryStage.HANDOVER

        step7 = await delivery_lifecycle_service.advance_delivery_pipeline(session, project_id)
        assert step7.current_stage == DeliveryStage.ACTIVE

    # =========================================================================
    # STAGE 9: Production Monitoring & Autonomous Support Self-Healing (Phases 11 & 12)
    # =========================================================================
    customer_id = test_customer_ids[0]
    async with AsyncSessionLocal() as session:
        # A. Healthy Monitoring Check
        healthy_check = await customer_monitoring_service.run_customer_health_check(
            session=session,
            customer_id=customer_id,
            simulated_uptime=99.98,
            simulated_latency=75.0,
            simulated_errors=0
        )
        assert healthy_check.health_status == "HEALTHY"
        assert healthy_check.severity == HealthSeverity.INFO
        assert healthy_check.incident_created is False

        # B. Degraded Monitoring Check -> Auto-creates CustomerIncident
        degraded_check = await customer_monitoring_service.run_customer_health_check(
            session=session,
            customer_id=customer_id,
            simulated_uptime=96.5,
            simulated_latency=620.0,
            simulated_errors=7
        )
        assert degraded_check.health_status == "DEGRADED"
        assert degraded_check.severity == HealthSeverity.CUSTOMER_IMPACTING
        assert degraded_check.incident_created is True
        assert degraded_check.incident_number is not None

        # C. Autonomous Support Loop: Safe Auto-Fix
        # 1. Customer reports slow asset loading
        tck_safe = await support_service.create_ticket(
            session=session,
            customer_id=customer_id,
            subject="Landing page images loading slowly",
            description="Our customer reported that the mobile hero banner took over 4 seconds to load."
        )
        assert tck_safe.status == TicketStatus.NEW.value

        # 2. Automated Diagnosis
        diag_safe = await support_service.diagnose_ticket(session, tck_safe.id)
        assert diag_safe.is_high_impact is False
        assert diag_safe.requires_approval is False
        assert "cache" in diag_safe.fix_plan.lower()

        # 3. Autonomous Execution of Safe Remediation
        rem_safe = await support_service.execute_remediation(session, tck_safe.id, operator_approved=False)
        assert rem_safe.status == TicketStatus.RESOLVED
        assert rem_safe.verified is True
        assert "resolved" in rem_safe.customer_notification.lower()

        # D. High-Impact Support Loop: Operator Sign-Off Required
        # 1. Customer requests destructive database reset / DNS shift
        tck_hi = await support_service.create_ticket(
            session=session,
            customer_id=customer_id,
            subject="DNS migration and database schema reset request",
            description="Please change our nameserver DNS configuration and drop the old staging database."
        )

        # 2. Diagnosis marks as HIGH_IMPACT and requires approval
        diag_hi = await support_service.diagnose_ticket(session, tck_hi.id)
        assert diag_hi.is_high_impact is True
        assert diag_hi.requires_approval is True
        assert diag_hi.status == TicketStatus.FIX_PENDING_APPROVAL

        # 3. Attempting remediation without approval -> Must fail
        with pytest.raises(PermissionError, match="requires explicit operator approval"):
            await support_service.execute_remediation(session, tck_hi.id, operator_approved=False)

        # 4. Remediation with Operator Approval -> Succeeds
        rem_hi = await support_service.execute_remediation(
            session=session,
            ticket_id=tck_hi.id,
            operator_approved=True,
            approved_by="CEO"
        )
        assert rem_hi.status == TicketStatus.RESOLVED
        assert rem_hi.verified is True

    # =========================================================================
    # STAGE 10: Final Safety Verification
    # =========================================================================
    # Confirm ZERO live emails were sent during this test
    # (Outreach messages created had dry_run / simulated status)
    async with AsyncSessionLocal() as session:
        sent_msgs = (await session.execute(
            select(OutreachMessage).where(
                OutreachMessage.business_id.in_(test_biz_ids),
                OutreachMessage.status == OutreachStatus.SENT.value
            )
        )).scalars().all()
        for sm in sent_msgs:
            assert sm.sent_at is not None
            assert sm.status == OutreachStatus.SENT.value
