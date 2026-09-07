import base64
import pytest
from unittest.mock import patch, MagicMock
from app.outreach.providers.gmail_oauth_provider import (
    GmailOAuthEmailProvider, _sanitize_error, GMAIL_SCOPES, GMAIL_SEND_SCOPE, GMAIL_READONLY_SCOPE
)
from app.outreach.providers.factory import get_email_provider
from app.outreach.providers.dry_run import DryRunEmailProvider
from app.database.models import Business, OutreachMessage, OutreachEvent, OutreachStatus, PipelineStage
from app.crm.inbox_poller import inbox_poller
from app.core.config import settings


# 1. OAuth Configuration Test
def test_oauth_configuration_fields():
    assert hasattr(settings, "GMAIL_CLIENT_ID")
    assert hasattr(settings, "GMAIL_CLIENT_SECRET")
    assert hasattr(settings, "GMAIL_REFRESH_TOKEN")
    assert hasattr(settings, "GMAIL_SENDER_EMAIL")
    assert GMAIL_SEND_SCOPE in GMAIL_SCOPES
    assert GMAIL_READONLY_SCOPE in GMAIL_SCOPES
    assert len(GMAIL_SCOPES) == 2  # strictly least-privilege


# 2. Provider Factory Routing Test
def test_provider_factory_routing():
    # Safety invariant: when EMAIL_DRY_RUN=True, factory ALWAYS returns DryRunEmailProvider
    with patch.object(settings, "EMAIL_DRY_RUN", True):
        with patch.object(settings, "EMAIL_PROVIDER", "gmail"):
            provider = get_email_provider()
            assert isinstance(provider, DryRunEmailProvider)

    # When EMAIL_DRY_RUN=False and provider="gmail", returns GmailOAuthEmailProvider
    with patch.object(settings, "EMAIL_DRY_RUN", False):
        with patch.object(settings, "EMAIL_PROVIDER", "gmail"):
            provider = get_email_provider()
            assert isinstance(provider, GmailOAuthEmailProvider)

    # When EMAIL_DRY_RUN=False and provider="gmail_oauth", returns GmailOAuthEmailProvider
    with patch.object(settings, "EMAIL_DRY_RUN", False):
        with patch.object(settings, "EMAIL_PROVIDER", "gmail_oauth"):
            provider = get_email_provider()
            assert isinstance(provider, GmailOAuthEmailProvider)


# 3. Dry-Run Send Test (Safety Invariant)
@pytest.mark.asyncio
async def test_dry_run_safety():
    with patch.object(settings, "EMAIL_DRY_RUN", True):
        with patch.object(settings, "EMAIL_PROVIDER", "gmail"):
            provider = get_email_provider()
            res = await provider.send_email(
                to_email="prospect@example.com",
                subject="Test Subject",
                body="Test Body"
            )
            assert res["status"] == "SUCCESS"
            assert res["provider"] == "dry_run"
            assert res["details"]["dry_run"] is True


# 4. MIME Generation Test
def test_mime_generation():
    provider = GmailOAuthEmailProvider(
        client_id="test-client-id",
        client_secret="test-secret",
        refresh_token="test-refresh",
        sender_email="owner@gmail.com"
    )

    mime_info = provider.build_mime_message(
        to_email="prospect@targetdomain.com",
        subject="Audit Observations",
        body="Plain text audit body.",
        html_body="<p>Plain text audit body.</p>",
        from_name="Business Owner",
        from_email="owner@gmail.com"
    )

    payload = mime_info["payload"]
    assert "raw" in payload
    # Decode base64url and check headers
    decoded = base64.urlsafe_b64decode(payload["raw"]).decode("utf-8")
    assert "To: prospect@targetdomain.com" in decoded
    assert "Subject: Audit Observations" in decoded
    assert "From: Business Owner <owner@gmail.com>" in decoded
    assert "Message-ID:" in decoded


# 5. Thread ID & Headers Handling Test
def test_thread_id_and_headers_handling():
    provider = GmailOAuthEmailProvider(
        client_id="test-id",
        client_secret="test-sec",
        refresh_token="test-ref",
        sender_email="owner@gmail.com"
    )

    mime_info = provider.build_mime_message(
        to_email="prospect@targetdomain.com",
        subject="Re: Audit Observations",
        body="Following up on my note.",
        thread_id="thread_xyz_987",
        in_reply_to="<orig_msg_123@gmail.com>",
        references="<orig_msg_123@gmail.com>"
    )

    payload = mime_info["payload"]
    assert payload["threadId"] == "thread_xyz_987"
    decoded = base64.urlsafe_b64decode(payload["raw"]).decode("utf-8")
    assert "In-Reply-To: <orig_msg_123@gmail.com>" in decoded
    assert "References: <orig_msg_123@gmail.com>" in decoded


# 6. Reply Parsing from Gmail API Message
def test_reply_parsing():
    raw_body_text = "Thanks for reaching out! We would like to see the audit details."
    encoded_body = base64.urlsafe_b64encode(raw_body_text.encode("utf-8")).decode("utf-8")

    sample_gmail_msg = {
        "id": "msg_abc_456",
        "threadId": "thread_xyz_987",
        "snippet": raw_body_text,
        "payload": {
            "headers": [
                {"name": "From", "value": "Director <director@targetdomain.com>"},
                {"name": "Subject", "value": "Re: Audit Observations"},
                {"name": "Message-ID", "value": "<reply_msg_789@targetdomain.com>"},
                {"name": "In-Reply-To", "value": "<orig_msg_123@gmail.com>"},
                {"name": "Date", "value": "Sun, 06 Sep 2026 15:00:00 -0700"}
            ],
            "mimeType": "text/plain",
            "body": {
                "data": encoded_body
            }
        }
    }

    parsed = GmailOAuthEmailProvider.parse_gmail_message(sample_gmail_msg)
    assert parsed["id"] == "msg_abc_456"
    assert parsed["threadId"] == "thread_xyz_987"
    assert parsed["sender_email"] == "director@targetdomain.com"
    assert parsed["subject"] == "Re: Audit Observations"
    assert parsed["in_reply_to"] == "<orig_msg_123@gmail.com>"
    assert parsed["body"] == raw_body_text


# 7. Identity Verification and Mismatch Test
def test_identity_verification_and_mismatch():
    provider = GmailOAuthEmailProvider(
        client_id="test-id",
        client_secret="test-sec",
        refresh_token="test-ref",
        sender_email="owner@gmail.com"
    )

    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {
        "emailAddress": "owner@gmail.com",
        "messagesTotal": 120,
        "threadsTotal": 45
    }

    with patch.object(provider, "get_service", return_value=mock_service):
        health = provider.check_auth_health()
        assert health["status"] == "OK"
        assert health["healthy"] is True
        assert health["authenticated_email"] == "owner@gmail.com"

    # Now test mismatch
    provider_mismatch = GmailOAuthEmailProvider(
        client_id="test-id",
        client_secret="test-sec",
        refresh_token="test-ref",
        sender_email="different_person@gmail.com"
    )
    with patch.object(provider_mismatch, "get_service", return_value=mock_service):
        health_mismatch = provider_mismatch.check_auth_health()
        assert health_mismatch["status"] == "ERROR"
        assert health_mismatch["healthy"] is False
        assert "identity mismatch" in health_mismatch["error"].lower()


# 8. Missing Credentials Fails Closed Test
def test_missing_credentials_fails_closed():
    # Empty provider with explicit empty strings
    provider = GmailOAuthEmailProvider(
        client_id="",
        client_secret="",
        refresh_token=""
    )

    health = provider.check_auth_health()
    assert health["status"] == "ERROR"
    assert health["healthy"] is False

    with pytest.raises(ValueError, match="GMAIL_CLIENT_ID is missing"):
        provider._get_credentials()

    # Also test when settings are unconfigured
    with patch.object(settings, "GMAIL_CLIENT_ID", None):
        with patch.object(settings, "GMAIL_CLIENT_SECRET", None):
            with patch.object(settings, "GMAIL_REFRESH_TOKEN", None):
                p_unconfigured = GmailOAuthEmailProvider()
                h = p_unconfigured.check_auth_health()
                assert h["status"] == "ERROR"
                assert h["healthy"] is False


# 9. Secret Redaction Test
def test_secret_redaction():
    secret_token = "1//04secret_refresh_token_very_long_string"
    secret_client = "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yz"

    with patch.object(settings, "GMAIL_REFRESH_TOKEN", secret_token):
        with patch.object(settings, "GMAIL_CLIENT_SECRET", secret_client):
            error = Exception(f"Failed connecting with refresh_token {secret_token} and secret {secret_client}")
            sanitized = _sanitize_error(error)
            assert secret_token not in sanitized
            assert secret_client not in sanitized
            assert "[REDACTED]" in sanitized


# 10. Live Send Execution (Mocked) Test
@pytest.mark.asyncio
async def test_live_send_mocked():
    provider = GmailOAuthEmailProvider(
        client_id="test-id",
        client_secret="test-sec",
        refresh_token="test-ref",
        sender_email="owner@gmail.com"
    )

    mock_service = MagicMock()
    mock_send = MagicMock()
    mock_send.execute.return_value = {
        "id": "gmail_msg_111",
        "threadId": "gmail_thread_222",
        "labelIds": ["SENT"]
    }
    mock_service.users.return_value.messages.return_value.send.return_value = mock_send

    with patch.object(provider, "get_service", return_value=mock_service):
        res = await provider.send_email(
            to_email="prospect@business.com",
            subject="Commercial HVAC Observation",
            body="Reviewing your site speed."
        )

        assert res["status"] == "SUCCESS"
        assert res["provider"] == "gmail"
        assert res["message_id"] == "gmail_msg_111"
        assert res["details"]["gmail_thread_id"] == "gmail_thread_222"
        mock_service.users.return_value.messages.return_value.send.assert_called_once()


# 11. Thread Matching in Inbox Poller Test
@pytest.mark.asyncio
async def test_inbox_poller_thread_matching(db_session):
    biz = Business(
        name="Desert Climate HVAC",
        domain="desertclimate.com",
        website_url="https://desertclimate.com",
        country="US",
        niche="hvac",
        public_email="contact@desertclimate.com"
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="contact@desertclimate.com",
        subject="Audit Observation",
        body="Here is the report.",
        status=OutreachStatus.SENT.value
    )
    db_session.add(msg)
    await db_session.flush()

    event = OutreachEvent(
        outreach_message_id=msg.id,
        event_type="email_dispatched",
        details={
            "gmail_message_id": "orig_gmail_123",
            "gmail_thread_id": "thread_abc_789",
            "message_id_header": "<msg_header_xyz@gmail.com>"
        }
    )
    db_session.add(event)
    await db_session.commit()

    # Process inbound reply with matching threadId
    reply = await inbox_poller.process_inbound_message(
        session=db_session,
        sender_email="contact@desertclimate.com",
        subject="Re: Audit Observation",
        body="Yes, please send more details on the turnaround.",
        thread_id="thread_abc_789"
    )

    assert reply is not None
    assert reply.business_id == biz.id
    assert reply.outreach_message_id == msg.id
