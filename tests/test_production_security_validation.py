import pytest
import re
from app.core.config import settings
from app.core.security import (
    validate_production_configuration,
    SecurityConfigurationError,
    create_session_token,
    verify_session_token_with_role,
    hash_password,
    verify_password,
)
from app.core.logging import SecretMaskingFilter, setup_logging
import logging


def test_startup_fails_closed_when_auth_disabled_in_production():
    """1. In production (APP_ENV=production), AUTH_ENABLED must be True or startup fails closed."""
    orig_env = settings.APP_ENV
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.APP_ENV = "production"
        settings.AUTH_ENABLED = False
        with pytest.raises(SecurityConfigurationError) as exc_info:
            validate_production_configuration(raise_on_error=True)
        assert "AUTH_ENABLED must be True when APP_ENV=production" in str(exc_info.value)
    finally:
        settings.APP_ENV = orig_env
        settings.AUTH_ENABLED = orig_auth


def test_startup_fails_closed_when_debug_enabled_in_production():
    """2. In production, DEBUG must be False or startup fails closed."""
    orig_env = settings.APP_ENV
    orig_debug = settings.DEBUG
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.APP_ENV = "production"
        settings.DEBUG = True
        settings.AUTH_ENABLED = True
        with pytest.raises(SecurityConfigurationError) as exc_info:
            validate_production_configuration(raise_on_error=True)
        assert "DEBUG must be False when APP_ENV=production" in str(exc_info.value)
    finally:
        settings.APP_ENV = orig_env
        settings.DEBUG = orig_debug
        settings.AUTH_ENABLED = orig_auth


def test_startup_fails_closed_when_credentials_missing_under_auth():
    """3. When AUTH_ENABLED=True, missing credentials cause startup to fail closed."""
    orig_auth = settings.AUTH_ENABLED
    orig_pass = settings.DASHBOARD_PASSWORD
    orig_key = settings.API_SECRET_KEY
    orig_sec = settings.SESSION_SECRET
    try:
        settings.AUTH_ENABLED = True

        # Missing password
        settings.DASHBOARD_PASSWORD = ""
        with pytest.raises(SecurityConfigurationError) as exc:
            validate_production_configuration(raise_on_error=True)
        assert "DASHBOARD_PASSWORD cannot be empty" in str(exc.value)

        # Missing API_SECRET_KEY
        settings.DASHBOARD_PASSWORD = hash_password("ValidPassword123!")
        settings.API_SECRET_KEY = ""
        with pytest.raises(SecurityConfigurationError) as exc:
            validate_production_configuration(raise_on_error=True)
        assert "API_SECRET_KEY cannot be empty" in str(exc.value)

        # Missing SESSION_SECRET
        settings.API_SECRET_KEY = "a" * 64
        settings.SESSION_SECRET = ""
        with pytest.raises(SecurityConfigurationError) as exc:
            validate_production_configuration(raise_on_error=True)
        assert "SESSION_SECRET cannot be empty" in str(exc.value)
    finally:
        settings.AUTH_ENABLED = orig_auth
        settings.DASHBOARD_PASSWORD = orig_pass
        settings.API_SECRET_KEY = orig_key
        settings.SESSION_SECRET = orig_sec


def test_startup_fails_closed_when_default_or_placeholder_credentials_used():
    """4. Rejects known default passwords, fallback secrets, and .env.example placeholders."""
    orig_auth = settings.AUTH_ENABLED
    orig_pass = settings.DASHBOARD_PASSWORD
    orig_sec = settings.SESSION_SECRET
    orig_key = settings.API_SECRET_KEY
    try:
        settings.AUTH_ENABLED = True
        forbidden_test_values = [
            ("DASHBOARD_PASSWORD", "agency_admin_2026"),
            ("SESSION_SECRET", "agency_session_hmac_secret_2026"),
            ("API_SECRET_KEY", "REPLACE_WITH_RANDOM_HEX_64_CHAR_KEY"),
            ("DASHBOARD_PASSWORD", "password123"),
            ("VIEWER_PASSWORD", "agency_viewer_2026"),
            ("SESSION_SECRET", "admin123"),
        ]
        for field, bad_val in forbidden_test_values:
            # Set all other required secrets to valid dummy values
            settings.DASHBOARD_PASSWORD = hash_password("SecureAdminPass2026!")
            settings.VIEWER_PASSWORD = hash_password("SecureViewerPass2026!")
            settings.API_SECRET_KEY = "b" * 64
            settings.SESSION_SECRET = "c" * 64
            setattr(settings, field, bad_val)

            with pytest.raises(SecurityConfigurationError) as exc:
                validate_production_configuration(raise_on_error=True)
            assert "Insecure default or example placeholder detected" in str(exc.value)
    finally:
        settings.AUTH_ENABLED = orig_auth
        settings.DASHBOARD_PASSWORD = orig_pass
        settings.SESSION_SECRET = orig_sec
        settings.API_SECRET_KEY = orig_key


def test_startup_fails_closed_when_secret_entropy_insufficient():
    """5. Fails closed if API_SECRET_KEY or SESSION_SECRET is shorter than 32 characters."""
    orig_auth = settings.AUTH_ENABLED
    orig_pass = settings.DASHBOARD_PASSWORD
    orig_key = settings.API_SECRET_KEY
    orig_sec = settings.SESSION_SECRET
    try:
        settings.AUTH_ENABLED = True
        settings.DASHBOARD_PASSWORD = hash_password("SecureAdminPass2026!")
        settings.VIEWER_PASSWORD = hash_password("SecureViewerPass2026!")
        settings.SESSION_SECRET = "e" * 64

        # Short API key
        settings.API_SECRET_KEY = "short_key_under_32_chars"
        with pytest.raises(SecurityConfigurationError) as exc:
            validate_production_configuration(raise_on_error=True)
        assert "API_SECRET_KEY must be at least 32 characters" in str(exc.value)

        # Short Session Secret
        settings.API_SECRET_KEY = "d" * 64
        settings.SESSION_SECRET = "short_session_key"
        with pytest.raises(SecurityConfigurationError) as exc:
            validate_production_configuration(raise_on_error=True)
        assert "SESSION_SECRET must be at least 32 characters" in str(exc.value)
    finally:
        settings.AUTH_ENABLED = orig_auth
        settings.DASHBOARD_PASSWORD = orig_pass
        settings.API_SECRET_KEY = orig_key
        settings.SESSION_SECRET = orig_sec


def test_startup_fails_closed_when_passwords_not_pbkdf2_in_production():
    """6. In production, passwords must use PBKDF2 format (pbkdf2:sha256:...) or startup fails."""
    orig_env = settings.APP_ENV
    orig_auth = settings.AUTH_ENABLED
    orig_debug = settings.DEBUG
    orig_pass = settings.DASHBOARD_PASSWORD
    orig_vpass = settings.VIEWER_PASSWORD
    orig_key = settings.API_SECRET_KEY
    orig_sec = settings.SESSION_SECRET
    try:
        settings.APP_ENV = "production"
        settings.AUTH_ENABLED = True
        settings.DEBUG = False
        settings.API_SECRET_KEY = "f" * 64
        settings.SESSION_SECRET = "g" * 64
        settings.VIEWER_PASSWORD = hash_password("SecureViewerPass2026!")

        # Plaintext dashboard password
        settings.DASHBOARD_PASSWORD = "PlaintextLongPasswordNotHashed!"
        with pytest.raises(SecurityConfigurationError) as exc:
            validate_production_configuration(raise_on_error=True)
        assert "DASHBOARD_PASSWORD must use the PBKDF2 hashed format" in str(exc.value)

        # Plaintext viewer password
        settings.DASHBOARD_PASSWORD = hash_password("SecureAdminPass2026!")
        settings.VIEWER_PASSWORD = "PlaintextViewerPasswordNotHashed!"
        with pytest.raises(SecurityConfigurationError) as exc:
            validate_production_configuration(raise_on_error=True)
        assert "VIEWER_PASSWORD must use the PBKDF2 hashed format" in str(exc.value)
    finally:
        settings.APP_ENV = orig_env
        settings.AUTH_ENABLED = orig_auth
        settings.DEBUG = orig_debug
        settings.DASHBOARD_PASSWORD = orig_pass
        settings.VIEWER_PASSWORD = orig_vpass
        settings.API_SECRET_KEY = orig_key
        settings.SESSION_SECRET = orig_sec


def test_startup_succeeds_with_valid_production_credentials():
    """7. Startup succeeds without errors when all production security criteria are satisfied."""
    orig_env = settings.APP_ENV
    orig_auth = settings.AUTH_ENABLED
    orig_debug = settings.DEBUG
    orig_user = settings.DASHBOARD_USERNAME
    orig_vuser = settings.VIEWER_USERNAME
    orig_pass = settings.DASHBOARD_PASSWORD
    orig_vpass = settings.VIEWER_PASSWORD
    orig_key = settings.API_SECRET_KEY
    orig_sec = settings.SESSION_SECRET
    try:
        settings.APP_ENV = "production"
        settings.AUTH_ENABLED = True
        settings.DEBUG = False
        settings.DASHBOARD_USERNAME = "prod_admin"
        settings.DASHBOARD_PASSWORD = hash_password("ValidProductionAdminPassword2026!")
        settings.VIEWER_USERNAME = "prod_viewer"
        import secrets as pysecrets
        settings.API_SECRET_KEY = pysecrets.token_hex(32)
        settings.SESSION_SECRET = pysecrets.token_hex(32)

        errors = validate_production_configuration(raise_on_error=True)
        assert errors == []
    finally:
        settings.APP_ENV = orig_env
        settings.AUTH_ENABLED = orig_auth
        settings.DEBUG = orig_debug
        settings.DASHBOARD_USERNAME = orig_user
        settings.VIEWER_USERNAME = orig_vuser
        settings.DASHBOARD_PASSWORD = orig_pass
        settings.VIEWER_PASSWORD = orig_vpass
        settings.API_SECRET_KEY = orig_key
        settings.SESSION_SECRET = orig_sec


def test_create_session_token_fails_closed_if_session_secret_empty():
    """8. create_session_token must fail closed with SecurityConfigurationError if SESSION_SECRET is empty."""
    orig_sec = settings.SESSION_SECRET
    try:
        settings.SESSION_SECRET = ""
        with pytest.raises(SecurityConfigurationError) as exc:
            create_session_token("admin", role="admin")
        assert "SESSION_SECRET is empty" in str(exc.value)

        # verify_session_token_with_role must return None
        assert verify_session_token_with_role("admin.admin.12345.sig") is None
    finally:
        settings.SESSION_SECRET = orig_sec


def test_secret_masking_filter_redacts_pbkdf2_hashes_and_tokens():
    """9. SecretMaskingFilter redacts PBKDF2 hashes, API keys, and session tokens from log records."""
    filter_instance = SecretMaskingFilter()

    # Log record with PBKDF2 hash
    record1 = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="User authenticated with pbkdf2:sha256:100000$abc123$deadbeef",
        args=(), exc_info=None
    )
    filter_instance.filter(record1)
    assert "pbkdf2:sha256:100000$abc123$deadbeef" not in record1.msg
    assert "[REDACTED]" in record1.msg or "pbkdf2" not in record1.msg

    # Log record with API key
    record2 = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="API_KEY=0123456789abcdef0123456789abcdef",
        args=(), exc_info=None
    )
    filter_instance.filter(record2)
    assert "0123456789abcdef0123456789abcdef" not in record2.msg
    assert "[REDACTED]" in record2.msg


def test_docker_security_non_root_and_drop_capabilities():
    """10. Verifies Dockerfile and docker-compose configurations enforce non-root user and minimal caps."""
    with open("Dockerfile", "r", encoding="utf-8") as f:
        dockerfile_content = f.read()

    assert "appuser" in dockerfile_content
    assert "gosu appuser" in dockerfile_content or "USER appuser" in dockerfile_content or "entrypoint.sh" in dockerfile_content
    assert "HEALTHCHECK" in dockerfile_content

    with open("docker-compose.yml", "r", encoding="utf-8") as f:
        compose_content = f.read()

    assert "no-new-privileges:true" in compose_content
    assert "cap_drop:" in compose_content
    assert "127.0.0.1:8000:8000" in compose_content
