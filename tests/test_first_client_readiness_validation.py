import os
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.api.app import app
from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.models import OutreachMessage, OutreachEvent, Business, OutreachStatus
from app.infrastructure.production_activation import ProductionActivationManager
from app.outreach.sender import outreach_sender_adapter


@pytest.mark.asyncio
async def test_email_readiness_checklist_structure():
    checklist = ProductionActivationManager.get_email_readiness_checklist()

    assert "sender_identity" in checklist
    assert "reply_to" in checklist
    assert "spf" in checklist
    assert "dkim" in checklist
    assert "dmarc" in checklist
    assert "postal_address" in checklist
    assert "unsubscribe" in checklist
    assert "suppression" in checklist
    assert "bounce_handling" in checklist
    assert "domain_consistency" in checklist
    assert "inbox_monitoring" in checklist
    assert "overall_status" in checklist
    assert "is_ready" in checklist
    assert "blockers" in checklist
    assert isinstance(checklist["blockers"], list)
    assert checklist["postal_address"]["verified"] is True
    assert checklist["unsubscribe"]["verified"] is True
    assert checklist["suppression"]["verified"] is True
    assert checklist["bounce_handling"]["verified"] is True


@pytest.mark.asyncio
async def test_api_email_readiness_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/email/readiness")
        assert res.status_code == 200
        data = res.json()
        assert "overall_status" in data
        assert "sender_identity" in data
        assert "spf" in data
        assert "dkim" in data
        assert "dmarc" in data


@pytest.mark.asyncio
async def test_queue_message_preview_endpoint():
    uid = uuid.uuid4().hex[:8]
    test_domain = f"solar-{uid}.com"
    test_email = f"contact@{test_domain}"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Solar Pros {uid}",
            domain=test_domain,
            public_email=test_email,
            niche="Solar Installation",
            country="US",
            pipeline_stage="QUALIFIED"
        )
        session.add(biz)
        await session.flush()

        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=test_email,
            subject=f"Quick question regarding {test_domain} performance",
            body="Hello team, noticed 2.4s latency on mobile. We built a live test demo.",
            status="QUEUED"
        )
        session.add(msg)
        await session.commit()
        msg_id = msg.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/queue/{msg_id}/preview")
        assert res.status_code == 200
        data = res.json()
        assert data["message_id"] == msg_id
        assert data["recipient_email"] == test_email
        assert data["subject"] == f"Quick question regarding {test_domain} performance"
        assert "compliance_footer" in data
        assert "unsubscribe" in data["compliance_footer"].lower()
        assert "full_content" in data
        assert "email_readiness" in data


@pytest.mark.asyncio
async def test_hard_one_real_email_limit_enforcement():
    uid = uuid.uuid4().hex[:8]
    test_domain = f"roofing-{uid}.com"
    test_email = f"owner@{test_domain}"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Roofing Co {uid}",
            domain=test_domain,
            public_email=test_email,
            niche="Roofing",
            country="US",
            pipeline_stage="APPROVAL"
        )
        session.add(biz)
        await session.flush()

        msg1 = OutreachMessage(
            business_id=biz.id,
            recipient_email=f"first-{uid}@example.com",
            subject="Intro",
            body="Hi",
            status=OutreachStatus.SENT.value
        )
        session.add(msg1)
        await session.flush()

        prior_event = OutreachEvent(
            outreach_message_id=msg1.id,
            event_type="email_dispatched",
            details={
                "recipient": f"first-{uid}@example.com",
                "delivery_status": "DELIVERED",
                "dry_run": False
            }
        )
        session.add(prior_event)

        msg2 = OutreachMessage(
            business_id=biz.id,
            recipient_email=test_email,
            subject="Performance audit findings",
            body="Hi, here is the audit.",
            status=OutreachStatus.APPROVED.value
        )
        session.add(msg2)
        await session.commit()
        msg2_id = msg2.id

        orig_resend = settings.RESEND_API_KEY
        settings.RESEND_API_KEY = "re_test_mock_dummy_key"
        try:
            with pytest.raises(ValueError) as excinfo:
                async with AsyncSessionLocal() as session:
                    await outreach_sender_adapter.send_approved_message(session, msg2_id, force_live=True)

            assert "First-client validation limit reached" in str(excinfo.value)
            assert "Exactly 1 real outbound email is permitted" in str(excinfo.value)
        finally:
            settings.RESEND_API_KEY = orig_resend


@pytest.mark.asyncio
async def test_dry_run_vs_real_status_in_ceo_overview():
    uid = uuid.uuid4().hex[:8]
    test_domain = f"hvac-{uid}.com"
    test_email = f"service@{test_domain}"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"HVAC Solutions {uid}",
            domain=test_domain,
            public_email=test_email,
            niche="HVAC",
            country="US",
            pipeline_stage="CONTACTED"
        )
        session.add(biz)
        await session.flush()

        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=test_email,
            subject="Performance check",
            body="Hi there",
            status=OutreachStatus.SENT.value
        )
        session.add(msg)
        await session.flush()

        event = OutreachEvent(
            outreach_message_id=msg.id,
            event_type="dry_run_simulated",
            details={"recipient": test_email, "dry_run": True, "simulated": True}
        )
        session.add(event)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ceo/overview")
        assert res.status_code == 200
        data = res.json()
        assert "system_status" in data
        assert "email_readiness" in data["system_status"]
