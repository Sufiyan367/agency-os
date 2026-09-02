import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from app.database.models import (
    Business, OutreachMessage, FollowupSequence, FollowupStatus,
    PipelineStage, ReplyClassification, SuppressionList
)
from app.crm.inbox_poller import inbox_poller
from app.crm.reply_classifier import reply_classifier
from app.followups.engine import followup_engine
from app.outreach.compliance import compliance_guard

@pytest.mark.asyncio
async def test_inbox_message_matching_and_interested_reply(db_session):
    biz = Business(
        name="Horizon Commercial Roofing",
        domain="horizonroofs.com",
        website_url="https://horizonroofs.com",
        country="US",
        niche="commercial_roofing",
        public_email="director@horizonroofs.com",
        pipeline_stage=PipelineStage.CONTACTED.value
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="director@horizonroofs.com",
        subject="Audit review for Horizon",
        body="Here are findings...",
        status="SENT"
    )
    db_session.add(msg)
    await db_session.flush()

    # Schedule a follow-up
    fu = FollowupSequence(
        initial_message_id=msg.id,
        step_number=1,
        scheduled_for=datetime.utcnow() + timedelta(days=3),
        subject="Quick bump on our audit",
        body="Following up...",
        status=FollowupStatus.SCHEDULED.value
    )
    db_session.add(fu)
    await db_session.commit()

    # Ingest an interested reply
    reply = await inbox_poller.process_inbound_message(
        session=db_session,
        sender_email="director@horizonroofs.com",
        subject="Re: Audit review for Horizon",
        body="This sounds very interesting. Could you send the full audit report and pricing?"
    )

    assert reply is not None
    assert reply.classification in (ReplyClassification.INTERESTED.value, ReplyClassification.PRICE_REQUEST.value)
    assert reply.confidence >= 0.85

    # Check that pending follow-up was automatically CANCELLED
    await db_session.refresh(fu)
    assert fu.status == FollowupStatus.CANCELLED_REPLY.value

    # Check that CRM pipeline advanced to QUALIFIED_REPLY
    await db_session.refresh(biz)
    assert biz.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value

@pytest.mark.asyncio
async def test_unsubscribe_auto_stop_and_suppression(db_session):
    biz = Business(
        name="Optout Construction Co",
        domain="optoutco.com",
        website_url="https://optoutco.com",
        country="US",
        niche="commercial_roofing",
        public_email="manager@optoutco.com",
        pipeline_stage=PipelineStage.CONTACTED.value
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="manager@optoutco.com",
        subject="Audit for Optout Co",
        body="Here are findings...",
        status="SENT"
    )
    db_session.add(msg)
    await db_session.flush()

    fu = FollowupSequence(
        initial_message_id=msg.id,
        step_number=1,
        scheduled_for=datetime.utcnow() + timedelta(days=3),
        subject="Quick bump",
        body="Following up...",
        status=FollowupStatus.SCHEDULED.value
    )
    db_session.add(fu)
    await db_session.commit()

    # Ingest explicit unsubscribe reply
    reply = await inbox_poller.process_inbound_message(
        session=db_session,
        sender_email="manager@optoutco.com",
        subject="Re: Audit for Optout Co",
        body="Please unsubscribe me from your mailing list and remove my email."
    )

    assert reply is not None
    assert reply.classification == ReplyClassification.UNSUBSCRIBE.value

    # Check that pending follow-up was auto-stopped with CANCELLED_UNSUB
    await db_session.refresh(fu)
    assert fu.status == FollowupStatus.CANCELLED_UNSUB.value

    # Check that email was added to SuppressionList
    is_suppressed = await compliance_guard.is_suppressed(db_session, "manager@optoutco.com")
    assert is_suppressed is True

    # Check that CRM pipeline stage moved to LOST
    await db_session.refresh(biz)
    assert biz.pipeline_stage == PipelineStage.LOST.value

@pytest.mark.asyncio
async def test_bounce_auto_stop_and_suppression(db_session):
    biz = Business(
        name="Bounced Enterprise",
        domain="bouncedbiz.com",
        website_url="https://bouncedbiz.com",
        country="US",
        niche="commercial_roofing",
        public_email="invalid@bouncedbiz.com",
        pipeline_stage=PipelineStage.CONTACTED.value
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="invalid@bouncedbiz.com",
        subject="Audit for Bounced Enterprise",
        body="Here are findings...",
        status="SENT"
    )
    db_session.add(msg)
    await db_session.flush()

    fu = FollowupSequence(
        initial_message_id=msg.id,
        step_number=1,
        scheduled_for=datetime.utcnow() + timedelta(days=2),
        subject="Follow-up bump",
        body="Following up...",
        status=FollowupStatus.SCHEDULED.value
    )
    db_session.add(fu)
    await db_session.commit()

    # Ingest automated bounce notice
    reply = await inbox_poller.process_inbound_message(
        session=db_session,
        sender_email="invalid@bouncedbiz.com",
        subject="Delivery Status Notification (Failure)",
        body="550 5.1.1 User unknown. Mail delivery failed: address not found."
    )

    assert reply is not None
    assert reply.classification == ReplyClassification.BOUNCE.value

    await db_session.refresh(fu)
    assert fu.status == FollowupStatus.CANCELLED_UNSUB.value

    is_suppressed = await compliance_guard.is_suppressed(db_session, "invalid@bouncedbiz.com")
    assert is_suppressed is True

@pytest.mark.asyncio
async def test_process_due_followups_execution(db_session):
    biz = Business(
        name="Scheduled Followup LLC",
        domain="scheduledllc.com",
        website_url="https://scheduledllc.com",
        country="US",
        niche="commercial_roofing",
        public_email="team@scheduledllc.com",
        pipeline_stage=PipelineStage.CONTACTED.value
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="team@scheduledllc.com",
        subject="Initial outreach",
        body="Our findings...",
        status="SENT"
    )
    db_session.add(msg)
    await db_session.flush()

    # Schedule follow-up due in past
    past_date = datetime.utcnow() - timedelta(hours=1)
    fu = FollowupSequence(
        initial_message_id=msg.id,
        step_number=1,
        scheduled_for=past_date,
        subject="Just following up on the audit",
        body="Did you have a chance to review?",
        status=FollowupStatus.SCHEDULED.value
    )
    db_session.add(fu)
    await db_session.commit()

    sent = await followup_engine.process_due_followups(db_session)
    assert len(sent) == 1
    assert sent[0].id == fu.id
    assert sent[0].status == FollowupStatus.SENT.value
    assert sent[0].sent_at is not None
