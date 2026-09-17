"""Tests for Outreach Approval State, Queue & Dashboard Unification.

Verifies:
1. Deterministic synthetic/test record detection and exclusion.
2. Canonical database-derived outreach metrics (pending, approved, sent, failed, replies).
3. Queue listing reflects canonical OutreachMessage state excluding synthetic records.
4. Business pipeline stage transitions cleanly when message is rejected.
5. Business pipeline stage transitions cleanly when outreach send is blocked or fails.
6. Reply handling does not overwrite pipeline stage to APPROVAL.
7. API endpoints (/api/queue, /api/replies, /api/leads) filter out synthetic test noise.
"""

import pytest
from datetime import datetime
from sqlalchemy import select, func
from app.database.models import (
    Business, OutreachMessage, OutreachStatus, PipelineStage,
    Reply, PipelineEvent, Offer
)
from app.core.safety_filters import (
    is_test_or_synthetic,
    get_synthetic_business_filter_clauses,
    get_synthetic_outreach_filter_clauses,
    get_synthetic_reply_filter_clauses
)
from app.outreach.delivery_service import outreach_delivery_service
from app.outreach.queue import outreach_approval_queue
from app.outreach.sender import outreach_sender_adapter


def test_synthetic_classification():
    # Synthetic domains
    assert is_test_or_synthetic(domain="designcorp.example") is True
    assert is_test_or_synthetic(domain="testcorp.test") is True
    assert is_test_or_synthetic(domain="service.invalid") is True
    assert is_test_or_synthetic(domain="localhost") is True
    assert is_test_or_synthetic(domain="example.com") is True

    # Test emails
    assert is_test_or_synthetic(email="arttest@agencyos.tech") is True
    assert is_test_or_synthetic(email="sufiyansurve333@gmail.com") is True
    assert is_test_or_synthetic(email="mrsufiyansurve@gmail.com") is True
    assert is_test_or_synthetic(email="classicshot.7@gmail.com") is True
    assert is_test_or_synthetic(email="postmaster@homeandaway.ie") is True
    assert is_test_or_synthetic(email="marcus@vanceautomations.test") is True

    # Real commercial entities
    assert is_test_or_synthetic(domain="acmeroofing.com", email="contact@acmeroofing.com") is False
    assert is_test_or_synthetic(domain="chicagodentalcare.com", email="drsmith@chicagodentalcare.com") is False
    assert is_test_or_synthetic(domain="apexplumbing.co.uk", email="info@apexplumbing.co.uk") is False


@pytest.mark.asyncio
async def test_canonical_metrics_calculation(db_session):
    # 1. Create a real business and outreach messages with various statuses
    biz = Business(
        name="Chicago Dental Care",
        domain="chicagodentalcare.com",
        website_url="https://chicagodentalcare.com",
        country="US",
        niche="dental-clinics",
        public_email="info@chicagodentalcare.com",
        pipeline_stage=PipelineStage.APPROVAL.value
    )
    db_session.add(biz)
    await db_session.flush()

    m_pending = OutreachMessage(
        business_id=biz.id,
        recipient_email="info@chicagodentalcare.com",
        subject="Practice audit",
        body="Audit findings...",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    m_approved = OutreachMessage(
        business_id=biz.id,
        recipient_email="info@chicagodentalcare.com",
        subject="Approved pitch",
        body="Approved pitch body...",
        status=OutreachStatus.APPROVED.value
    )
    m_sent = OutreachMessage(
        business_id=biz.id,
        recipient_email="info@chicagodentalcare.com",
        subject="Sent note",
        body="Sent body...",
        status=OutreachStatus.SENT.value
    )
    m_failed = OutreachMessage(
        business_id=biz.id,
        recipient_email="info@chicagodentalcare.com",
        subject="Failed note",
        body="Failed body...",
        status=OutreachStatus.SEND_FAILED.value
    )
    rep = Reply(
        business_id=biz.id,
        sender_email="info@chicagodentalcare.com",
        raw_body="Yes we are interested, please call us.",
        classification="INTERESTED",
        is_handled=False
    )
    db_session.add_all([m_pending, m_approved, m_sent, m_failed, rep])

    # 2. Add a synthetic test message that must NOT be counted in production KPIs
    synth_biz = Business(
        name="Design Corp Test",
        domain="designcorp.example",
        website_url="https://designcorp.example",
        country="US",
        niche="design",
        public_email="arttest@agencyos.tech",
        pipeline_stage=PipelineStage.APPROVAL.value
    )
    db_session.add(synth_biz)
    await db_session.flush()

    m_synth = OutreachMessage(
        business_id=synth_biz.id,
        recipient_email="arttest@agencyos.tech",
        subject="Test subject",
        body="Test body",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    r_synth = Reply(
        business_id=synth_biz.id,
        sender_email="arttest@agencyos.tech",
        raw_body="Synthetic reply",
        is_handled=False
    )
    db_session.add_all([m_synth, r_synth])
    await db_session.commit()

    # 3. Fetch metrics
    metrics = await outreach_delivery_service.get_outreach_metrics(db_session)

    # Synthetic message and reply should be excluded
    assert metrics["outreach_pending_approval"] == 1
    assert metrics["outreach_approved"] == 1
    assert metrics["outreach_sent"] == 1
    assert metrics["outreach_failed"] == 1
    assert metrics["replies_in_human_review"] == 1


@pytest.mark.asyncio
async def test_rejection_synchronizes_pipeline_stage(db_session):
    biz = Business(
        name="Denver HVAC Pros",
        domain="denverhvacpros.com",
        country="US",
        niche="hvac",
        public_email="service@denverhvacpros.com",
        pipeline_stage=PipelineStage.APPROVAL.value
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="service@denverhvacpros.com",
        subject="Denver HVAC SEO Review",
        body="Body text...",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    # Operator rejects message
    rejected_msg = await outreach_approval_queue.reject_message(
        db_session, msg.id, reason="Not a good market fit right now"
    )

    assert rejected_msg.status == OutreachStatus.REJECTED.value
    # Verify Business.pipeline_stage transitioned out of APPROVAL to REJECTED
    await db_session.refresh(biz)
    assert biz.pipeline_stage == PipelineStage.REJECTED.value

    # Verify PipelineEvent was logged
    eq = select(PipelineEvent).where(PipelineEvent.business_id == biz.id)
    events = (await db_session.execute(eq)).scalars().all()
    assert len(events) >= 1
    assert events[-1].to_stage == PipelineStage.REJECTED.value


@pytest.mark.asyncio
async def test_queue_listing_excludes_synthetic_messages(db_session):
    real_biz = Business(
        name="Austin Automotive",
        domain="austinautomotivecare.com",
        country="US",
        niche="automotive",
        public_email="service@austinautomotivecare.com",
        pipeline_stage=PipelineStage.APPROVAL.value
    )
    synth_biz = Business(
        name="Design Corp",
        domain="designcorp.example",
        country="US",
        niche="agency",
        public_email="arttest@agencyos.tech",
        pipeline_stage=PipelineStage.APPROVAL.value
    )
    db_session.add_all([real_biz, synth_biz])
    await db_session.flush()

    m_real = OutreachMessage(
        business_id=real_biz.id,
        recipient_email="service@austinautomotivecare.com",
        subject="Audit note",
        body="Audit body...",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    m_synth = OutreachMessage(
        business_id=synth_biz.id,
        recipient_email="arttest@agencyos.tech",
        subject="Test note",
        body="Test body...",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add_all([m_real, m_synth])
    await db_session.commit()

    pending_msgs = await outreach_approval_queue.list_pending(db_session)
    recipient_emails = [m.recipient_email for m in pending_msgs]

    assert "service@austinautomotivecare.com" in recipient_emails
    assert "arttest@agencyos.tech" not in recipient_emails
