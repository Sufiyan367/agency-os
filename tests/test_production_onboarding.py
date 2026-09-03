import os
import pytest
import hmac
import hashlib
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings
from app.core.settings_manager import settings_manager, SettingsManager
from app.outreach.providers.factory import get_email_provider
from app.payments.abstraction import get_payment_provider, RealRazorpayPaymentProvider, MockPaymentProvider
from app.payments.deal_service import deal_closing_service
from app.database.connection import get_db
from app.database.models import Business, Proposal, Customer

@pytest.fixture(autouse=True)
def reset_settings_state():
    """Ensures safe baseline state before and after each test."""
    original_email_provider = settings.EMAIL_PROVIDER
    original_email_dry_run = settings.EMAIL_DRY_RUN
    original_resend_key = settings.RESEND_API_KEY
    original_sendgrid_key = settings.SENDGRID_API_KEY
    original_smtp_host = settings.SMTP_HOST
    original_smtp_user = settings.SMTP_USER
    original_pay_mode = getattr(settings, "RAZORPAY_MODE", "test")
    original_pay_dry_run = settings.PAYMENT_DRY_RUN
    original_pay_key_id = settings.RAZORPAY_KEY_ID
    original_pay_key_sec = settings.RAZORPAY_KEY_SECRET
    SettingsManager._test_email_verified = False
    if "_test_email_verified" in settings_manager.__dict__:
        del settings_manager.__dict__["_test_email_verified"]

    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    env_backup = None
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            env_backup = f.read()

    yield

    settings.EMAIL_PROVIDER = original_email_provider
    settings.EMAIL_DRY_RUN = original_email_dry_run
    settings.RESEND_API_KEY = original_resend_key
    settings.SENDGRID_API_KEY = original_sendgrid_key
    settings.SMTP_HOST = original_smtp_host
    settings.SMTP_USER = original_smtp_user
    setattr(settings, "RAZORPAY_MODE", original_pay_mode)
    settings.PAYMENT_DRY_RUN = original_pay_dry_run
    settings.RAZORPAY_KEY_ID = original_pay_key_id
    settings.RAZORPAY_KEY_SECRET = original_pay_key_sec
    SettingsManager._test_email_verified = False
    if "_test_email_verified" in settings_manager.__dict__:
        del settings_manager.__dict__["_test_email_verified"]

    if env_backup is not None:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_backup)


@pytest.mark.asyncio
async def test_secrets_never_returned_by_api():
    """
    Verifies that raw API keys and secrets are NEVER exposed in API responses.
    Only masked strings or boolean configured flags are returned.
    """
    settings.RESEND_API_KEY = "re_live_secret_key_1234567890"
    settings.SENDGRID_API_KEY = "SG.live_secret_sendgrid_9876543210"
    settings.SMTP_PASSWORD = "super_secret_smtp_password"
    settings.RAZORPAY_KEY_SECRET = "rzp_secret_razorpay_live_pass"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/settings")
        assert res.status_code == 200
        data = res.json()

        # Check Email Secrets
        email_data = data["email"]
        assert "re_live_secret_key_1234567890" not in str(data)
        assert "SG.live_secret_sendgrid_9876543210" not in str(data)
        assert "super_secret_smtp_password" not in str(data)
        assert "rzp_secret_razorpay_live_pass" not in str(data)

        assert email_data["resend_configured"] is True
        assert email_data["resend_key_masked"].startswith("re_")
        assert "••••" in email_data["resend_key_masked"]

        # Check Payment Secrets
        pay_data = data["payments"]
        assert pay_data["key_secret_configured"] is True
        assert pay_data["key_secret_masked"].startswith("rz")
        assert "••••" in pay_data["key_secret_masked"]
        assert "key_secret" not in pay_data or pay_data.get("key_secret") is None


@pytest.mark.asyncio
async def test_missing_email_credentials_safety():
    """Verifies that missing credentials for live providers safely block activation."""
    settings.EMAIL_PROVIDER = "resend"
    settings.RESEND_API_KEY = None

    with pytest.raises(ValueError) as exc:
        await settings_manager.toggle_live_email(enabled=True)
    assert "RESEND_API_KEY is not configured" in str(exc.value)

    settings.EMAIL_PROVIDER = "sendgrid"
    settings.SENDGRID_API_KEY = None
    with pytest.raises(ValueError) as exc2:
        await settings_manager.toggle_live_email(enabled=True)
    assert "SENDGRID_API_KEY is not configured" in str(exc2.value)

    settings.EMAIL_PROVIDER = "smtp"
    settings.SMTP_HOST = None
    with pytest.raises(ValueError) as exc3:
        await settings_manager.toggle_live_email(enabled=True)
    assert "SMTP_HOST and SMTP_USERNAME are not configured" in str(exc3.value)


@pytest.mark.asyncio
async def test_invalid_email_configuration():
    """Verifies that invalid provider name or malformed email addresses are rejected."""
    with pytest.raises(ValueError) as exc:
        await settings_manager.update_email_settings(provider="unsupported_mail_provider")
    assert "Unsupported email provider" in str(exc.value)

    with pytest.raises(ValueError) as exc2:
        await settings_manager.send_test_email("not-a-valid-email")
    assert "Invalid test recipient address" in str(exc2.value)


@pytest.mark.asyncio
async def test_test_email_success_and_status_transition():
    """Verifies that diagnostic test email execution works and unlocks CONFIGURED state."""
    settings.EMAIL_PROVIDER = "dry_run"
    settings.EMAIL_DRY_RUN = True
    assert settings_manager.get_email_status() == "DRY RUN"

    test_res = await settings_manager.send_test_email("operator@agencytest.com")
    assert test_res["success"] is True
    assert test_res["test_verified"] is True
    assert settings_manager._test_email_verified is True


@pytest.mark.asyncio
async def test_dry_run_blocks_real_delivery():
    """Verifies that DRY_RUN mode strictly isolates outbound network delivery."""
    settings.EMAIL_DRY_RUN = True
    provider = get_email_provider()
    assert "Mock" in provider.__class__.__name__ or "DryRun" in provider.__class__.__name__

    delivery = await provider.send_email(
        to_email="prospect@dallascooling.com",
        subject="Audit Review",
        body="Audit findings",
        from_email="outreach@agencygrowth.co"
    )
    assert delivery["status"] == "SUCCESS"
    assert delivery["details"]["dry_run"] is True
    assert delivery["message_id"].startswith("dry_run_")


@pytest.mark.asyncio
async def test_live_mode_explicit_activation_safety_lock():
    """
    Verifies the multi-gate safety lock for enabling Live Email:
    1. Provider cannot be 'dry_run'.
    2. Credentials must exist.
    3. Test email must be verified.
    """
    settings.EMAIL_PROVIDER = "resend"
    settings.RESEND_API_KEY = "re_test_dummy_key_12345"
    SettingsManager._test_email_verified = False  # Has not verified test email yet!

    # Should be blocked by safety lock
    with pytest.raises(RuntimeError) as exc:
        await settings_manager.toggle_live_email(enabled=True)
    assert "Safety Lock Active" in str(exc.value)
    assert "successful test email" in str(exc.value)

    # Now verify test email
    SettingsManager._test_email_verified = True
    res = await settings_manager.toggle_live_email(enabled=True)
    assert settings.EMAIL_DRY_RUN is False
    assert res["email"]["status"] == "LIVE"

    # Safely disable live mode back to dry run
    res_off = await settings_manager.toggle_live_email(enabled=False)
    assert settings.EMAIL_DRY_RUN is True
    assert res_off["email"]["dry_run"] is True


@pytest.mark.asyncio
async def test_payment_test_mode_and_live_mode_gate():
    """Verifies Razorpay test mode vs live mode credentials gate."""
    # Test mode default
    settings.RAZORPAY_KEY_ID = "rzp_test_123456789"
    settings.RAZORPAY_KEY_SECRET = "secret_test_987654321"
    setattr(settings, "RAZORPAY_MODE", "test")
    settings.PAYMENT_DRY_RUN = True

    status = settings_manager.get_payment_status()
    assert status == "TEST MODE"

    # Switching to live mode without credentials fails
    settings.RAZORPAY_KEY_ID = ""
    settings.RAZORPAY_KEY_SECRET = ""
    with pytest.raises(ValueError) as exc:
        await settings_manager.update_payment_settings(mode="live")
    assert "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be configured" in str(exc.value)

    # Switching to live mode with credentials succeeds
    settings.RAZORPAY_KEY_ID = "rzp_live_abc123"
    settings.RAZORPAY_KEY_SECRET = "rzp_live_secret456"
    res = await settings_manager.update_payment_settings(mode="live")
    assert getattr(settings, "RAZORPAY_MODE") == "live"
    assert settings.PAYMENT_DRY_RUN is False
    assert res["payments"]["status"] == "LIVE"


@pytest.mark.asyncio
async def test_advance_and_remaining_balance_calculation():
    """
    Verifies automatic advance deposit and remaining balance calculation
    e.g. $2,500 total, 40% advance -> $1,000 due, $1,500 remaining balance.
    """
    total_val = 2500.0
    advance_pct = 40.0
    adv_due = round(total_val * (advance_pct / 100.0), 2)
    remaining = round(total_val - adv_due, 2)

    assert adv_due == 1000.0
    assert remaining == 1500.0

    import uuid
    uid = uuid.uuid4().hex[:6]
    dom = f"balance-calc-{uid}.com"

    async for db in get_db():
        biz = Business(name="Balance Calc Test LLC", domain=dom, country="US", city="Austin", niche="HVAC")
        db.add(biz)
        await db.flush()

        # Proposal creation with split
        prop = await deal_closing_service.create_proposal(
            session=db,
            business_id=biz.id,
            title="Commercial Automation Architecture",
            total_value=total_val,
            advance_required=adv_due
        )
        assert prop.total_value == 2500.0
        assert prop.advance_required == 1000.0
        assert prop.remaining_balance == 2500.0
        assert prop.advance_received == 0.0

        # Commercial floor check (<$1,000 must fail)
        with pytest.raises(ValueError) as exc:
            await deal_closing_service.create_proposal(
                session=db,
                business_id=biz.id,
                title="Tiny Sub-threshold Proposal",
                total_value=500.0,
                advance_required=200.0
            )
        assert "commercial qualification requirement" in str(exc.value)
        break


@pytest.mark.asyncio
async def test_unauthorized_payment_success_prevention():
    """
    Verifies that payment status is NEVER marked successful without
    verified Razorpay cryptographic signatures or legitimate provider confirmation.
    """
    provider = RealRazorpayPaymentProvider(
        key_id="rzp_test_mock",
        key_secret="mock_secret",
        webhook_secret="test_webhook_secret_123"
    )

    payload = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_123"}}}}'
    bogus_sig = "bogus_unauthorized_signature_hex"

    is_valid, reason = provider.verify_webhook_signature(payload, bogus_sig)
    assert is_valid is False
    assert "mismatch" in reason.lower()

    # Valid signature check
    valid_sig = hmac.new(b"test_webhook_secret_123", payload, hashlib.sha256).hexdigest()
    is_valid_real, reason_real = provider.verify_webhook_signature(payload, valid_sig)
    assert is_valid_real is True
    assert "valid" in reason_real.lower()
