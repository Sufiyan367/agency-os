import pytest
import logging
from unittest.mock import patch, MagicMock
from rich.console import Console
import io

from app.core.config import settings
from app.core.settings_manager import SettingsManager
from app.infrastructure.domain_validator import DomainValidator, domain_validator
from app.infrastructure.payment_validator import PaymentValidator, payment_validator
from app.infrastructure.setup_wizard import SetupWizard

@pytest.fixture(autouse=True)
def restore_settings():
    orig_state = {k: getattr(settings, k) for k in type(settings).model_fields.keys()}
    yield
    for k, v in orig_state.items():
        try:
            setattr(settings, k, v)
        except Exception:
            pass

@pytest.fixture
def mock_dns():
    with patch("dns.resolver.Resolver.resolve") as mock_resolve:
        yield mock_resolve

def test_domain_syntax_validation():
    assert domain_validator.validate_domain_syntax("agencygrowth.co") is True
    assert domain_validator.validate_domain_syntax("example.org") is True
    assert domain_validator.validate_domain_syntax("invalid_domain") is False
    assert domain_validator.validate_domain_syntax("") is False

def test_email_syntax_validation():
    assert domain_validator.validate_email_syntax("user@example.com") is True
    assert domain_validator.validate_email_syntax("elena.vance@agencygrowth.co") is True
    assert domain_validator.validate_email_syntax("not-an-email") is False
    assert domain_validator.validate_email_syntax("user@") is False
    assert domain_validator.validate_email_syntax("") is False

def test_identity_consistency_validation():
    # Valid
    res = domain_validator.validate_identity_consistency(
        "outreach@agencygrowth.co", "replies@agencygrowth.co", expected_domain="agencygrowth.co"
    )
    assert res["valid"] is True
    assert res["sender_domain"] == "agencygrowth.co"

    # Mismatched expected domain
    res_mismatch = domain_validator.validate_identity_consistency(
        "outreach@otherdomain.com", "replies@otherdomain.com", expected_domain="agencygrowth.co"
    )
    assert res_mismatch["valid"] is False
    assert "does not match expected domain" in res_mismatch["error"]

    # Invalid email syntax
    res_invalid = domain_validator.validate_identity_consistency(
        "not-an-email", "replies@agencygrowth.co"
    )
    assert res_invalid["valid"] is False

def test_payment_validation_test_mode_success():
    res = payment_validator.validate_razorpay_configuration(
        key_id="rzp_test_1234567890ABC",
        key_secret="secret_key_12345",
        webhook_secret="whsec_12345",
        mode="test",
        currency="USD"
    )
    assert res["valid"] is True
    assert res["mode"] == "test"
    assert res["masked_summary"]["key_secret_status"] == "PRESENT"
    assert res["masked_summary"]["webhook_secret_status"] == "PRESENT"
    assert "secret_key_12345" not in str(res["masked_summary"])

def test_payment_validation_test_live_mismatch_rejected():
    # TEST mode with live key
    res = payment_validator.validate_razorpay_configuration(
        key_id="rzp_live_999888777666",
        key_secret="secret_key_12345",
        webhook_secret="whsec_12345",
        mode="test",
        currency="USD"
    )
    assert res["valid"] is False
    assert any("rzp_test_" in err for err in res["errors"])

    # LIVE mode with test key
    res_live = payment_validator.validate_razorpay_configuration(
        key_id="rzp_test_1234567890ABC",
        key_secret="secret_key_12345",
        webhook_secret="whsec_12345",
        mode="live",
        currency="USD"
    )
    assert res_live["valid"] is False
    assert any("rzp_live_" in err for err in res_live["errors"])

def test_payment_validation_invalid_currency():
    res = payment_validator.validate_razorpay_configuration(
        key_id="rzp_test_1234567890ABC",
        key_secret="secret_key_12345",
        webhook_secret="whsec_12345",
        mode="test",
        currency="XYZ_INVALID"
    )
    assert res["valid"] is False
    assert any("Unsupported or invalid currency" in err for err in res["errors"])

def test_payment_validation_short_secrets():
    res = payment_validator.validate_razorpay_configuration(
        key_id="rzp_test_1234567890ABC",
        key_secret="short",
        webhook_secret="tiny",
        mode="test",
        currency="USD"
    )
    assert res["valid"] is False
    assert any("too short" in err for err in res["errors"])

def test_wizard_hidden_secret_input_and_summary_redaction(monkeypatch):
    dummy_api_key = "re_dummy_secret_api_key_999"
    dummy_pay_secret = "rzp_secret_key_secure_888"
    dummy_wh_secret = "rzp_webhook_secret_777"

    prompts = {
        "Select provider [A/B/C]": "A",
        "Enter real sender email address (e.g. outreach@yourdomain.com)": "ceo@growthagency.com",
        "Enter sender display name": "Elena Vance",
        "Enter reply-to email address": "ceo@growthagency.com",
        "Select Razorpay environment (A. TEST, B. LIVE)": "A",
        "Enter payment currency (e.g. USD, GBP, EUR, INR)": "USD"
    }

    passwords = {
        "Enter Resend API Key (starts with 're_')": dummy_api_key,
        "Enter Razorpay Key ID (e.g. rzp_test_... or rzp_live_...)": "rzp_test_1234567890ABC",
        "Enter Razorpay Key Secret": dummy_pay_secret,
        "Enter Razorpay Webhook Secret": dummy_wh_secret
    }

    confirms = {
        "Do you want to configure payments now? [yes/no]": True,
        "Save this production configuration? [yes/no]": True
    }

    def mock_prompt(msg, default=""):
        return prompts.get(msg, default)

    def mock_password(msg):
        return passwords[msg]

    def mock_confirm(msg):
        return confirms[msg]

    output_buffer = io.StringIO()
    test_console = Console(file=output_buffer, color_system=None)

    # Intercept SettingsManager.write_env_key to avoid modifying local .env during testing
    written_keys = {}
    def mock_write_env_key(key, val):
        written_keys[key] = val

    monkeypatch.setattr(SettingsManager, "write_env_key", mock_write_env_key)

    wizard = SetupWizard(
        prompt_fn=mock_prompt,
        password_fn=mock_password,
        confirm_fn=mock_confirm,
        custom_console=test_console
    )

    with patch.object(domain_validator, "inspect_domain_dns") as mock_dns_inspect:
        mock_dns_inspect.return_value = {
            "domain": "growthagency.com",
            "valid_syntax": True,
            "dns_available": True,
            "mx_present": True,
            "spf_present": True,
            "spf_includes_provider": True,
            "dmarc_present": True,
            "dmarc_policy": "none",
            "dkim_status": "Provider verification required"
        }
        res = wizard.run()

    rendered_output = output_buffer.getvalue()

    # Confirm secrets are redacted in output
    assert dummy_api_key not in rendered_output
    assert dummy_pay_secret not in rendered_output
    assert dummy_wh_secret not in rendered_output

    # Confirm "Credential: PRESENT" and "Key Secret: PRESENT" are displayed
    assert "Credential:  PRESENT" in rendered_output or "Credential: PRESENT" in rendered_output
    assert "Key Secret:      PRESENT" in rendered_output or "Key Secret: PRESENT" in rendered_output
    assert "Webhook Secret:  PRESENT" in rendered_output or "Webhook Secret: PRESENT" in rendered_output

    # Confirm post-save safety flags were written
    assert written_keys["RESEARCH_ONLY"] == "true"
    assert written_keys["EMAIL_DRY_RUN"] == "true"
    assert written_keys["PAYMENTS_ENABLED"] == "false"
    assert written_keys["PAYMENT_DRY_RUN"] == "true"

    assert res["saved"] is True
    assert res["research_only"] is True
    assert res["email_dry_run"] is True
    assert res["payments_enabled"] is False
    assert res["payment_dry_run"] is True

def test_wizard_no_secret_logging(caplog, monkeypatch):
    dummy_api_key = "re_secret_forbidden_in_logs_123"

    prompts = {
        "Select provider [A/B/C]": "A",
        "Enter real sender email address (e.g. outreach@yourdomain.com)": "outreach@agencygrowth.co",
        "Enter sender display name": "Director",
        "Enter reply-to email address": "outreach@agencygrowth.co"
    }

    passwords = {
        "Enter Resend API Key (starts with 're_')": dummy_api_key
    }

    confirms = {
        "Do you want to configure payments now? [yes/no]": False,
        "Save this production configuration? [yes/no]": True
    }

    monkeypatch.setattr(SettingsManager, "write_env_key", lambda k, v: None)

    wizard = SetupWizard(
        prompt_fn=lambda m, d="": prompts.get(m, d),
        password_fn=lambda m: passwords[m],
        confirm_fn=lambda m: confirms[m],
        custom_console=Console(file=io.StringIO(), color_system=None)
    )

    with caplog.at_level(logging.DEBUG):
        with patch.object(domain_validator, "inspect_domain_dns") as mock_dns_inspect:
            mock_dns_inspect.return_value = {
                "domain": "agencygrowth.co",
                "valid_syntax": True,
                "dns_available": True,
                "mx_present": True,
                "spf_present": True,
                "spf_includes_provider": True,
                "dmarc_present": True,
                "dmarc_policy": "none",
                "dkim_status": "Provider verification required"
            }
            wizard.run()

    # Assert secret never logged
    for record in caplog.records:
        assert dummy_api_key not in record.message

def test_wizard_abort_on_pre_save_rejection(monkeypatch):
    prompts = {
        "Select provider [A/B/C]": "A",
        "Enter real sender email address (e.g. outreach@yourdomain.com)": "ceo@example.com",
        "Enter sender display name": "CEO",
        "Enter reply-to email address": "ceo@example.com"
    }

    passwords = {
        "Enter Resend API Key (starts with 're_')": "re_dummy_key_12345"
    }

    confirms = {
        "Do you want to configure payments now? [yes/no]": False,
        "Save this production configuration? [yes/no]": False  # REJECT SAVE
    }

    write_mock = MagicMock()
    monkeypatch.setattr(SettingsManager, "write_env_key", write_mock)

    wizard = SetupWizard(
        prompt_fn=lambda m, d="": prompts.get(m, d),
        password_fn=lambda m: passwords[m],
        confirm_fn=lambda m: confirms[m],
        custom_console=Console(file=io.StringIO(), color_system=None)
    )

    with patch.object(domain_validator, "inspect_domain_dns") as mock_dns_inspect:
        mock_dns_inspect.return_value = {
            "domain": "example.com",
            "valid_syntax": True,
            "dns_available": True,
            "mx_present": True,
            "spf_present": False,
            "spf_includes_provider": False,
            "dmarc_present": False,
            "dmarc_policy": None,
            "dkim_status": "Provider verification required"
        }
        res = wizard.run()

    assert res["saved"] is False
    assert write_mock.call_count == 0  # Nothing written to .env

def test_wizard_invalid_provider_rejected():
    wizard = SetupWizard(
        prompt_fn=lambda m, d="": "INVALID_CHOICE",
        password_fn=lambda m: "secret",
        confirm_fn=lambda m: True,
        custom_console=Console(file=io.StringIO(), color_system=None)
    )
    with pytest.raises(ValueError, match="Invalid provider selection"):
        wizard.run()

def test_wizard_invalid_email_rejected():
    prompts = {
        "Select provider [A/B/C]": "A",
        "Enter real sender email address (e.g. outreach@yourdomain.com)": "not_an_email"
    }
    wizard = SetupWizard(
        prompt_fn=lambda m, d="": prompts.get(m, d),
        password_fn=lambda m: "re_valid_api_key_123",
        confirm_fn=lambda m: True,
        custom_console=Console(file=io.StringIO(), color_system=None)
    )
    with pytest.raises(ValueError, match="Invalid sender email syntax"):
        wizard.run()

def test_wizard_empty_credential_rejected():
    prompts = {
        "Select provider [A/B/C]": "A"
    }
    wizard = SetupWizard(
        prompt_fn=lambda m, d="": prompts.get(m, d),
        password_fn=lambda m: "",  # Empty API key
        confirm_fn=lambda m: True,
        custom_console=Console(file=io.StringIO(), color_system=None)
    )
    with pytest.raises(ValueError, match="Resend API key cannot be empty"):
        wizard.run()

def test_wizard_no_email_dispatched_and_no_payment_created(monkeypatch):
    """
    Verifies that the entire setup wizard process produces ZERO email dispatches
    and ZERO payment requests.
    """
    email_dispatch_mock = MagicMock()
    payment_create_mock = MagicMock()

    from app.outreach.sender import OutreachSenderAdapter
    from app.sales.payment_flow import PaymentWorkflowManager

    monkeypatch.setattr(OutreachSenderAdapter, "send_approved_message", email_dispatch_mock)
    monkeypatch.setattr(PaymentWorkflowManager, "issue_payment_request", payment_create_mock)
    monkeypatch.setattr(SettingsManager, "write_env_key", lambda k, v: None)

    prompts = {
        "Select provider [A/B/C]": "A",
        "Enter real sender email address (e.g. outreach@yourdomain.com)": "real@myagency.com",
        "Enter sender display name": "Director",
        "Enter reply-to email address": "real@myagency.com",
        "Select Razorpay environment (A. TEST, B. LIVE)": "B",
        "Enter payment currency (e.g. USD, GBP, EUR, INR)": "USD"
    }
    passwords = {
        "Enter Resend API Key (starts with 're_')": "re_live_dummy_12345",
        "Enter Razorpay Key ID (e.g. rzp_test_... or rzp_live_...)": "rzp_live_999888777666",
        "Enter Razorpay Key Secret": "live_secret_abc1234",
        "Enter Razorpay Webhook Secret": "whsec_live_5678"
    }
    confirms = {
        "Do you want to configure payments now? [yes/no]": True,
        "Save this production configuration? [yes/no]": True
    }

    wizard = SetupWizard(
        prompt_fn=lambda m, d="": prompts.get(m, d),
        password_fn=lambda m: passwords[m],
        confirm_fn=lambda m: confirms[m],
        custom_console=Console(file=io.StringIO(), color_system=None)
    )

    with patch.object(domain_validator, "inspect_domain_dns") as mock_dns_inspect:
        mock_dns_inspect.return_value = {
            "domain": "myagency.com",
            "valid_syntax": True,
            "dns_available": True,
            "mx_present": True,
            "spf_present": True,
            "spf_includes_provider": True,
            "dmarc_present": True,
            "dmarc_policy": "none",
            "dkim_status": "Provider verification required"
        }
        res = wizard.run()

    # Strict verifications
    assert email_dispatch_mock.call_count == 0
    assert payment_create_mock.call_count == 0
    assert res["research_only"] is True
    assert res["email_dry_run"] is True
    assert res["payments_enabled"] is False
    assert res["payment_dry_run"] is True
