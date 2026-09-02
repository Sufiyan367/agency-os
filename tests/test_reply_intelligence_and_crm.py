import pytest
from app.database.models import (
    Business, OutreachMessage, FollowupSequence, FollowupStatus,
    PipelineStage, ReplyClassification, Customer, Project, Payment
)
from app.crm.reply_classifier import reply_classifier
from app.crm.pipeline import pipeline_manager
from app.outreach.compliance import compliance_guard
from datetime import datetime, timedelta
from sqlalchemy import select

@pytest.mark.asyncio
async def test_reply_classification_and_pipeline_advancement(db_session):
    biz = Business(
        name="Summit HVAC Pros",
        domain="summithvactest.com",
        website_url="https://summithvactest.com",
        country="US",
        niche="hvac-services",
        public_email="dispatch@summithvactest.com",
        pipeline_stage=PipelineStage.CONTACTED.value
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email=biz.public_email,
        subject="Audit Note",
        body="Hello",
        status="SENT"
    )
    db_session.add(msg)
    await db_session.flush()

    # Add scheduled follow-up
    fu = FollowupSequence(
        initial_message_id=msg.id,
        step_number=2,
        delay_days=3,
        scheduled_for=datetime.utcnow() + timedelta(days=3),
        subject="Follow up",
        body="Any thoughts?",
        status=FollowupStatus.SCHEDULED.value
    )
    db_session.add(fu)
    await db_session.commit()

    # Process positive reply
    reply_body = "Sounds interesting. Could we meet on Zoom this Friday at 11am?"
    reply = await reply_classifier.process_incoming_reply(
        db_session, business_id=biz.id, sender_email=biz.public_email, raw_body=reply_body
    )

    assert reply.classification in (ReplyClassification.MEETING_REQUEST.value, ReplyClassification.INTERESTED.value)
    assert biz.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value

    # Check follow-up was automatically cancelled!
    await db_session.refresh(fu)
    assert fu.status == FollowupStatus.CANCELLED_REPLY.value

    # Advance to WON
    await pipeline_manager.transition_stage(
        db_session, business_id=biz.id, target_stage=PipelineStage.WON, deal_value=850.0
    )
    assert biz.pipeline_stage == PipelineStage.WON.value

    # Verify Customer and Delivery Project creation
    cust_q = select(Customer).where(Customer.business_id == biz.id)
    cust = (await db_session.execute(cust_q)).scalar_one_or_none()
    assert cust is not None
    assert cust.contract_amount == 850.0

    proj_q = select(Project).where(Project.customer_id == cust.id)
    proj = (await db_session.execute(proj_q)).scalar_one_or_none()
    assert proj is not None
    assert proj.status == "IN_PROGRESS"

@pytest.mark.asyncio
async def test_unsubscribe_reply_adds_to_suppression(db_session):
    biz = Business(
        name="OptOut Corp",
        domain="optoutcorp.com",
        website_url="https://optoutcorp.com",
        country="US",
        niche="accounting-firms",
        public_email="remove@optoutcorp.com"
    )
    db_session.add(biz)
    await db_session.commit()

    reply = await reply_classifier.process_incoming_reply(
        db_session, business_id=biz.id, sender_email="remove@optoutcorp.com", raw_body="Please unsubscribe me immediately"
    )
    assert reply.classification == ReplyClassification.UNSUBSCRIBE.value
    assert await compliance_guard.is_suppressed(db_session, "remove@optoutcorp.com") is True
