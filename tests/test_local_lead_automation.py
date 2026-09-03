import pytest
from datetime import datetime, timedelta
from app.ai.mock import MockAIProvider
from app.ai.factory import get_ai_provider
from app.ai.schemas import LeadQualificationResult, ReplyClassificationResult
from app.agents.qualifier import LeadQualificationAgent
from app.providers.mock import MockMessageProvider
from app.services.followup_engine import FollowUpEngine
from app.database.connection import AsyncSessionLocal, init_db
from app.models.entities import Business, Lead, Audit, OutreachMessage, FollowupSchedule, LeadEvent, EventType, LeadStatus, FollowupStatus
from app.services.qualification import QualificationService
from app.services.outreach import OutreachService

@pytest.mark.asyncio
async def test_ai_provider_abstraction():
    provider = get_ai_provider("mock")
    assert provider.provider_name == "mock"

    qual = await provider.qualify_lead(
        {"name": "Metro HVAC", "niche": "HVAC"},
        {"overall_health_score": 25.0, "performance_score": 20.0, "seo_score": 30.0, "mobile_responsive": False}
    )
    assert isinstance(qual, LeadQualificationResult)
    assert qual.lead_score >= 70.0
    assert qual.qualification in ("HOT", "WARM")
    assert len(qual.pain_points) > 0

@pytest.mark.asyncio
async def test_inbound_reply_classification_and_stop():
    provider = MockAIProvider()
    
    # Test unsubscribe detection
    reply1 = await provider.classify_reply("Please unsubscribe me from your emails immediately.", [], {})
    assert reply1.classification == "UNSUBSCRIBE"
    assert reply1.suggested_action == "STOP_FOLLOWUP"

    # Test booking interest
    reply2 = await provider.classify_reply("Can you send me the calendar link? I want to book a call tomorrow.", [], {})
    assert reply2.classification == "INTERESTED"
    assert reply2.suggested_action == "BOOK_CALL"
    assert reply2.needs_human is True

@pytest.mark.asyncio
async def test_lead_qualification_agent_and_scoring():
    agent = LeadQualificationAgent(MockAIProvider())
    res = await agent.qualify(
        {"name": "Downtown Dentist", "niche": "Dental", "domain": "downtowndentist.com"},
        {"overall_health_score": 30.0, "performance_score": 25.0, "seo_score": 35.0, "mobile_responsive": False}
    )
    assert res.lead_score >= 75.0
    assert res.qualification in ("HOT", "WARM")
    assert "Slow mobile page load speed" in res.pain_points[0]

@pytest.mark.asyncio
async def test_mock_message_provider_audit_dispatch():
    msg_provider = MockMessageProvider()
    result = await msg_provider.send_message(
        recipient="owner@testbiz.com",
        subject="Audit review",
        body="Here are the findings",
        lead_id=999
    )
    assert result.status == "MOCKED_SENT"
    assert result.is_mocked is True
    assert result.message_id.startswith("mock-")
    
    history = await msg_provider.get_sent_messages(lead_id=999)
    assert len(history) == 1
    assert history[0].recipient == "owner@testbiz.com"

@pytest.mark.asyncio
async def test_followup_engine_duplicate_prevention_and_cancellation():
    await init_db()
    async with AsyncSessionLocal() as db:
        # Create test business & lead
        biz = Business(name="Test Plumbing", domain=f"plumb-{datetime.utcnow().timestamp()}.com", niche="Plumbing")
        db.add(biz)
        await db.commit()
        await db.refresh(biz)

        lead = Lead(business_id=biz.id, contact_name="Bob", contact_email=f"bob-{biz.id}@test.com")
        db.add(lead)
        await db.commit()
        await db.refresh(lead)

        engine = FollowUpEngine(time_compression_factor=86400.0)
        schedules = await engine.schedule_sequence_for_lead(db, lead.id)
        assert len(schedules) == 3

        # Duplicate schedule must raise ValueError
        with pytest.raises(ValueError, match="already active"):
            await engine.schedule_sequence_for_lead(db, lead.id)

        # Cancel followups
        cancelled = await engine.cancel_followups_for_lead(db, lead.id, reason="Customer replied")
        assert cancelled == 3

@pytest.mark.asyncio
async def test_human_takeover_blocks_outreach_and_followups():
    await init_db()
    async with AsyncSessionLocal() as db:
        biz = Business(name="Roofing Co", domain=f"roof-{datetime.utcnow().timestamp()}.com", niche="Roofing")
        db.add(biz)
        await db.commit()
        await db.refresh(biz)

        lead = Lead(business_id=biz.id, contact_name="Alice", contact_email=f"alice-{biz.id}@test.com")
        db.add(lead)
        await db.commit()
        await db.refresh(lead)

        outreach_svc = OutreachService()
        msg = await outreach_svc.draft_outreach_for_lead(db, lead.id)
        assert msg.status == "PENDING_APPROVAL"

        # Enable Human Takeover
        lead.human_takeover = True
        lead.human_takeover_reason = "Manual takeover test"
        await db.commit()

        # Approval must be rejected due to human takeover
        with pytest.raises(RuntimeError, match="Human takeover is ACTIVE"):
            await outreach_svc.approve_and_send(db, msg.id)

@pytest.mark.asyncio
async def test_lead_event_audit_trail_recorded():
    await init_db()
    async with AsyncSessionLocal() as db:
        biz = Business(name="Auto Care", domain=f"auto-{datetime.utcnow().timestamp()}.com", niche="Auto Repair")
        db.add(biz)
        await db.commit()
        await db.refresh(biz)

        lead = Lead(business_id=biz.id, contact_name="Charlie", contact_email=f"charlie-{biz.id}@test.com")
        db.add(lead)
        await db.commit()
        await db.refresh(lead)

        qual_svc = QualificationService()
        await qual_svc.qualify_lead_record(db, lead.id)

        from sqlalchemy import select
        events_res = await db.execute(select(LeadEvent).where(LeadEvent.lead_id == lead.id))
        events = events_res.scalars().all()
        assert len(events) >= 1
        assert events[0].event_type == EventType.LEAD_QUALIFIED.value
