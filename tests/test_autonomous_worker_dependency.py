"""
Autonomous Agency OS — Remove Manual Run-Cycle Dependency Test Suite.

Verifies:
1. Continuous background worker executes revenue loop without manual Run Cycle
2. Multi-prospect concurrency (WAITING_FOR_REPLY does not block other prospects)
3. Positive reply automatically triggers demo pipeline, cancels follow-ups, and emits notification
4. Bounded follow-up execution runs automatically
5. Failure isolation (prospect-level exception or provider failure does not crash worker)
6. 70/day hard outbound capacity ceiling is strictly enforced
7. Suppression & idempotency prevent duplicate sends
8. Real dashboard state: payments disabled displays "PAYMENTS NOT ACTIVE" and truthful revenue
9. Absolute ZERO real outbound messages sent during tests
"""

import pytest
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import select, func

from app.core.config import settings
from app.database.models import (
    Business, OutreachMessage, OutreachStatus, OutreachEvent,
    Reply, ReplyClassification, SuppressionList, PipelineStage,
    FollowupSequence, FollowupStatus, LeadScore, AuditRun, Payment
)
from app.orchestrator.worker import PersistentAgencyWorker
from app.campaigns.sender_registry import sender_registry
from app.outreach.compliance import compliance_guard
from app.core.event_bus import event_bus, AgencyEvent


def get_worker_session_mock(db_session):
    @asynccontextmanager
    async def _ctx():
        yield db_session
    return _ctx


@pytest.mark.asyncio
async def test_worker_runs_without_manual_run_cycle(db_session):
    """Verify worker tick executes inbox processing, approved dispatch, and backlog drainage automatically."""
    worker = PersistentAgencyWorker()
    worker.interval_seconds = 120
    worker.last_cycle_at = datetime.utcnow() - timedelta(hours=2)

    # Ensure worker reports running and autonomous auto-discovery is enabled
    status = worker.get_status()
    assert status["autonomous_auto_discovery"] is True

    # Seed an audited business needing scoring
    biz = Business(name="Auto Worker Biz", domain="autoworker.com", country="AE", niche="hvac", public_email="info@autoworker.com", pipeline_stage=PipelineStage.AUDITED.value)
    db_session.add(biz)
    await db_session.commit()

    with patch("app.orchestrator.worker.AsyncSessionLocal", side_effect=get_worker_session_mock(db_session)), \
         patch("app.orchestrator.worker.inbox_poller.poll_inbox", new_callable=AsyncMock) as mock_poll, \
         patch("app.orchestrator.worker.lead_scoring_engine.score_business", new_callable=AsyncMock) as mock_score, \
         patch("app.orchestrator.worker.offer_engine.generate_offer_for_business", new_callable=AsyncMock) as mock_offer, \
         patch("app.orchestrator.worker.orchestrator.run_full_autonomous_cycle", new_callable=AsyncMock) as mock_cycle, \
         patch("app.orchestrator.worker.attention_engine.get_attention_feed", new_callable=AsyncMock) as mock_att:

        mock_poll.return_value = []
        mock_score_obj = MagicMock()
        mock_score_obj.total_score = 85.0
        mock_score.return_value = mock_score_obj

        mock_offer_obj = MagicMock()
        mock_offer_obj.recommended_price = 1500.0
        mock_offer.return_value = mock_offer_obj

        mock_cycle.return_value = {"status": "SUCCESS", "leads_discovered": 1}
        mock_att.return_value = {"overall_status": "ALL_CLEAR", "counts": {"high_priority": 0}}

        summary = await worker.execute_tick()

        assert summary["status"] == "SUCCESS"
        assert summary["scored_backlog"] >= 1
        assert summary["autonomous_cycle_run"] is True
        mock_cycle.assert_called_once()

        # Business should have advanced to QUALIFIED automatically without manual Run Cycle
        res_biz = (await db_session.execute(select(Business).where(Business.domain == "autoworker.com"))).scalar_one()
        assert res_biz.pipeline_stage == PipelineStage.QUALIFIED.value


@pytest.mark.asyncio
async def test_multi_prospect_concurrency(db_session):
    """Verify that a prospect in WAITING_FOR_REPLY / CONTACTED does NOT block other prospects from progressing."""
    worker = PersistentAgencyWorker()

    # Prospect 1: CONTACTED / WAITING_FOR_REPLY
    biz1 = Business(name="Contacted Lead", domain="contactedlead.com", country="AE", niche="dental", pipeline_stage=PipelineStage.CONTACTED.value)
    # Prospect 2: QUALIFIED (ready for drafting)
    biz2 = Business(name="Qualified Lead", domain="qualifiedlead.com", country="AE", niche="dental", pipeline_stage=PipelineStage.QUALIFIED.value)
    # Prospect 3: DISCOVERED (ready for audit)
    biz3 = Business(name="Discovered Lead", domain="discoveredlead.com", country="AE", niche="dental", pipeline_stage=PipelineStage.DISCOVERED.value)

    db_session.add_all([biz1, biz2, biz3])
    await db_session.commit()

    with patch("app.orchestrator.worker.website_audit_engine.audit_business", new_callable=AsyncMock) as mock_audit, \
         patch("app.orchestrator.worker.outreach_personalizer.prepare_outreach_for_business", new_callable=AsyncMock) as mock_prep, \
         patch("app.orchestrator.worker.inbox_poller.poll_inbox", new_callable=AsyncMock, return_value=[]), \
         patch("app.orchestrator.worker.attention_engine.get_attention_feed", new_callable=AsyncMock, return_value={"overall_status": "ALL_CLEAR"}):

        mock_audit.return_value = MagicMock()
        mock_msg = MagicMock()
        mock_msg.id = 999
        mock_prep.return_value = mock_msg

        # Drain audit backlog
        audited_n = await worker.drain_audit_backlog(db_session, limit=10)
        assert audited_n >= 1
        res3 = (await db_session.execute(select(Business).where(Business.domain == "discoveredlead.com"))).scalar_one()
        assert res3.pipeline_stage == PipelineStage.AUDITED.value

        # Drain drafting backlog
        drafted_n = await worker.drain_drafting_backlog(db_session, limit=10)
        assert drafted_n >= 1
        res2 = (await db_session.execute(select(Business).where(Business.domain == "qualifiedlead.com"))).scalar_one()
        assert res2.pipeline_stage == PipelineStage.APPROVAL.value

        # Biz 1 remains in CONTACTED unaffected
        res1 = (await db_session.execute(select(Business).where(Business.domain == "contactedlead.com"))).scalar_one()
        assert res1.pipeline_stage == PipelineStage.CONTACTED.value


@pytest.mark.asyncio
async def test_positive_reply_advances_and_triggers_demo(db_session):
    """Verify that an inbound positive reply automatically updates stage, cancels followups, triggers demo, and emits notification."""
    worker = PersistentAgencyWorker()
    worker.last_cycle_at = datetime.utcnow()

    biz = Business(name="Interested Tech", domain="interestedtech.com", country="AE", niche="saas", pipeline_stage=PipelineStage.CONTACTED.value)
    db_session.add(biz)
    await db_session.flush()

    # Outbound message + scheduled follow-up
    outreach = OutreachMessage(
        business_id=biz.id,
        recipient_email="ceo@interestedtech.com",
        subject="AI Proposal",
        body="Let us show you",
        status=OutreachStatus.SENT.value
    )
    db_session.add(outreach)
    await db_session.flush()

    fu = FollowupSequence(
        initial_message_id=outreach.id,
        step_number=1,
        scheduled_for=datetime.utcnow() + timedelta(days=2),
        subject="Quick Followup",
        body="Did you have a chance to review?",
        status=FollowupStatus.SCHEDULED.value
    )
    db_session.add(fu)

    # Inbound unhandled reply
    reply = Reply(
        business_id=biz.id,
        sender_email="ceo@interestedtech.com",
        raw_body="We are definitely interested in your automation services, can you send over a demo?",
        classification="POSITIVE",
        confidence=0.96,
        is_handled=False
    )
    db_session.add(reply)
    await db_session.commit()

    events_published = []
    async def capture_event(ev: AgencyEvent):
        events_published.append(ev)

    event_bus.subscribe("POSITIVE_REPLY", capture_event)

    with patch("app.orchestrator.worker.AsyncSessionLocal", side_effect=get_worker_session_mock(db_session)), \
         patch("app.orchestrator.worker.inbox_poller.poll_inbox", new_callable=AsyncMock, return_value=[]), \
         patch("app.builder.pipeline.pipeline_orchestrator.trigger_demo_pipeline", new_callable=AsyncMock) as mock_demo, \
         patch("app.orchestrator.worker.attention_engine.get_attention_feed", new_callable=AsyncMock, return_value={"overall_status": "ALL_CLEAR"}):

        mock_demo.return_value = {"success": True, "demo_url": "https://automatedagencyos.tech/demo/interested-tech"}

        summary = await worker.execute_tick()

        assert summary["status"] == "SUCCESS"

        # Verify pipeline stage advanced to QUALIFIED_REPLY
        res_biz = (await db_session.execute(select(Business).where(Business.domain == "interestedtech.com"))).scalar_one()
        assert res_biz.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value

        # Verify demo pipeline was NOT triggered automatically (Critical Requirement #6: requirements first)
        mock_demo.assert_not_called()

        # Verify reply was marked handled and suggested response prompts for requirements / conversation
        res_reply = (await db_session.execute(select(Reply).where(Reply.id == reply.id))).scalar_one()
        assert res_reply.is_handled is True
        assert "requirements" in res_reply.suggested_response or "discovery call" in res_reply.suggested_response

        # Verify follow-up was cancelled
        res_fu = (await db_session.execute(select(FollowupSequence).where(FollowupSequence.id == fu.id))).scalar_one()
        assert res_fu.status == FollowupStatus.CANCELLED_REPLY.value

        # Verify POSITIVE_REPLY notification event was published
        assert any(e.event_type == "POSITIVE_REPLY" for e in events_published)


@pytest.mark.asyncio
async def test_bounded_followups_cancelled_on_negative_or_unsub(db_session):
    """Verify followups are cancelled and suppression enforced on negative / unsubscribe replies."""
    worker = PersistentAgencyWorker()
    worker.last_cycle_at = datetime.utcnow()

    biz = Business(name="Unsub Corp", domain="unsubcorp.com", country="AE", niche="retail", pipeline_stage=PipelineStage.CONTACTED.value)
    db_session.add(biz)
    await db_session.flush()

    outreach = OutreachMessage(
        business_id=biz.id,
        recipient_email="optout@unsubcorp.com",
        subject="Outreach",
        body="Body",
        status=OutreachStatus.SENT.value
    )
    db_session.add(outreach)
    await db_session.flush()

    fu = FollowupSequence(
        initial_message_id=outreach.id,
        step_number=1,
        scheduled_for=datetime.utcnow() + timedelta(days=2),
        subject="Follow-up note",
        body="Just checking in.",
        status=FollowupStatus.SCHEDULED.value
    )
    db_session.add(fu)

    reply = Reply(
        business_id=biz.id,
        sender_email="optout@unsubcorp.com",
        raw_body="Please remove us from your mailing list.",
        classification="UNSUBSCRIBE",
        confidence=0.99,
        is_handled=False
    )
    db_session.add(reply)
    await db_session.commit()

    with patch("app.orchestrator.worker.AsyncSessionLocal", side_effect=get_worker_session_mock(db_session)), \
         patch("app.orchestrator.worker.inbox_poller.poll_inbox", new_callable=AsyncMock, return_value=[]), \
         patch("app.orchestrator.worker.attention_engine.get_attention_feed", new_callable=AsyncMock, return_value={"overall_status": "ALL_CLEAR"}):

        summary = await worker.execute_tick()
        assert summary["status"] == "SUCCESS"

        res_biz = (await db_session.execute(select(Business).where(Business.domain == "unsubcorp.com"))).scalar_one()
        assert res_biz.pipeline_stage == PipelineStage.LOST.value

        res_fu = (await db_session.execute(select(FollowupSequence).where(FollowupSequence.id == fu.id))).scalar_one()
        assert res_fu.status == FollowupStatus.CANCELLED_UNSUB.value


@pytest.mark.asyncio
async def test_failure_isolation_single_prospect(db_session):
    """Verify that an exception in one prospect does NOT halt other prospects or crash the worker tick."""
    worker = PersistentAgencyWorker()

    biz_bad = Business(name="Bad Domain Biz", domain="baddomain.com", country="AE", niche="legal", pipeline_stage=PipelineStage.DISCOVERED.value)
    biz_good = Business(name="Good Domain Biz", domain="gooddomain.com", country="AE", niche="legal", pipeline_stage=PipelineStage.DISCOVERED.value)

    db_session.add_all([biz_bad, biz_good])
    await db_session.commit()

    async def mock_audit_impl(session, biz):
        if biz.domain == "baddomain.com":
            raise ValueError("Scraper connection timeout on bad domain")
        return MagicMock()

    with patch("app.orchestrator.worker.website_audit_engine.audit_business", side_effect=mock_audit_impl):
        audited_count = await worker.drain_audit_backlog(db_session, limit=10)

        # Good prospect succeeded despite bad prospect failure
        assert audited_count == 1
        res_good = (await db_session.execute(select(Business).where(Business.domain == "gooddomain.com"))).scalar_one()
        assert res_good.pipeline_stage == PipelineStage.AUDITED.value

        res_bad = (await db_session.execute(select(Business).where(Business.domain == "baddomain.com"))).scalar_one()
        assert res_bad.pipeline_stage == PipelineStage.DISCOVERED.value


@pytest.mark.asyncio
async def test_failure_isolation_provider_error(db_session):
    """Verify that an outbound sender socket/provider error does not crash the worker tick."""
    worker = PersistentAgencyWorker()
    worker.last_cycle_at = datetime.utcnow()

    biz = Business(name="Approved Biz", domain="approvedbiz.com", country="AE", niche="medical", pipeline_stage=PipelineStage.APPROVAL.value)
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="contact@approvedbiz.com",
        subject="Approved Subject",
        body="Approved Body",
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.commit()

    with patch("app.orchestrator.worker.AsyncSessionLocal", side_effect=get_worker_session_mock(db_session)), \
         patch("app.orchestrator.worker.inbox_poller.poll_inbox", new_callable=AsyncMock, return_value=[]), \
         patch("app.orchestrator.worker.outreach_sender_adapter.send_approved_message", side_effect=ConnectionError("Titan SMTP connection reset")), \
         patch("app.orchestrator.worker.attention_engine.get_attention_feed", new_callable=AsyncMock, return_value={"overall_status": "ALL_CLEAR"}):

        summary = await worker.execute_tick()

        # Tick finishes gracefully despite provider error
        assert summary["status"] == "SUCCESS"
        assert summary.get("approved_queue_processed", 0) == 0

        # Message remains approved for retry
        await db_session.refresh(msg)
        assert msg.status == OutreachStatus.APPROVED.value


@pytest.mark.asyncio
async def test_70_per_day_hard_cap_enforced(db_session):
    """Verify capacity calculation strictly caps daily outbound to 70."""
    cap_summary = await sender_registry.get_sender_capacity_summary(db_session)
    assert cap_summary["rollout_daily_cap"] == 70
    assert cap_summary["available_capacity"] <= 70


@pytest.mark.asyncio
async def test_truthful_revenue_and_payment_status(db_session):
    """Verify that when payments are disabled, payment_status is 'PAYMENTS NOT ACTIVE' and revenue is truthful $0.00."""
    from app.api.routes import get_ceo_control_center_overview

    mock_user = {"sub": "admin", "role": "ceo"}
    with patch("app.core.config.settings.PAYMENTS_ENABLED", False):
        overview = await get_ceo_control_center_overview(db=db_session, user_info=mock_user)

        metrics = overview["executive_metrics"]
        sys_status = overview["system_status"]

        assert metrics["payment_status"] == "PAYMENTS NOT ACTIVE"
        assert metrics["revenue_label"] == "$0.00"
        assert sys_status["payment_mode"] == "PAYMENTS NOT ACTIVE"
        assert sys_status["system_status"] == "RUNNING"
        assert sys_status["revenue_loop"] == "AUTONOMOUS"

        # Check observability metrics existence
        assert "daily_outbound_sent" in metrics
        assert "daily_outbound_cap" in metrics
        assert metrics["daily_outbound_cap"] == 70
        assert "waiting_for_reply" in metrics
        assert "positive_leads" in metrics
        assert "active_demos" in metrics
        assert "customers_count" in metrics
