import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import (
    Business, PipelineStage, VerificationStatus,
    OutreachMessage, OutreachStatus, FollowupSequence,
    FollowupStatus, Reply, ReplyClassification, ModelPrediction, ProspectMemory
)
from app.ml.reply_intelligence import intelligent_reply_classifier, IntelligentReplyClassifier
from app.ml.cadence_engine import cadence_decision_engine, CadenceDecisionEngine
from app.core.config import settings

@pytest.mark.asyncio
async def test_reply_classifier_text_rules():
    classifier = IntelligentReplyClassifier()

    # 1. Unsubscribe
    unsub = await classifier.classify_text("Please unsubscribe me from this mailing list immediately.")
    assert unsub["classification"] == ReplyClassification.UNSUBSCRIBE.value
    assert unsub["confidence"] >= 0.95
    assert unsub["requires_human_review"] is False

    # 2. Bounce
    bounce = await classifier.classify_text("Mail delivery failed: 550 User unknown host not found")
    assert bounce["classification"] == ReplyClassification.BOUNCE.value
    assert bounce["confidence"] >= 0.95

    # 3. Out of office
    ooo = await classifier.classify_text("I am currently out of the office on annual leave until next Monday.")
    assert ooo["classification"] == ReplyClassification.OUT_OF_OFFICE.value
    assert ooo["confidence"] >= 0.90

    # 4. Referral
    referral = await classifier.classify_text("I am not the right person for this, please reach out to sarah@partnercorp.com")
    assert referral["classification"] == ReplyClassification.REFERRAL.value
    assert referral.get("referral_email") == "sarah@partnercorp.com"
    assert referral["requires_human_review"] is True

    # 5. Meeting request
    meet = await classifier.classify_text("Let's talk. Are you available for a quick zoom screenshare tomorrow morning?")
    assert meet["classification"] == ReplyClassification.MEETING_REQUEST.value
    assert meet["confidence"] >= 0.90

    # 6. Price request
    price = await classifier.classify_text("What is your cost and pricing for the full site remediation?")
    assert price["classification"] == ReplyClassification.PRICE_REQUEST.value
    assert price["confidence"] >= 0.90

    # 7. Postpone / Later
    later = await classifier.classify_text("We are busy right now, please check back next quarter in Q3.")
    assert later["classification"] == ReplyClassification.LATER.value
    assert later["confidence"] >= 0.90

    # 8. Positive interest
    interested = await classifier.classify_text("Sounds good, please send more details on the audit findings.")
    assert interested["classification"] == ReplyClassification.INTERESTED.value
    assert interested["confidence"] >= 0.85

    # 9. Direct decline
    decline = await classifier.classify_text("No thanks, we're good and not interested at this time.")
    assert decline["classification"] == ReplyClassification.NOT_INTERESTED.value
    assert decline["confidence"] >= 0.90

    # 10. Fallback inquiry / question
    inquiry = await classifier.classify_text("Where is your development agency headquartered?")
    assert inquiry["classification"] in (ReplyClassification.QUESTION.value, ReplyClassification.UNKNOWN.value)

@pytest.mark.asyncio
async def test_process_and_record_reply_unsubscribe():
    await init_db()
    uid = uuid.uuid4().hex[:6]
    sender_email = f"lead-{uid}@prospect-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Unsub Prospect {uid}",
            domain=f"prospect-{uid}.com",
            country="US",
            niche="HVAC",
            public_email=sender_email,
            pipeline_stage=PipelineStage.CONTACTED.value,
            verification_status=VerificationStatus.VERIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Process unsubscribe reply
        reply = await intelligent_reply_classifier.process_and_record_reply(
            session=session,
            business_id=biz.id,
            sender_email=sender_email,
            raw_body="Stop emailing me and unsubscribe immediately."
        )

        assert reply.id is not None
        assert reply.classification == ReplyClassification.UNSUBSCRIBE.value

        # Verify business updated to LOST
        await session.refresh(biz)
        assert biz.pipeline_stage == PipelineStage.LOST.value

        # Verify compliance suppression added
        from app.database.models import SuppressionList
        from sqlalchemy import select
        q_supp = select(SuppressionList).where(SuppressionList.email == sender_email)
        supp = (await session.execute(q_supp)).scalar_one_or_none()
        assert supp is not None
        assert supp.reason == "UNSUBSCRIBE"

        # Verify ModelPrediction logged
        q_pred = (
            select(ModelPrediction)
            .where(
                ModelPrediction.entity_id == reply.id,
                ModelPrediction.entity_type == "reply",
                ModelPrediction.model_name == "reply_classifier"
            )
            .order_by(ModelPrediction.id.desc())
        )
        pred = (await session.execute(q_pred)).scalars().first()
        assert pred is not None
        assert pred.metadata_json["category"] == ReplyClassification.UNSUBSCRIBE.value

@pytest.mark.asyncio
async def test_process_and_record_reply_interested_advances_stage():
    await init_db()
    uid = uuid.uuid4().hex[:6]
    sender_email = f"owner-{uid}@dealcorp.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Interested Corp {uid}",
            domain=f"dealcorp-{uid}.com",
            country="US",
            niche="Plumbing",
            public_email=sender_email,
            pipeline_stage=PipelineStage.CONTACTED.value,
            verification_status=VerificationStatus.VERIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        from sqlalchemy import select
        q_mem = select(ProspectMemory).where(ProspectMemory.business_id == biz.id)
        mem = (await session.execute(q_mem)).scalar_one_or_none()
        if not mem:
            mem = ProspectMemory(
                business_id=biz.id,
                domain=biz.domain,
                pipeline_stage=PipelineStage.CONTACTED.value,
                last_interaction="Initial outreach sent",
                next_expected_action="AWAIT_REPLY",
                conversation_history=[]
            )
            session.add(mem)
        else:
            mem.pipeline_stage = PipelineStage.CONTACTED.value
            mem.last_interaction = "Initial outreach sent"
            mem.next_expected_action = "AWAIT_REPLY"
            mem.conversation_history = []
        await session.commit()

        # Ingest positive interest reply
        reply = await intelligent_reply_classifier.process_and_record_reply(
            session=session,
            business_id=biz.id,
            sender_email=sender_email,
            raw_body="Yes please, send more info on how you can fix our mobile speed issues."
        )

        assert reply.classification == ReplyClassification.INTERESTED.value

        # Check stage progression to QUALIFIED_REPLY
        await session.refresh(biz)
        assert biz.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value

        # Check memory history updated
        await session.refresh(mem)
        assert mem.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value
        assert len(mem.conversation_history) >= 2  # Prospect reply + Agent suggested response

@pytest.mark.asyncio
async def test_cadence_engine_channel_routing_and_delays():
    engine = CadenceDecisionEngine()

    biz_with_phone = Business(name="Phone Biz", domain="phonebiz.com", phone="+1-512-555-0100")
    biz_no_phone = Business(name="No Phone Biz", domain="nophone.com", phone=None)

    # Step 2 channel routing
    assert engine.determine_next_channel(biz_with_phone, step_number=2) == "EMAIL"
    assert engine.determine_next_channel(biz_no_phone, step_number=2) == "EMAIL"

    # Step 3 channel routing
    with patch.object(settings, "VOICE_PROVIDER", "dry_run"):
        assert engine.determine_next_channel(biz_with_phone, step_number=3) == "VOICE"
        assert engine.determine_next_channel(biz_no_phone, step_number=3) == "EMAIL"

    with patch.object(settings, "VOICE_PROVIDER", "disabled"):
        assert engine.determine_next_channel(biz_with_phone, step_number=3) == "EMAIL"

    # Scheduled delays
    base = datetime(2026, 9, 1, 12, 0, 0)
    t_step2 = engine.calculate_scheduled_time(base, step_number=2)
    t_step3 = engine.calculate_scheduled_time(base, step_number=3)
    t_step4 = engine.calculate_scheduled_time(base, step_number=4)

    assert (t_step2.date() - base.date()).days == 3
    assert (t_step3.date() - base.date()).days == 7
    assert (t_step4.date() - base.date()).days == 14

@pytest.mark.asyncio
async def test_cadence_engine_schedule_and_safety_dispatch():
    await init_db()
    uid = uuid.uuid4().hex[:6]

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Cadence Client {uid}",
            domain=f"cadence-{uid}.com",
            country="US",
            niche="Roofing",
            public_email=f"contact@cadence-{uid}.com",
            pipeline_stage=PipelineStage.CONTACTED.value,
            verification_status=VerificationStatus.VERIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject=f"Diagnostic audit for {biz.domain}",
            body="Initial outreach body",
            status=OutreachStatus.SENT.value,
            sent_at=datetime.utcnow()
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)

        # Schedule cadence
        sequences = await cadence_decision_engine.schedule_cadence_for_message(
            session=session,
            initial_message=msg,
            business=biz
        )

        assert len(sequences) == 3
        assert sequences[0].step_number == 2
        assert sequences[1].step_number == 3
        assert sequences[2].step_number == 4
        assert sequences[0].status == FollowupStatus.SCHEDULED.value

        # Check safety evaluation when still CONTACTED
        with patch("app.outreach.compliance.compliance_guard.is_suppressed", new_callable=AsyncMock, return_value=False), \
             patch("app.outreach.compliance.compliance_guard.can_send_today", new_callable=AsyncMock, return_value=True):
            decision = await cadence_decision_engine.can_dispatch_followup(session, sequences[0])
            assert decision.allowed is True

        # Advance business stage to WON -> Follow-up must be blocked
        biz.pipeline_stage = PipelineStage.WON.value
        await session.commit()

        decision_blocked = await cadence_decision_engine.can_dispatch_followup(session, sequences[0])
        assert decision_blocked.allowed is False
        assert "already progressed to stage" in decision_blocked.reason
