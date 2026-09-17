import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from app.core.config import settings
from app.database.models import ActiveOutreachLock, OutreachMessage, Business, Campaign
from app.acquisition.controller import active_prospect_controller
from app.outreach.providers.factory import get_email_provider
from app.outreach.providers.titan_provider import TitanEmailProvider
from app.outreach.sender import outreach_sender_adapter
from app.infrastructure.domain_validator import domain_validator
from app.infrastructure.production_activation import production_activation
from app.campaigns.sender_registry import sender_registry


@pytest.mark.asyncio
async def test_titan_is_primary_provider():
    """Verify Titan Email is resolved as primary outbound email provider."""
    with patch.object(settings, "EMAIL_DRY_RUN", False), \
         patch.object(settings, "PRIMARY_EMAIL_PROVIDER", "titan"), \
         patch.object(settings, "EMAIL_PROVIDER", "titan"):
        prov = get_email_provider()
        assert isinstance(prov, TitanEmailProvider)
        assert prov.provider_name == "titan"
        assert settings.PRIMARY_EMAIL_PROVIDER == "titan"


@pytest.mark.asyncio
async def test_sender_identity_defaults_to_business_mailbox():
    """Verify canonical sender and reply-to use business mailbox hello@automatedagencyos.tech."""
    assert settings.EMAIL_FROM == "hello@automatedagencyos.tech"
    assert settings.EMAIL_REPLY_TO in (None, "hello@automatedagencyos.tech")
    assert "sufiyansurve333@gmail.com" not in settings.EMAIL_FROM

    with patch.object(settings, "PRIMARY_EMAIL_PROVIDER", "titan"), \
         patch.object(settings, "EMAIL_PROVIDER", "titan"):
        sender_info = sender_registry.resolve_sender()
        assert sender_info["from_email"] == "hello@automatedagencyos.tech"
        assert sender_info["reply_to"] == "hello@automatedagencyos.tech"


@pytest.mark.asyncio
async def test_lock_semantics_idle_after_send(db_session):
    """
    Verify ActiveOutreachLock represents ONLY the short-lived concurrency lock.
    When a message is sent and prospect enters WAITING_FOR_REPLY / SENT stage,
    lock.status MUST be IDLE, never WAITING_FOR_REPLY.
    """
    biz = Business(
        name="Lock Test Business",
        domain="locktest.com",
        country="US",
        niche="legal"
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="prospect@locktest.com",
        subject="Lock Test Subject",
        body="Lock Test Body",
        status="APPROVED"
    )
    db_session.add(msg)
    await db_session.flush()

    mock_send_result = {
        "status": "SENT",
        "provider": "titan",
        "message_id": "test-msg-uuid",
        "sent_at": datetime.utcnow().isoformat()
    }

    lock = await active_prospect_controller.get_or_create_lock(db_session)
    lock.business_id = biz.id
    lock.current_stage = "APPROVED"
    lock.status = "IDLE"
    await db_session.commit()

    with patch("app.acquisition.controller.outreach_sender_adapter.send_approved_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_send_result
        res = await active_prospect_controller.approve_and_send(db_session, business_id=biz.id, message_id=msg.id)

    assert res["status"] == "SENT"
    
    lock = await active_prospect_controller.get_or_create_lock(db_session)
    assert lock.status == "IDLE", f"Expected lock status to be IDLE, got {lock.status}"
    assert lock.status != "WAITING_FOR_REPLY"
    assert lock.locked_at is None


@pytest.mark.asyncio
async def test_waiting_for_reply_non_blocking(db_session):
    """
    Verify that an active prospect in WAITING_FOR_REPLY stage does not block
    system health or lock status.
    """
    biz = Business(
        name="Reply Test Business",
        domain="replytest.com",
        country="US",
        niche="legal"
    )
    db_session.add(biz)
    await db_session.flush()

    lock = await active_prospect_controller.get_or_create_lock(db_session)
    lock.business_id = biz.id
    lock.current_stage = "WAITING_FOR_REPLY"
    lock.status = "IDLE"
    lock.locked_at = None
    await db_session.commit()

    status_data = await active_prospect_controller.get_active_status(db_session)
    assert status_data.status == "IDLE"
    assert status_data.current_stage == "WAITING_FOR_REPLY"
    assert status_data.is_occupied is True
    assert status_data.business_id == biz.id


@pytest.mark.asyncio
async def test_missing_titan_password_blocks_live_send(db_session):
    """
    Verify that if TITAN_SMTP_PASSWORD is missing, live send fails closed
    and raises RuntimeError, rather than fabricating readiness or silently falling back.
    """
    biz = Business(
        name="Block Test Business",
        domain="blocktest.com",
        country="US",
        niche="legal"
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="prospect@test.com",
        subject="Test Subject",
        body="Test Body",
        status="APPROVED"
    )
    db_session.add(msg)
    await db_session.flush()

    with patch.object(settings, "TITAN_SMTP_PASSWORD", None), \
         patch.object(settings, "EMAIL_DRY_RUN", False), \
         patch.object(settings, "RESEARCH_ONLY", False), \
         patch.object(settings, "PRIMARY_EMAIL_PROVIDER", "titan"), \
         patch.object(settings, "EMAIL_PROVIDER", "titan"), \
         patch.object(settings, "FALLBACK_EMAIL_PROVIDER", None):
        
        with pytest.raises((RuntimeError, ValueError), match=r"(TITAN_SMTP_PASSWORD|Titan SMTP credentials)"):
            await outreach_sender_adapter.send_approved_message(db_session, msg.id, force_live=True)


@pytest.mark.asyncio
async def test_dns_validation_for_automatedagencyos():
    """Verify SPF and DKIM resolution for automatedagencyos.tech."""
    res = domain_validator.inspect_domain_dns("automatedagencyos.tech", provider="titan")
    assert res["valid_syntax"] is True
    assert res["spf_present"] is True
    assert "spf.titan.email" in (res.get("spf_record") or "")
    assert res["spf_includes_provider"] is True
    assert "VERIFIED" in res["dkim_status"]
    assert res["dmarc_present"] in (True, False)


@pytest.mark.asyncio
async def test_deliverability_readiness_checklist_reports_blocked_without_password():
    """Verify email readiness checklist reports BLOCKED when Titan SMTP password is not set."""
    with patch.object(settings, "TITAN_SMTP_PASSWORD", None), \
         patch.object(settings, "SMTP_PASSWORD", None), \
         patch.object(settings, "EMAIL_PROVIDER", "titan"):
        
        checklist = production_activation.get_email_readiness_checklist()
        assert checklist["overall_status"] == "BLOCKED"
        assert any("Titan SMTP password is missing" in b for b in checklist["blockers"])
