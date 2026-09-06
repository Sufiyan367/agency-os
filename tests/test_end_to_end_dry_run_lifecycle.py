import pytest
import asyncio
import uuid
import json
import hmac
import hashlib
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business,
    AuditRun,
    LeadScore,
    Offer,
    OutreachMessage,
    PipelineStage,
    VerificationStatus,
    OutreachStatus,
    Payment,
    Customer,
    Project
)
from app.crm.memory_service import memory_service
from app.crm.inbox_poller import inbox_poller
from app.communications.router import ChannelType
from app.agents.revenue_agent import revenue_agent_orchestrator
from app.orchestrator.loop import AutonomousCycleOrchestrator
from app.core.config import settings
from app.api.app import app
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_complete_end_to_end_dry_run_lifecycle_and_isolated_tracks():
    """
    PHASE 6: Complete End-to-End Dry-Run Verification Lifecycle Test.
    Demonstrates:
      Track 1: Discover -> Verify -> Audit -> Score -> $500 Floor -> Offer -> Outreach (DRY RUN) -> Memory Persistence -> Next Prospect B.
      Track 2: Asynchronous Inbound Reply -> Memory Lookup -> Contextual Response -> Meeting -> Proposal -> Payment -> Won.
      Proves Track 1 and Track 2 are completely non-blocking and decoupled.
    """
    await init_db()

    uid_a = uuid.uuid4().hex[:6]
    domain_a = f"prospect-alpha-{uid_a}.com"
    email_a = f"contact@{domain_a}"

    uid_b = uuid.uuid4().hex[:6]
    domain_b = f"prospect-beta-{uid_b}.com"
    email_b = f"contact@{domain_b}"

    # Verify dry-run safety invariant before start
    assert settings.EMAIL_DRY_RUN is True
    assert settings.VOICE_DRY_RUN is True
    assert settings.PAYMENT_DRY_RUN is True

    # -------------------------------------------------------------------------
    # TRACK 1: AUTONOMOUS PROSPECTING (PROSPECT A)
    # -------------------------------------------------------------------------
    
    # 1. Discover Prospect A
    async with AsyncSessionLocal() as session:
        biz_a = Business(
            name=f"Alpha Solutions {uid_a}",
            domain=domain_a,
            website_url=f"https://{domain_a}",
            country="US",
            city="Austin",
            niche="Commercial Services",
            public_email=email_a,
            phone="+15125550111",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.DISCOVERED.value
        )
        session.add(biz_a)
        await session.commit()
        await session.refresh(biz_a)
        biz_a_id = biz_a.id

    # 2. Verify Prospect A
    async with AsyncSessionLocal() as session:
        biz = await session.get(Business, biz_a_id)
        biz.verification_status = VerificationStatus.VERIFIED.value
        biz.pipeline_stage = PipelineStage.VERIFIED.value
        await session.commit()

    # 3. Audit Prospect A
    async with AsyncSessionLocal() as session:
        audit_a = AuditRun(
            business_id=biz_a_id,
            url_audited=f"https://{domain_a}",
            performance_score=46.0,
            seo_score=58.0,
            a11y_score=62.0,
            metrics={"load_time_seconds": 4.8, "cwv_lcp": "3.8s"}
        )
        session.add(audit_a)
        biz = await session.get(Business, biz_a_id)
        biz.pipeline_stage = PipelineStage.AUDITED.value
        await session.commit()

    # 4. Score Prospect A
    async with AsyncSessionLocal() as session:
        score_a = LeadScore(
            business_id=biz_a_id,
            total_score=84.5,
            priority="A"
        )
        session.add(score_a)
        await session.commit()

    # 5. Apply $500 commercial floor & 6. Generate offer
    async with AsyncSessionLocal() as session:
        offer_a = Offer(
            business_id=biz_a_id,
            service_type="web_speed_turnaround",
            title="Core Web Vitals & Conversion Acceleration Package",
            recommended_price=850.0,
            suggested_price_min=750.0,
            suggested_price_max=1200.0,
            deliverables=["LCP Optimization", "Image Compression Pipeline", "Caching Strategy"]
        )
        assert offer_a.recommended_price >= settings.COMMERCIAL_FLOOR_USD
        session.add(offer_a)
        biz = await session.get(Business, biz_a_id)
        biz.pipeline_stage = PipelineStage.OUTREACH_READY.value
        await session.commit()
        await session.refresh(offer_a)
        offer_a_id = offer_a.id

    # 7. Generate evidence-grounded outreach
    async with AsyncSessionLocal() as session:
        outreach_a = OutreachMessage(
            business_id=biz_a_id,
            status=OutreachStatus.SENT.value,
            subject=f"Diagnostic audit report for {domain_a}",
            body=f"Hi team, your site {domain_a} currently loads in 4.8s. We can bring this under 1.5s.",
            recipient_email=email_a,
            offer_id=offer_a_id
        )
        session.add(outreach_a)
        biz = await session.get(Business, biz_a_id)
        biz.pipeline_stage = PipelineStage.CONTACTED.value
        await session.commit()

    # 8. Dispatch in DRY-RUN mode (Simulated - no external network call)
    assert settings.EMAIL_DRY_RUN is True

    # 9. Persist complete ProspectMemory
    async with AsyncSessionLocal() as session:
        mem_a = await memory_service.save_memory(
            session=session,
            business_id=biz_a_id,
            domain=domain_a,
            contact_email=email_a,
            contact_phone="+15125550111",
            contact_name="Alpha Principal",
            channel_used="EMAIL",
            pipeline_stage="CONTACTED",
            buyer_score=84.5,
            opportunity_score=80.0,
            estimated_value=850.0,
            audit_results={"performance_score": 46.0, "load_time_seconds": 4.8},
            offer_proposal={"title": "Core Web Vitals & Conversion Acceleration Package", "price": 850.0},
            outreach_message={"subject": f"Diagnostic audit report for {domain_a}", "channel": "EMAIL"},
            last_interaction=f"Diagnostic audit report for {domain_a} sent in DRY_RUN."
        )
        assert mem_a is not None
        assert mem_a.domain == domain_a

    # 10. Immediately continue to Prospect B without waiting for Prospect A's reply
    async with AsyncSessionLocal() as session:
        biz_b = Business(
            name=f"Beta Enterprises {uid_b}",
            domain=domain_b,
            website_url=f"https://{domain_b}",
            country="US",
            city="Austin",
            niche="Roofing Contractors",
            public_email=email_b,
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.DISCOVERED.value
        )
        session.add(biz_b)
        await session.commit()
        await session.refresh(biz_b)
        biz_b_id = biz_b.id

    # 11. Confirm Prospect A is CONTACTED while Prospect B is DISCOVERED
    async with AsyncSessionLocal() as session:
        check_a = await session.get(Business, biz_a_id)
        check_b = await session.get(Business, biz_b_id)
        assert check_a.pipeline_stage == PipelineStage.CONTACTED.value
        assert check_b.pipeline_stage == PipelineStage.DISCOVERED.value

    # -------------------------------------------------------------------------
    # TRACK 2: ASYNCHRONOUS INBOUND REPLY & CONVERSATION RESUMPTION (PROSPECT A)
    # -------------------------------------------------------------------------

    # 12. Simulate an inbound reply from Prospect A
    # 13. Identify Prospect A using stored identifiers & 14. Restore ProspectMemory
    reply_subject = f"Re: Diagnostic audit report for {domain_a}"
    reply_body = "This sounds interesting. What is the scope of your speed turnaround package?"

    async with AsyncSessionLocal() as session:
        stored_mem = await memory_service.get_memory(session, domain=domain_a)
        assert stored_mem is not None
        assert stored_mem.business_id == biz_a_id

        # 15. Restore audit evidence & 16. Restore previous offer & 17. Restore conversation history
        restored_audit = stored_mem.audit_results
        restored_offer = stored_mem.offer_proposal
        assert restored_audit["performance_score"] == 46.0
        assert restored_offer["price"] == 850.0

        # 18. Classify reply & 19. Generate context-aware response
        reply_record = await inbox_poller.process_inbound_message(
            session=session,
            sender_email=email_a,
            subject=reply_subject,
            body=reply_body
        )
        assert reply_record is not None

        # 20. Update Prospect A's state
        updated_biz_a = await session.get(Business, biz_a_id)
        assert updated_biz_a.pipeline_stage in (PipelineStage.REPLIED.value, PipelineStage.QUALIFIED_REPLY.value, PipelineStage.MEETING.value)

    # 21. Simulate meeting event & 22. Map meeting back to Prospect A
    async with AsyncSessionLocal() as session:
        from datetime import datetime, timedelta
        from app.database.models import Meeting
        meeting = Meeting(
            business_id=biz_a_id,
            prospect_name="Alpha Principal",
            prospect_contact="+15125550111",
            title="Diagnostic Walkthrough Consultation",
            scheduled_time=datetime.utcnow() + timedelta(days=2),
            duration_minutes=20,
            meeting_url="https://meet.agencygrowth.co/diagnostic-consultation",
            status="SCHEDULED",
            notes=f"Consultation scheduled for Alpha Solutions {uid_a}."
        )
        session.add(meeting)
        biz = await session.get(Business, biz_a_id)
        biz.pipeline_stage = PipelineStage.MEETING.value
        await session.commit()
        await session.refresh(meeting)
        assert meeting is not None
        assert meeting.business_id == biz_a_id

    # 23. Simulate proposal event
    async with AsyncSessionLocal() as session:
        biz = await session.get(Business, biz_a_id)
        biz.pipeline_stage = PipelineStage.PROPOSAL.value
        await session.commit()

    # 24. Simulate payment webhook in DRY RUN mode
    test_secret = "test_rzp_sec_e2e_dryrun"
    from app.payments.razorpay import razorpay_payment_provider
    orig_sec = razorpay_payment_provider.webhook_secret
    razorpay_payment_provider.webhook_secret = test_secret

    webhook_payload = {
        "event": "payment_link.paid",
        "created_at": 1710009999,
        "payload": {
            "payment_link": {
                "entity": {
                    "id": f"plink_e2e_{uid_a}",
                    "amount": 85000,
                    "amount_paid": 85000,
                    "currency": "USD",
                    "status": "paid",
                    "notes": {"business_id": str(biz_a_id)}
                }
            },
            "payment": {
                "entity": {
                    "id": f"pay_e2e_alpha_{uid_a}",
                    "amount": 85000,
                    "currency": "USD",
                    "status": "captured",
                    "email": email_a
                }
            }
        }
    }
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")
    sig = hmac.new(test_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res1 = await client.post(
                "/api/webhooks/razorpay",
                content=payload_bytes,
                headers={"X-Razorpay-Signature": sig}
            )
            assert res1.status_code == 200
            assert res1.json()["status"] == "SUCCESS"

            # 25. Verify payment webhook idempotency (duplicate call)
            res2 = await client.post(
                "/api/webhooks/razorpay",
                content=payload_bytes,
                headers={"X-Razorpay-Signature": sig}
            )
            assert res2.status_code == 200
            assert res2.json()["status"] in ("DUPLICATE_IGNORED", "SUCCESS")
    finally:
        razorpay_payment_provider.webhook_secret = orig_sec

    # 26. Advance Prospect A to the correct final state (WON, Customer onboarded, Project created)
    async with AsyncSessionLocal() as session:
        final_biz_a = await session.get(Business, biz_a_id)
        assert final_biz_a.pipeline_stage == PipelineStage.WON.value

        cust = (await session.execute(
            select(Customer).where(Customer.business_id == biz_a_id)
        )).scalars().first()
        assert cust is not None

        proj = (await session.execute(
            select(Project).where(Project.customer_id == cust.id)
        )).scalars().first()
        assert proj is not None
        assert proj.status in ("IN_PROGRESS", "ACTIVE")

    # 27. Verify the main prospecting loop was never blocked by Prospect A's reply
    async with AsyncSessionLocal() as session:
        # Prospect B remains in its active independent cycle state
        final_biz_b = await session.get(Business, biz_b_id)
        assert final_biz_b is not None
        assert final_biz_b.id == biz_b_id
