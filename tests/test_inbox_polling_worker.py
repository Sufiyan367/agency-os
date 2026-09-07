import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import init_db
from app.database.models import (
    Business, AuditRun, AuditFinding, Offer, OutreachMessage,
    FollowupSequence, FollowupStatus, PipelineStage, Reply,
    ReplyClassification, OutreachEvent, Proposal, PipelineEvent
)
from app.crm.inbox_poller import InboxPoller, inbox_poller
from app.orchestrator.worker import PersistentAgencyWorker
from app.acquisition.autonomous_controller import autonomous_acquisition_controller
from app.core.config import settings


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()


async def create_audited_test_business(session: AsyncSession) -> Business:
    """Helper to create a fully audited business with an offer for pipeline integration tests."""
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name=f"Cascade Commercial Plumbing {uid}",
        domain=f"cascade-{uid}.com",
        country="US",
        city="Seattle",
        niche="commercial_plumbing",
        public_email=f"service@cascade-{uid}.com",
        email_status="verified",
        pipeline_stage=PipelineStage.CONTACTED.value
    )
    session.add(biz)
    await session.flush()

    audit = AuditRun(
        business_id=biz.id,
        url_audited=f"https://{biz.domain}/",
        performance_score=48.0,
        seo_score=92.0,
        a11y_score=75.0,
        ux_conversion_score=85.0,
        security_score=100.0,
        content_score=88.0,
        overall_health_score=78.0,
        summary="Audit summary: Excessive TTFB and uncompressed hero assets."
    )
    session.add(audit)
    await session.flush()

    finding = AuditFinding(
        audit_id=audit.id,
        category="Performance",
        finding="High TTFB Latency",
        severity="HIGH",
        evidence="Observed TTFB of 1,450ms on mobile profile.",
        url=f"https://{biz.domain}/",
        recommended_fix="Implement edge CDN caching.",
        estimated_business_impact="Elevated bounce rate."
    )
    session.add(finding)
    await session.flush()

    offer = Offer(
        business_id=biz.id,
        title="Core Web Vitals & Load Speed Acceleration",
        service_type="Speed Optimization",
        recommended_price=650.0,
        estimated_delivery_days=5,
        deliverables=["Edge CDN caching", "Asset compression"]
    )
    session.add(offer)
    await session.commit()
    await session.refresh(biz)
    return biz


# ----------------------------------------------------------------------
# 1. Worker invokes InboxPoller on its configured interval/schedule
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_invokes_inbox_poller_on_schedule():
    custom_worker = PersistentAgencyWorker(interval_seconds=15)
    assert custom_worker.interval_seconds == 15
    assert custom_worker.is_running is False

    default_worker = PersistentAgencyWorker()
    expected_default = getattr(settings, "WORKER_TICK_INTERVAL_SECONDS", None) or getattr(settings, "INBOX_POLL_INTERVAL_SECONDS", 60)
    assert default_worker.interval_seconds == expected_default

    with patch("app.crm.inbox_poller.inbox_poller.poll_inbox", new_callable=AsyncMock) as mock_poll, \
         patch("app.followups.engine.followup_engine.process_due_followups", new_callable=AsyncMock) as mock_fu, \
         patch("app.payments.provider.stripe_payment_provider.fetch_completed_sessions", new_callable=AsyncMock), \
         patch("app.orchestrator.loop.orchestrator.run_full_autonomous_cycle", new_callable=AsyncMock):
        mock_poll.return_value = []
        mock_fu.return_value = []

        summary = await custom_worker.execute_tick()
        assert summary["status"] == "SUCCESS"
        mock_poll.assert_called_once()
        assert summary["inbox_replies_processed"] == 0
        assert custom_worker.ticks_executed == 1


# ----------------------------------------------------------------------
# 2. Newly discovered inbound message is processed
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_newly_discovered_inbound_message_processed(db_session):
    biz = Business(
        name="Apex Commercial Roofing",
        domain="apexroofingny.com",
        website_url="https://apexroofingny.com",
        country="US",
        niche="commercial_roofing",
        public_email="info@apexroofingny.com",
        pipeline_stage=PipelineStage.CONTACTED.value
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="info@apexroofingny.com",
        subject="Audit Observation for Apex Roofing",
        body="Diagnostic report available.",
        status="SENT"
    )
    db_session.add(msg)
    await db_session.flush()

    fu = FollowupSequence(
        initial_message_id=msg.id,
        step_number=1,
        scheduled_for=datetime.utcnow() + timedelta(days=2),
        subject="Quick follow-up",
        body="Checking in...",
        status=FollowupStatus.SCHEDULED.value
    )
    db_session.add(fu)
    await db_session.commit()

    reply = await inbox_poller.process_inbound_message(
        session=db_session,
        sender_email="info@apexroofingny.com",
        subject="Re: Audit Observation for Apex Roofing",
        body="We are definitely interested in seeing the diagnostic findings and turnaround plan.",
        gmail_message_id="gmail_msg_new_001",
        message_id_header="<apex_001@apexroofingny.com>"
    )

    assert reply is not None
    assert reply.business_id == biz.id
    assert reply.classification == ReplyClassification.INTERESTED.value
    assert reply.outreach_message_id == msg.id

    # Verify DB persistence of reply
    db_reply = (await db_session.execute(select(Reply).where(Reply.id == reply.id))).scalars().first()
    assert db_reply is not None
    assert db_reply.classification == ReplyClassification.INTERESTED.value

    # Verify pending follow-up cancellation
    await db_session.refresh(fu)
    assert fu.status == FollowupStatus.CANCELLED_REPLY.value

    # Verify business pipeline stage advance
    await db_session.refresh(biz)
    assert biz.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value


# ----------------------------------------------------------------------
# 3. Duplicate message is not processed twice
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_message_not_processed_twice(db_session):
    biz = Business(
        name="Desert Sun Mechanical",
        domain="desertsunmech.com",
        website_url="https://desertsunmech.com",
        country="US",
        niche="hvac",
        public_email="service@desertsunmech.com",
        pipeline_stage=PipelineStage.CONTACTED.value
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="service@desertsunmech.com",
        subject="Efficiency analysis for Desert Sun",
        body="Here are initial observations.",
        status="SENT"
    )
    db_session.add(msg)
    await db_session.commit()

    # Pass #1: First delivery of message
    first_reply = await inbox_poller.process_inbound_message(
        session=db_session,
        sender_email="service@desertsunmech.com",
        subject="Re: Efficiency analysis for Desert Sun",
        body="Yes, send us the pricing and breakdown.",
        gmail_message_id="gmail_dup_unique_999",
        message_id_header="<dup_999@desertsunmech.com>"
    )
    assert first_reply is not None
    assert inbox_poller.is_message_processed("gmail_dup_unique_999") is True

    # Pass #2: Exact same message delivered again (same gmail_message_id)
    second_reply = await inbox_poller.process_inbound_message(
        session=db_session,
        sender_email="service@desertsunmech.com",
        subject="Re: Efficiency analysis for Desert Sun",
        body="Yes, send us the pricing and breakdown.",
        gmail_message_id="gmail_dup_unique_999",
        message_id_header="<dup_999@desertsunmech.com>"
    )
    assert second_reply is None, "Duplicate message must be rejected and return None"

    # Pass #3: Simulate worker restart (in-memory cleared) — database event check prevents duplicate
    fresh_poller = InboxPoller()
    assert fresh_poller.is_message_processed("gmail_dup_unique_999") is False

    third_reply = await fresh_poller.process_inbound_message(
        session=db_session,
        sender_email="service@desertsunmech.com",
        subject="Re: Efficiency analysis for Desert Sun",
        body="Yes, send us the pricing and breakdown.",
        gmail_message_id="gmail_dup_unique_999",
        message_id_header="<dup_999@desertsunmech.com>"
    )
    assert third_reply is None, "Database event deduplication must reject message even after in-memory restart"

    # Pass #4: Check that DB contains strictly ONE reply for this business
    q = select(Reply).where(Reply.business_id == biz.id)
    all_replies = (await db_session.execute(q)).scalars().all()
    assert len(all_replies) == 1


# ----------------------------------------------------------------------
# 4. Gmail/API failure is handled safely
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gmail_api_failure_handled_safely(db_session):
    worker = PersistentAgencyWorker(interval_seconds=1)

    mock_provider = MagicMock()
    mock_provider.list_unread_messages.side_effect = RuntimeError("Gmail API 503 Service Unavailable: rate limit exceeded")

    with patch("app.core.config.settings.GMAIL_CLIENT_ID", "mock_client_id"), \
         patch("app.core.config.settings.GMAIL_REFRESH_TOKEN", "mock_refresh_token"), \
         patch("app.core.config.settings.EMAIL_PROVIDER", "gmail_oauth"), \
         patch("app.outreach.providers.gmail_oauth_provider.GmailOAuthEmailProvider", return_value=mock_provider), \
         patch("app.followups.engine.followup_engine.process_due_followups", new_callable=AsyncMock, return_value=[]), \
         patch("app.payments.provider.stripe_payment_provider.fetch_completed_sessions", new_callable=AsyncMock, return_value=[]), \
         patch("app.orchestrator.loop.orchestrator.run_full_autonomous_cycle", new_callable=AsyncMock):

        # inbox_poller.poll_gmail handles failure gracefully without throwing
        gmail_replies = await inbox_poller.poll_gmail(db_session)
        assert gmail_replies == []

        # inbox_poller.poll_inbox handles failure gracefully
        inbox_replies = await inbox_poller.poll_inbox(db_session)
        assert inbox_replies == []

        # Worker tick executes safely without crashing
        summary = await worker.execute_tick()
        assert summary["status"] == "SUCCESS"
        assert summary["inbox_replies_processed"] == 0


# ----------------------------------------------------------------------
# 5. INTERESTED reply reaches existing AutonomousController pipeline
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_interested_reply_reaches_autonomous_controller(db_session):
    biz = await create_audited_test_business(db_session)

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email=biz.public_email,
        subject="Audit Observation",
        body="Initial report.",
        status="SENT"
    )
    db_session.add(msg)
    await db_session.commit()

    # Create an INTERESTED reply record
    reply = Reply(
        business_id=biz.id,
        outreach_message_id=msg.id,
        sender_email=biz.public_email,
        raw_body="Sounds good, we are definitely interested! Send more details and scope.",
        classification="INTERESTED",
        confidence=0.92
    )
    db_session.add(reply)
    await db_session.commit()

    worker = PersistentAgencyWorker(interval_seconds=1)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session_ctx():
        yield db_session

    with patch("app.orchestrator.worker.AsyncSessionLocal", side_effect=mock_session_ctx), \
         patch("app.crm.inbox_poller.inbox_poller.poll_inbox", new_callable=AsyncMock, return_value=[reply]), \
         patch("app.followups.engine.followup_engine.process_due_followups", new_callable=AsyncMock, return_value=[]), \
         patch("app.payments.provider.stripe_payment_provider.fetch_completed_sessions", new_callable=AsyncMock, return_value=[]), \
         patch("app.orchestrator.loop.orchestrator.run_full_autonomous_cycle", new_callable=AsyncMock):

        summary = await worker.execute_tick()
        assert summary["status"] == "SUCCESS"
        assert summary["inbox_replies_processed"] == 1

        # Verify proposal was created by the AutonomousController pipeline
        prop_q = select(Proposal).where(Proposal.business_id == biz.id)
        proposals = (await db_session.execute(prop_q)).scalars().all()
        assert len(proposals) >= 1
        assert proposals[0].status == "DRAFT"

        # Verify CEO Alert event was created
        events_q = select(PipelineEvent).where(PipelineEvent.business_id == biz.id)
        events = (await db_session.execute(events_q)).scalars().all()
        ceo_alerts = [e for e in events if "[CEO ALERT]" in (e.note or "")]
        assert len(ceo_alerts) >= 1


# ----------------------------------------------------------------------
# 6. Existing dry-run email safety remains intact
# ----------------------------------------------------------------------
def test_dry_run_email_safety_intact():
    assert settings.EMAIL_DRY_RUN is True
    assert settings.DRY_RUN is True


# ----------------------------------------------------------------------
# 7. Existing payment dry-run safety remains intact
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_payment_dry_run_safety_intact(db_session):
    assert settings.PAYMENTS_ENABLED is False
    assert settings.PAYMENT_DRY_RUN is True

    biz = await create_audited_test_business(db_session)

    res = await autonomous_acquisition_controller._step_process_reply(
        session=db_session,
        business_id=biz.id,
        reply_category="INTERESTED",
        reply_body="Yes, we are interested in moving forward."
    )

    assert res["status"] == "SUCCESS"
    handoff = res["payment_handoff"]
    assert handoff is not None
    assert handoff.payments_enabled is False
    assert handoff.payment_provider == "dry_run"
    assert handoff.payment_status == "PENDING_AUTHORIZATION"
    assert handoff.approval_requirements == "HUMAN_APPROVAL_REQUIRED"
