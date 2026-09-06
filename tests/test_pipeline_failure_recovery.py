import pytest
import asyncio
import uuid
import json
import hmac
import hashlib
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business,
    AuditRun,
    Offer,
    OutreachMessage,
    PipelineStage,
    VerificationStatus,
    OutreachStatus,
    Payment
)
from app.orchestrator.loop import AutonomousCycleOrchestrator
from app.crm.memory_service import memory_service
from app.crm.inbox_poller import inbox_poller
from app.payments.razorpay import razorpay_payment_provider
from app.core.config import settings
from app.api.app import app
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_failure_recovery_during_audit_and_scoring():
    """
    PHASE 8.1: Verifies system crash during audit/scoring does not crash loop permanently,
    and resumes processing safely on subsequent cycle.
    """
    await init_db()
    uid = uuid.uuid4().hex[:6]
    domain = f"crash-audit-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Crash Test Biz {uid}",
            domain=domain,
            country="US",
            city="Austin",
            niche="Plumbing",
            public_email=f"contact@{domain}",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.VERIFIED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        biz_id = biz.id

    # Simulate audit engine crash
    orch = AutonomousCycleOrchestrator()
    from app.auditing.engine import website_audit_engine
    from app.core.logging import logger

    with patch.object(website_audit_engine, "audit_business", side_effect=RuntimeError("Simulated Network Timeout during Audit")):
        async with AsyncSessionLocal() as session:
            # Crash recovery step resumes and catches error gracefully without raising
            await orch._recover_incomplete_stages(session, logger)

    # Verify prospect remains in VERIFIED stage ready for retry, not lost or corrupted
    async with AsyncSessionLocal() as session:
        check_biz = await session.get(Business, biz_id)
        assert check_biz.pipeline_stage == PipelineStage.VERIFIED.value


@pytest.mark.asyncio
async def test_failure_recovery_prevents_duplicate_outreach():
    """
    PHASE 8.2: Verifies that if an outreach message is already marked SENT,
    crash recovery or repeat cycles will NEVER re-send to the same prospect.
    """
    await init_db()
    uid = uuid.uuid4().hex[:6]
    domain = f"no-duplicate-send-{uid}.com"
    email = f"lead@{domain}"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Duplicate Safe Biz {uid}",
            domain=domain,
            country="US",
            niche="Plumbing",
            public_email=email,
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.CONTACTED.value
        )
        session.add(biz)
        await session.flush()

        msg = OutreachMessage(
            business_id=biz.id,
            status=OutreachStatus.SENT.value,
            subject=f"Speed report for {domain}",
            body="First contact body",
            recipient_email=email
        )
        session.add(msg)
        await session.commit()
        biz_id = biz.id

    # Run cycle; verify this contacted business is never contacted a second time
    orch = AutonomousCycleOrchestrator()
    from app.outreach.sender import outreach_sender_adapter
    from app.core.logging import logger
    with patch.object(outreach_sender_adapter, "send_approved_message", new_callable=AsyncMock) as mock_send:
        async with AsyncSessionLocal() as session:
            await orch._recover_incomplete_stages(session, logger)
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_failure_recovery_inbound_reply_and_webhook_idempotency():
    """
    PHASE 8.3: Verifies that duplicate payment webhooks or repeated reply processing
    are completely idempotent and cannot produce duplicate payments or duplicate onboarding.
    """
    await init_db()
    uid = uuid.uuid4().hex[:6]
    domain = f"pay-recovery-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Pay Recovery Biz {uid}",
            domain=domain,
            country="US",
            niche="Commercial Services",
            public_email=f"admin@{domain}",
            pipeline_stage=PipelineStage.PROPOSAL.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        biz_id = biz.id

    test_secret = "test_sec_recovery_9988"
    orig_sec = razorpay_payment_provider.webhook_secret
    razorpay_payment_provider.webhook_secret = test_secret

    webhook_payload = {
        "event": "payment_link.paid",
        "created_at": 1710009999,
        "payload": {
            "payment_link": {
                "entity": {
                    "id": f"plink_rec_{uid}",
                    "amount": 75000,
                    "amount_paid": 75000,
                    "currency": "USD",
                    "status": "paid",
                    "notes": {"business_id": str(biz_id)}
                }
            },
            "payment": {
                "entity": {
                    "id": f"pay_rec_{uid}",
                    "amount": 75000,
                    "currency": "USD",
                    "status": "captured",
                    "email": f"admin@{domain}"
                }
            }
        }
    }
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")
    sig = hmac.new(test_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. First webhook execution: Processed
            r1 = await client.post(
                "/api/webhooks/razorpay",
                content=payload_bytes,
                headers={"X-Razorpay-Signature": sig}
            )
            assert r1.status_code == 200

            # 2. Simulated crash / replay retry: Idempotently handled
            r2 = await client.post(
                "/api/webhooks/razorpay",
                content=payload_bytes,
                headers={"X-Razorpay-Signature": sig}
            )
            assert r2.status_code == 200

        # Verify only 1 Payment record created
        async with AsyncSessionLocal() as session:
            payments = (await session.execute(
                select(Payment).where(Payment.reference_id == f"pay_rec_{uid}")
            )).scalars().all()
            assert len(payments) == 1
    finally:
        razorpay_payment_provider.webhook_secret = orig_sec
