import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.outreach.providers.dry_run import DryRunEmailProvider
from app.outreach.providers.factory import get_email_provider
from app.outreach.providers.resend_provider import ResendEmailProvider
from app.outreach.providers.sendgrid_provider import SendGridEmailProvider
from app.outreach.sender import outreach_sender_adapter
from app.database.models import Business, OutreachMessage, OutreachStatus, PipelineStage
from app.outreach.compliance import compliance_guard
from app.core.config import settings

@pytest.mark.asyncio
async def test_dry_run_provider():
    provider = DryRunEmailProvider()
    res = await provider.send_email(
        to_email="test@commercialroofing.com",
        subject="Audit Findings for Your Commercial Site",
        body="Hello, we identified several high-impact Core Web Vitals issues.",
        from_email="prospects@agencygrowth.co",
        from_name="Elena Vance"
    )
    assert res["status"] == "SUCCESS"
    assert res["provider"] == "dry_run"
    assert "dry_run_" in res["message_id"]
    assert res["details"]["dry_run"] is True
    assert res["details"]["to"] == "test@commercialroofing.com"

@pytest.mark.asyncio
async def test_email_provider_factory_safety_default():
    # By default, EMAIL_DRY_RUN=True so factory MUST return DryRunEmailProvider
    provider = get_email_provider()
    assert isinstance(provider, DryRunEmailProvider)

@pytest.mark.asyncio
async def test_resend_provider_payload():
    provider = ResendEmailProvider(api_key="re_test_dummy_key_123")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "resend_msg_abc123"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        res = await provider.send_email(
            to_email="director@company.com",
            subject="SEO Review",
            body="Reviewing your site..."
        )
        assert res["status"] == "SUCCESS"
        assert res["provider"] == "resend"
        assert res["message_id"] == "resend_msg_abc123"

@pytest.mark.asyncio
async def test_sendgrid_provider_payload():
    provider = SendGridEmailProvider(api_key="SG.dummy_key_456")
    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_resp.headers = {"X-Message-Id": "sg_msg_789"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        res = await provider.send_email(
            to_email="owner@service.com",
            subject="Technical Assessment",
            body="Your website performance score..."
        )
        assert res["status"] == "SUCCESS"
        assert res["provider"] == "sendgrid"
        assert res["message_id"] == "sg_msg_789"

@pytest.mark.asyncio
async def test_mandatory_human_approval_enforcement(db_session):
    """
    INVARIANT TEST: An outreach message cannot be sent without human approval (status == APPROVED).
    Attempting to send a PENDING_APPROVAL or REJECTED message must raise ValueError.
    """
    biz = Business(
        name="Apex Industrial Roofing",
        domain="apexroofing.com",
        website_url="https://apexroofing.com",
        country="US",
        niche="commercial_roofing",
        public_email="info@apexroofing.com"
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="info@apexroofing.com",
        subject="Audit findings",
        body="Here are findings...",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    # Attempt to send directly without approval
    with pytest.raises(ValueError, match="must be APPROVED"):
        await outreach_sender_adapter.send_approved_message(db_session, msg.id)

    # Approve the message
    msg.status = OutreachStatus.APPROVED.value
    await db_session.commit()

    # Now sending should succeed
    res = await outreach_sender_adapter.send_approved_message(db_session, msg.id)
    assert res["status"] in ("SENT", "SUCCESS")
    assert msg.status == OutreachStatus.SENT.value

@pytest.mark.asyncio
async def test_suppression_list_blocks_sender(db_session):
    """
    INVARIANT TEST: Suppressed emails must never be sent, even if approved.
    """
    biz = Business(
        name="Suppressed Client Corp",
        domain="suppressedcorp.com",
        website_url="https://suppressedcorp.com",
        country="US",
        niche="commercial_roofing",
        public_email="optout@suppressedcorp.com"
    )
    db_session.add(biz)
    await db_session.flush()

    await compliance_guard.add_to_suppression(db_session, "optout@suppressedcorp.com", reason="TEST_UNSUB")

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="optout@suppressedcorp.com",
        subject="Audit findings",
        body="Here are findings...",
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.commit()

    with pytest.raises(ValueError, match="is on suppression list"):
        await outreach_sender_adapter.send_approved_message(db_session, msg.id)
