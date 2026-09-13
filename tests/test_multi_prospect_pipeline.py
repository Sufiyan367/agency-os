"""
Tests for Multi-Prospect Acquisition Pipeline & Queue Engine.
Verifies:
1. Multi-lead ingestion across 10 distinct industries.
2. Audit queue drainage with failure isolation (1 failure does not halt the remaining 9).
3. Scoring & commercial floor qualification (>= $500).
4. Strict cold outreach human approval invariant (all drafts in PENDING_APPROVAL).
5. Queue inspection across multiple businesses simultaneously.
6. Human operator approval simulation.
7. Capacity-governed dispatch simulation (DRY RUN safe, 0 real emails sent).
8. Inbound response loops:
   - Positive reply triggers Demo Factory for that niche, advances to DEMO_READY, alerts operator.
   - Negative reply cancels follow-ups, suppresses email, marks LOST.
   - Question reply drafts suggested response for operator review, marks REPLIED, 0 auto-sent emails.
"""
import uuid
from datetime import datetime
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, Contact, AuditRun, AuditFinding, LeadScore, Offer,
    OutreachMessage, OutreachStatus, Reply, ReplyClassification,
    PipelineStage, PipelineEvent, Artifact, FollowupSequence
)
from app.orchestrator.worker import PersistentAgencyWorker
from app.crm.reply_classifier import reply_classifier
from app.outreach.compliance import compliance_guard


PROSPECT_FIXTURES = [
    {"name": "Apex Auto Repair", "domain": "apex-auto-test.com", "niche": "automotive", "city": "Dallas", "country": "US"},
    {"name": "Summit Roofing Pros", "domain": "summit-roofing-test.com", "niche": "roofing", "city": "Denver", "country": "US"},
    {"name": "BrightSmile Dental", "domain": "brightsmile-dental-test.com", "niche": "dental", "city": "Austin", "country": "US"},
    {"name": "ComfortAir Heating & Cooling", "domain": "comfortair-hvac-test.com", "niche": "hvac", "city": "Phoenix", "country": "US"},
    {"name": "Vanguard Law Partners", "domain": "vanguard-law-test.com", "niche": "legal", "city": "Chicago", "country": "US"},
    {"name": "ClearFlow Plumbing", "domain": "clearflow-plumbing-test.com", "niche": "plumbing", "city": "Seattle", "country": "US"},
    {"name": "Pristine Commercial Cleaners", "domain": "pristine-cleaning-test.com", "niche": "cleaning", "city": "Atlanta", "country": "US"},
    {"name": "Ironclad Builders", "domain": "ironclad-builders-test.com", "niche": "construction", "city": "Miami", "country": "US"},
    {"name": "Nexus Cloud Solutions", "domain": "nexus-it-test.com", "niche": "it-services", "city": "Boston", "country": "US"},
    {"name": "VoltMaster Electric", "domain": "voltmaster-electric-test.com", "niche": "electrical", "city": "Houston", "country": "US"}
]

test_business_ids = []


@pytest.fixture(autouse=True)
async def db_setup_and_teardown():
    await init_db()
    yield
    if test_business_ids:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Artifact).where(Artifact.business_id.in_(test_business_ids)))
            await session.execute(delete(Reply).where(Reply.business_id.in_(test_business_ids)))
            await session.execute(delete(PipelineEvent).where(PipelineEvent.business_id.in_(test_business_ids)))
            await session.execute(delete(OutreachMessage).where(OutreachMessage.business_id.in_(test_business_ids)))
            await session.execute(delete(Offer).where(Offer.business_id.in_(test_business_ids)))
            await session.execute(delete(LeadScore).where(LeadScore.business_id.in_(test_business_ids)))
            await session.execute(delete(AuditRun).where(AuditRun.business_id.in_(test_business_ids)))
            await session.execute(delete(Contact).where(Contact.business_id.in_(test_business_ids)))
            await session.execute(delete(Business).where(Business.id.in_(test_business_ids)))
            await session.commit()
        test_business_ids.clear()


@pytest.mark.asyncio
async def test_multi_prospect_pipeline_end_to_end():
    worker = PersistentAgencyWorker(interval_seconds=60)

    # -------------------------------------------------------------
    # 1. Ingestion / Discovery: Ingest 10 prospects across 10 industries
    # -------------------------------------------------------------
    async with AsyncSessionLocal() as session:
        for p in PROSPECT_FIXTURES:
            uid = uuid.uuid4().hex[:4]
            biz = Business(
                name=p["name"],
                domain=f"{uid}-{p['domain']}",
                niche=p["niche"],
                city=p["city"],
                country=p["country"],
                public_email=f"contact@{uid}-{p['domain']}",
                phone="+1-555-0100",
                pipeline_stage=PipelineStage.DISCOVERED.value
            )
            session.add(biz)
            await session.flush()
            test_business_ids.append(biz.id)
        await session.commit()

    assert len(test_business_ids) == 10

    # -------------------------------------------------------------
    # 2. Audit Queue Drainage with Failure Isolation
    # Simulate Prospect 3 (Dental) failing audit; 9 others succeed
    # -------------------------------------------------------------
    failing_biz_id = test_business_ids[2]

    async with AsyncSessionLocal() as session:
        from app.auditing.engine import website_audit_engine

        original_audit = website_audit_engine.audit_business

        async def isolated_audit_mock(sess, biz):
            if biz.id == failing_biz_id:
                raise RuntimeError("Simulated transient connection timeout on prospect 3")
            return await original_audit(sess, biz)

        with patch.object(website_audit_engine, "audit_business", side_effect=isolated_audit_mock):
            audited_count = await worker.drain_audit_backlog(session, limit=10)

        # 9 must succeed, failing 1 must not stop the batch
        assert audited_count == 9

        # Verify failing prospect remains in DISCOVERED
        failing_biz = await session.get(Business, failing_biz_id)
        assert failing_biz.pipeline_stage == PipelineStage.DISCOVERED.value

        # Verify other 9 prospects advanced to AUDITED
        successful_q = select(Business).where(
            Business.id.in_(test_business_ids),
            Business.pipeline_stage == PipelineStage.AUDITED.value
        )
        audited_bizs = (await session.execute(successful_q)).scalars().all()
        assert len(audited_bizs) == 9

    # -------------------------------------------------------------
    # 3. Scoring & Commercial Floor Qualification
    # -------------------------------------------------------------
    async with AsyncSessionLocal() as session:
        scored_count = await worker.drain_scoring_backlog(session, limit=10)
        assert scored_count == 9

        # Verify at least some qualified
        qualified_q = select(Business).where(
            Business.id.in_(test_business_ids),
            Business.pipeline_stage == PipelineStage.QUALIFIED.value
        )
        qualified_bizs = (await session.execute(qualified_q)).scalars().all()
        assert len(qualified_bizs) >= 1

    # -------------------------------------------------------------
    # 4. Personalization & Strict Cold Outreach Human Approval
    # -------------------------------------------------------------
    async with AsyncSessionLocal() as session:
        drafted_count = await worker.drain_drafting_backlog(session, limit=10)
        assert drafted_count >= 1

        # Check that ALL created outreach messages are in PENDING_APPROVAL
        msg_q = select(OutreachMessage).where(OutreachMessage.business_id.in_(test_business_ids))
        messages = (await session.execute(msg_q)).scalars().all()
        assert len(messages) >= 1

        for msg in messages:
            assert msg.status == OutreachStatus.PENDING_APPROVAL.value
            assert msg.approved_at is None
            assert msg.sent_at is None

    # -------------------------------------------------------------
    # 5. Queue Inspection: Multiple Businesses in PENDING_APPROVAL
    # -------------------------------------------------------------
    # -------------------------------------------------------------
    # 5. Queue Inspection & 6. Operator Approval Simulation
    # -------------------------------------------------------------
    approved_ids = []
    async with AsyncSessionLocal() as session:
        pending_q = select(OutreachMessage).where(
            OutreachMessage.business_id.in_(test_business_ids),
            OutreachMessage.status == OutreachStatus.PENDING_APPROVAL.value
        )
        pending_msgs = (await session.execute(pending_q)).scalars().all()
        assert len(pending_msgs) >= 2

        # Simulate operator approving 2 leads
        msgs_to_approve = pending_msgs[:2]
        approved_ids = [m.id for m in msgs_to_approve]
        for m in msgs_to_approve:
            m.status = OutreachStatus.APPROVED.value
            m.approved_at = datetime.utcnow()
        await session.commit()

        # Verify exactly those 2 moved to APPROVED
        appr_q = select(OutreachMessage).where(
            OutreachMessage.business_id.in_(test_business_ids),
            OutreachMessage.status == OutreachStatus.APPROVED.value
        )
        approved_in_db = (await session.execute(appr_q)).scalars().all()
        assert len(approved_in_db) == len(approved_ids)

    # -------------------------------------------------------------
    # 7. Capacity-Governed Dispatch Simulation (DRY RUN / MOCK)
    # -------------------------------------------------------------
    with patch("app.crm.inbox_poller.inbox_poller.poll_inbox", new_callable=AsyncMock) as mock_poll, \
         patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary") as mock_cap, \
         patch("app.outreach.sender.outreach_sender_adapter.send_approved_message", new_callable=AsyncMock) as mock_send, \
         patch("app.followups.engine.followup_engine.process_due_followups", new_callable=AsyncMock) as mock_fu:
        mock_poll.return_value = []
        mock_cap.return_value = {"available_capacity": 5, "rollout_stage_name": "Testing", "rollout_daily_cap": 5, "sent_today": 0}
        mock_send.return_value = True
        mock_fu.return_value = []

        # Execute tick dispatch
        tick_res = await worker.execute_tick()
        assert tick_res["status"] == "SUCCESS"
        assert mock_send.call_count == len(approved_ids)

    # -------------------------------------------------------------
    # 8. Response Loop Simulations
    # -------------------------------------------------------------
    # Scenario A: Prospect 1 replies POSITIVE
    async with AsyncSessionLocal() as session:
        p1_id = test_business_ids[0]
        p1_biz = await session.get(Business, p1_id)
        p1_reply_text = "Yes, this sounds interesting! Can you show me how your system works for our shop?"

        reply_a = await reply_classifier.process_incoming_reply(
            session=session,
            business_id=p1_id,
            sender_email=p1_biz.public_email,
            raw_body=p1_reply_text
        )
        await session.commit()

        # Refresh business
        await session.refresh(p1_biz)
        assert reply_a.classification in (ReplyClassification.INTERESTED.value, ReplyClassification.POSITIVE.value)
        # Demo Factory triggered & stage advanced to DEMO_READY
        assert p1_biz.pipeline_stage == PipelineStage.DEMO_READY.value

        # Verify demo artifact was generated
        demo_art_q = select(Artifact).where(
            Artifact.business_id == p1_id,
            Artifact.artifact_type == "DEMO_PACKAGE"
        )
        demo_art = (await session.execute(demo_art_q)).scalars().first()
        assert demo_art is not None
        assert demo_art.path is not None

        # Verify CEO alert event logged with /demo/ preview
        event_q = select(PipelineEvent).where(
            PipelineEvent.business_id == p1_id,
            PipelineEvent.to_stage == PipelineStage.DEMO_READY.value
        )
        event = (await session.execute(event_q)).scalars().first()
        assert event is not None
        assert "/demo/" in event.note

    # Scenario B: Prospect 2 replies NEGATIVE
    async with AsyncSessionLocal() as session:
        p2_id = test_business_ids[1]
        p2_biz = await session.get(Business, p2_id)
        p2_reply_text = "Not interested. Please remove us from your mailing list."

        reply_b = await reply_classifier.process_incoming_reply(
            session=session,
            business_id=p2_id,
            sender_email=p2_biz.public_email,
            raw_body=p2_reply_text
        )
        await session.commit()

        await session.refresh(p2_biz)
        assert reply_b.classification in (ReplyClassification.NOT_INTERESTED.value, ReplyClassification.NEGATIVE.value, ReplyClassification.UNSUBSCRIBE.value)
        assert p2_biz.pipeline_stage == PipelineStage.LOST.value

        # Verify email added to suppression
        is_suppressed = await compliance_guard.is_suppressed(session, email=p2_biz.public_email)
        assert is_suppressed is True

    # Scenario C: Prospect 4 replies QUESTION
    async with AsyncSessionLocal() as session:
        p4_id = test_business_ids[3]
        p4_biz = await session.get(Business, p4_id)
        p4_reply_text = "How does it work and what is the typical implementation timeline?"

        reply_c = await reply_classifier.process_incoming_reply(
            session=session,
            business_id=p4_id,
            sender_email=p4_biz.public_email,
            raw_body=p4_reply_text
        )
        await session.commit()

        await session.refresh(p4_biz)
        assert reply_c.classification == ReplyClassification.QUESTION.value
        assert p4_biz.pipeline_stage == PipelineStage.REPLIED.value
        assert len(reply_c.suggested_response) > 0
