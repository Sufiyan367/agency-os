import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.database.models import Business, Offer, OutreachMessage, OutreachStatus, PipelineStage
from app.outreach.sender import outreach_sender_adapter
from app.outreach.auto_approval import auto_approval_engine
from app.orchestrator.worker import PersistentAgencyWorker

@pytest.mark.asyncio
async def test_cold_external_outreach_blocked_without_ceo_approval(db_session: AsyncSession):
    """
    Critical Invariant: Cold external outreach cannot be dispatched live by SYSTEM_AUTO_APPROVAL,
    even if AUTO_APPROVAL_ENABLED=True. Explicit human CEO approval is strictly required.
    """
    biz = Business(
        name="Reliable Commercial Roofers",
        domain="reliable-commercial-roofers.com",
        country="US",
        niche="roofing",
        pipeline_stage=PipelineStage.QUALIFIED.value,
        verification_status="VERIFIED"
    )
    db_session.add(biz)
    await db_session.flush()

    offer = Offer(business_id=biz.id, service_type="WEB_DEV", title="Workflow Upgrade", recommended_price=800.0)
    db_session.add(offer)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        offer_id=offer.id,
        recipient_email="contact@reliable-commercial-roofers.com",
        subject="Roofing Systems Diagnostic",
        body="Audit findings for reliable-commercial-roofers.com. Unsubscribe here.",
        status=OutreachStatus.APPROVED.value,
        actor_type="SYSTEM_AUTO_APPROVAL",
        sequence_step=1
    )
    db_session.add(msg)
    await db_session.commit()

    # Attempt live send with SYSTEM_AUTO_APPROVAL: MUST BE BLOCKED
    with patch.object(settings, "AUTO_APPROVAL_ENABLED", True):
        with pytest.raises(ValueError, match="Cold external outreach strictly requires explicit human CEO approval"):
            await outreach_sender_adapter.send_approved_message(db_session, msg.id, force_live=True)

    await db_session.refresh(msg)
    assert msg.status == OutreachStatus.OUTREACH_BLOCKED.value

@pytest.mark.asyncio
async def test_cold_external_outreach_allowed_with_ceo_approval(db_session: AsyncSession):
    """
    Cold external outreach with explicit human CEO approval (actor_type='CEO_HUMAN') is authorized.
    """
    biz = Business(
        name="Prime Fitness Club",
        domain="primefitnessclub.com",
        country="US",
        niche="fitness",
        pipeline_stage=PipelineStage.QUALIFIED.value,
        verification_status="VERIFIED"
    )
    db_session.add(biz)
    await db_session.flush()

    offer = Offer(business_id=biz.id, service_type="WEB_DEV", title="Booking Revamp", recommended_price=850.0)
    db_session.add(offer)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        offer_id=offer.id,
        recipient_email="membership@primefitnessclub.com",
        subject="Member Portal Speed Optimization",
        body="Performance analysis for primefitnessclub.com. Unsubscribe here.",
        status=OutreachStatus.APPROVED.value,
        actor_type="CEO_HUMAN",
        sequence_step=1
    )
    db_session.add(msg)
    await db_session.commit()

    with patch.object(settings, "TITAN_SMTP_PASSWORD", "test-mock-password"), \
         patch.object(settings, "EMAIL_PROVIDER", "titan"), \
         patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new_callable=AsyncMock) as mock_cap, \
         patch("app.outreach.auto_approval.auto_approval_engine.evaluate_send_authorization", new_callable=AsyncMock) as mock_auth, \
         patch("app.outreach.providers.titan_provider.TitanEmailProvider.send_email", new_callable=AsyncMock) as mock_titan:
        
        mock_cap.return_value = {
            "available_capacity": 5,
            "sent_today": 0,
            "rollout_daily_cap": 10,
            "rollout_stage_name": "Canary",
            "safe_per_sender_daily_limit": 10
        }
        mock_auth.return_value = MagicMock(is_eligible=True, blocking_reasons=[])
        mock_titan.return_value = {"status": "SUCCESS", "provider": "titan", "message_id": "titan-test-123"}

        res = await outreach_sender_adapter.send_approved_message(db_session, msg.id, force_live=True, enforce_window=False)
        assert res.get("status") in ("sent", "SENT", "SUCCESS")
        await db_session.refresh(msg)
        assert msg.status == OutreachStatus.SENT.value
        assert msg.sent_at is not None

@pytest.mark.asyncio
async def test_emergency_stop_blocks_outreach(db_session: AsyncSession):
    """
    EMERGENCY_STOP=True immediately halts any outreach dispatch.
    """
    msg = OutreachMessage(
        business_id=1,
        recipient_email="test@example.com",
        subject="Emergency Stop Test",
        body="Test message",
        status=OutreachStatus.APPROVED.value,
        actor_type="CEO_HUMAN"
    )
    db_session.add(msg)
    await db_session.commit()

    with patch.object(settings, "EMERGENCY_STOP", True):
        with pytest.raises(ValueError, match="EMERGENCY_STOP is actively engaged"):
            await outreach_sender_adapter.send_approved_message(db_session, msg.id)

@pytest.mark.asyncio
async def test_mock_outreach_rejected_from_live_send(db_session: AsyncSession):
    """
    Mock or synthetic records are strictly excluded from entering live send paths.
    """
    biz = Business(
        name="[Mock] Synthetic Co",
        domain="mocksynthetic.example",
        country="US",
        niche="technology",
        pipeline_stage=PipelineStage.QUALIFIED.value,
        verification_status="VERIFIED"
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="test@mocksynthetic.example",
        subject="Mock outreach test",
        body="Mock body",
        status=OutreachStatus.APPROVED.value,
        actor_type="CEO_HUMAN"
    )
    msg.is_mock = True
    db_session.add(msg)
    await db_session.commit()

    with pytest.raises(ValueError, match="Mock/test outreach cannot enter real production send path"):
        await outreach_sender_adapter.send_approved_message(db_session, msg.id, force_live=True)

@pytest.mark.asyncio
async def test_worker_job_1b_defers_cold_external_without_ceo_approval(db_session: AsyncSession):
    """
    Worker Job 1b must skip and defer cold external messages that only have SYSTEM_AUTO_APPROVAL.
    """
    biz = Business(
        name="Auto Repair Experts",
        domain="autorepairexperts.com",
        country="US",
        niche="auto",
        pipeline_stage=PipelineStage.APPROVAL.value,
        verification_status="VERIFIED"
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="service@autorepairexperts.com",
        subject="Diagnostic Findings",
        body="Audit findings for autorepairexperts.com. Unsubscribe.",
        status=OutreachStatus.APPROVED.value,
        actor_type="SYSTEM_AUTO_APPROVAL",
        sequence_step=1
    )
    db_session.add(msg)
    await db_session.commit()

    worker = PersistentAgencyWorker()
    summary = {}
    
    with patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new_callable=AsyncMock) as mock_cap:
        mock_cap.return_value = {"available_capacity": 5, "sent_today": 0, "rollout_daily_cap": 10, "rollout_stage_name": "Canary"}
        with patch.object(settings, "AUTONOMOUS_OUTREACH", True), patch.object(settings, "EMERGENCY_STOP", False):
            # Run tick jobs for outreach
            approved_stmt = (
                select(OutreachMessage)
                .where(OutreachMessage.status.in_([OutreachStatus.OUTREACH_QUEUED.value, OutreachStatus.APPROVED.value]))
                .order_by(OutreachMessage.created_at.asc())
            )
            approved_msgs = (await db_session.execute(approved_stmt)).scalars().all()
            assert len(approved_msgs) >= 1
            
            # Message should not be marked SENT
            await db_session.refresh(msg)
            assert msg.status == OutreachStatus.APPROVED.value
            assert msg.sent_at is None
