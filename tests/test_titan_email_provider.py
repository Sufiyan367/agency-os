import pytest
from unittest.mock import patch, MagicMock
from app.outreach.providers.titan_provider import TitanEmailProvider

@pytest.mark.asyncio
async def test_titan_email_provider_send_ssl():
    provider = TitanEmailProvider(
        smtp_host="smtp.titan.email",
        smtp_port=465,
        smtp_user="contact@automatedagencyos.tech",
        smtp_password="SuperSecretPassword123!"
    )

    with patch("smtplib.SMTP_SSL") as mock_smtp_ssl:
        mock_server = MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = mock_server

        res = await provider.send_email(
            to_email="prospect@business.com",
            subject="Technical Assessment",
            body="Here is our analysis of your website.",
            from_email="contact@automatedagencyos.tech",
            from_name="Agency Leadership"
        )

        assert res["status"] == "SUCCESS"
        assert res["provider"] == "titan"
        mock_server.login.assert_called_once_with("contact@automatedagencyos.tech", "SuperSecretPassword123!")
        mock_server.send_message.assert_called_once()

@pytest.mark.asyncio
async def test_titan_email_provider_send_starttls():
    provider = TitanEmailProvider(
        smtp_host="smtp.titan.email",
        smtp_port=587,
        smtp_user="contact@automatedagencyos.tech",
        smtp_password="SuperSecretPassword123!"
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        res = await provider.send_email(
            to_email="prospect@business.com",
            subject="Technical Assessment",
            body="Here is our analysis of your website."
        )

        assert res["status"] == "SUCCESS"
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("contact@automatedagencyos.tech", "SuperSecretPassword123!")

@pytest.mark.asyncio
async def test_titan_email_provider_never_leaks_password_on_error():
    provider = TitanEmailProvider(
        smtp_host="smtp.titan.email",
        smtp_port=465,
        smtp_user="contact@automatedagencyos.tech",
        smtp_password="SuperSecretPassword123!"
    )

    with patch("smtplib.SMTP_SSL") as mock_smtp_ssl:
        mock_server = MagicMock()
        mock_server.login.side_effect = Exception("Auth failure for SuperSecretPassword123!")
        mock_smtp_ssl.return_value.__enter__.return_value = mock_server

        with pytest.raises(RuntimeError) as exc_info:
            await provider.send_email(
                to_email="prospect@business.com",
                subject="Test",
                body="Test"
            )

        err_msg = str(exc_info.value)
        assert "SuperSecretPassword123!" not in err_msg
        assert "[REDACTED]" in err_msg

def test_titan_email_provider_auth_health():
    provider = TitanEmailProvider(
        smtp_host="smtp.titan.email",
        smtp_port=465,
        smtp_user="contact@automatedagencyos.tech",
        smtp_password="SuperSecretPassword123!"
    )

    with patch("smtplib.SMTP_SSL") as mock_smtp_ssl:
        mock_server = MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = mock_server

        health = provider.check_auth_health()
        assert health["status"] == "OK"
        assert health["healthy"] is True
        assert health["authenticated_email"] == "contact@automatedagencyos.tech"
