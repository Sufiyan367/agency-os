import pytest
from sqlalchemy import select
from app.database.models import Business, OutreachStatus, PipelineStage, FollowupSequence
from app.auditing.engine import website_audit_engine
from app.scoring.engine import lead_scoring_engine
from app.offers.generator import offer_engine
from app.outreach.personalization import outreach_personalizer
from app.outreach.queue import outreach_approval_queue
from app.outreach.sender import outreach_sender_adapter
from app.outreach.compliance import compliance_guard

@pytest.mark.asyncio
async def test_outreach_queue_and_approval_gate(db_session):
    biz = Business(
        name="Reliable Roofing Co",
        domain="reliableroofingtest.com",
        website_url="https://reliableroofingtest.com",
        country="US",
        niche="roofing-contractors",
        public_email="service@reliableroofingtest.com"
    )
    db_session.add(biz)
    await db_session.commit()

    await website_audit_engine.audit_business(db_session, biz)
    await lead_scoring_engine.score_business(db_session, biz)
    await offer_engine.generate_offer_for_business(db_session, biz)

    # 1. Draft message
    msg = await outreach_personalizer.prepare_outreach_for_business(db_session, biz)
    assert msg.status == OutreachStatus.PENDING_APPROVAL.value
    assert "reliableroofingtest.com" in msg.body
    assert "unsubscribe" in msg.body.lower()

    # 2. Verify Unapproved message cannot be sent!
    with pytest.raises(ValueError, match="must be APPROVED"):
        await outreach_sender_adapter.send_approved_message(db_session, msg.id)

    # 3. Approve message
    appr = await outreach_approval_queue.approve_message(db_session, msg.id)
    assert appr.status == OutreachStatus.APPROVED.value

    # 4. Send message (DRY_RUN simulation)
    send_res = await outreach_sender_adapter.send_approved_message(db_session, msg.id)
    assert send_res["status"] == "SUCCESS"
    assert appr.status == OutreachStatus.SENT.value
    assert biz.pipeline_stage == PipelineStage.CONTACTED.value

    # 5. Check Follow-ups were scheduled via explicit query
    fu_q = select(FollowupSequence).where(FollowupSequence.initial_message_id == msg.id)
    followups = (await db_session.execute(fu_q)).scalars().all()
    assert len(followups) == 3

@pytest.mark.asyncio
async def test_compliance_suppression_prevents_outreach(db_session):
    await compliance_guard.add_to_suppression(db_session, "blocked@spammer.com", reason="UNSUBSCRIBE")
    is_supp = await compliance_guard.is_suppressed(db_session, "blocked@spammer.com")
    assert is_supp is True
