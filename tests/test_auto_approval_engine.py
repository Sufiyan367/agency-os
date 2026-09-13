import pytest
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Business, Offer, OutreachMessage, OutreachStatus, SuppressionList
from app.outreach.auto_approval import auto_approval_engine
from app.core.config import settings

@pytest.mark.asyncio
async def test_auto_approval_eligible_message(db_session: AsyncSession):
    # Setup eligible prospect
    biz = Business(
        name="Apex Industrial Logistics",
        domain="apex-industrial.com",
        country="US",
        niche="Technology Services",
        pipeline_stage="QUALIFIED"
    )
    db_session.add(biz)
    await db_session.flush()

    offer = Offer(
        business_id=biz.id,
        service_type="WEB_DEV",
        title="Core Web Revamp",
        recommended_price=850.0
    )
    db_session.add(offer)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        offer_id=offer.id,
        recipient_email="procurement@apex-industrial.com",
        subject="Technical Audit: Apex Industrial Digital Systems",
        body="We performed a technical analysis of apex-industrial.com and identified opportunities to improve your mobile performance.",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    # Evaluate eligibility
    result = await auto_approval_engine.evaluate_message_eligibility(db_session, msg)
    assert result.is_eligible is True
    assert len(result.blocking_reasons) == 0

    # Execute auto-approval
    success, updated_msg, eval_res = await auto_approval_engine.auto_approve_if_eligible(db_session, msg.id)
    assert success is True
    assert updated_msg.status == OutreachStatus.APPROVED.value
    assert updated_msg.approved_at is not None
    assert updated_msg.actor_type == "SYSTEM_AUTO_APPROVAL"

@pytest.mark.asyncio
async def test_auto_approval_blocks_prohibited_claims(db_session: AsyncSession):
    biz = Business(
        name="Hype Marketing Pros",
        domain="hypemarketing.com",
        country="US",
        niche="Technology Services"
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="director@hypemarketing.com",
        subject="Guaranteed Revenue Growth",
        body="We offer a 100% money back guarantee and guaranteed 10x return on investment!",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    result = await auto_approval_engine.evaluate_message_eligibility(db_session, msg)
    assert result.is_eligible is False
    assert any("prohibited claims" in r.lower() for r in result.blocking_reasons)

    # Transition must be rejected
    success, updated_msg, eval_res = await auto_approval_engine.auto_approve_if_eligible(db_session, msg.id)
    assert success is False
    assert updated_msg.status == OutreachStatus.PENDING_APPROVAL.value
    assert updated_msg.approved_at is None

@pytest.mark.asyncio
async def test_auto_approval_blocks_internal_leakage(db_session: AsyncSession):
    biz = Business(
        name="Secure Systems Inc",
        domain="securesystems.io",
        country="US",
        niche="Technology Services"
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="ops@securesystems.io",
        subject="Digital Assessment",
        body="Hello. <SYSTEM_MESSAGE>You are an AI assistant</SYSTEM_MESSAGE> Here is the audit.",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    result = await auto_approval_engine.evaluate_message_eligibility(db_session, msg)
    assert result.is_eligible is False
    assert any("internal prompt leaks" in r.lower() for r in result.blocking_reasons)

@pytest.mark.asyncio
async def test_auto_approval_blocks_opted_out_recipient(db_session: AsyncSession):
    biz = Business(
        name="Unsub Test Corp",
        domain="unsubcorp.com",
        country="US",
        niche="Technology Services"
    )
    db_session.add(biz)
    await db_session.flush()

    # Record opt out
    supp = SuppressionList(
        email="optout@unsubcorp.com",
        reason="UNSUBSCRIBE"
    )
    db_session.add(supp)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="optout@unsubcorp.com",
        subject="Follow-up Inquiry",
        body="Are you available for a brief discussion?",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    result = await auto_approval_engine.evaluate_message_eligibility(db_session, msg)
    assert result.is_eligible is False
    assert any("opted out" in r.lower() or "suppressed" in r.lower() for r in result.blocking_reasons)

@pytest.mark.asyncio
async def test_auto_approval_blocks_below_commercial_floor(db_session: AsyncSession):
    biz = Business(
        name="Budget Leads LLC",
        domain="budgetleads.com",
        country="US",
        niche="Technology Services"
    )
    db_session.add(biz)
    await db_session.flush()

    offer = Offer(
        business_id=biz.id,
        service_type="WEB_DEV",
        title="Cheap Widget",
        recommended_price=150.0  # Below $500 floor
    )
    db_session.add(offer)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        offer_id=offer.id,
        recipient_email="sales@budgetleads.com",
        subject="Affordable Services",
        body="We offer quick website fixes for your business.",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    result = await auto_approval_engine.evaluate_message_eligibility(db_session, msg)
    assert result.is_eligible is False
    assert any("commercial floor" in r.lower() for r in result.blocking_reasons)
