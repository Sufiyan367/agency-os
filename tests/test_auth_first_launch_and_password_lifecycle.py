import pytest
import time
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete

from app.api.app import app
from app.core.config import settings
from app.core.auth_service import auth_service
from app.core.security import (
    create_session_token,
    verify_password,
    hash_password,
    rate_limiter,
    webhook_replay_guard
)
from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import User

@pytest.fixture(scope="module", autouse=True)
def preserve_module_users():
    """Safeguards real database users by restoring them after test module completes."""
    import os
    import sqlite3
    db_file = "agency.db"
    backup_rows = []
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
            if cur.fetchone():
                cur.execute("SELECT username, password_hash, role, is_setup_completed, created_at, updated_at FROM users;")
                backup_rows = cur.fetchall()
            conn.close()
        except Exception:
            backup_rows = []

    yield

    if backup_rows and os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("DELETE FROM users;")
            cur.executemany(
                "INSERT INTO users (username, password_hash, role, is_setup_completed, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
                backup_rows
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

@pytest.fixture(autouse=True)
async def setup_test_environment():
    """Ensures database is initialized and rate limits are reset."""
    await init_db()
    await rate_limiter.reset()
    await webhook_replay_guard.reset()
    auth_service.clear_cache()
    yield
    await rate_limiter.reset()
    await webhook_replay_guard.reset()
    auth_service.clear_cache()

@pytest.fixture
async def clean_user_table():
    """Cleans up user table before and after test."""
    auth_service.clear_cache()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User))
        await session.commit()
    yield
    auth_service.clear_cache()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User))
        await session.commit()

@pytest.mark.asyncio
async def test_fresh_database_requires_setup(clean_user_table):
    """1. On a fresh database with no users, setup is required."""
    orig_auth = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        async with AsyncSessionLocal() as session:
            assert await auth_service.is_setup_required(session) is True

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Check API status endpoint
            resp = await client.get("/api/auth/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["setup_required"] is True
            assert data["status"] == "SETUP_REQUIRED"

            # Check /dashboard redirects to /setup
            resp_dash = await client.get("/dashboard", follow_redirects=False)
            assert resp_dash.status_code in (302, 307)
            assert resp_dash.headers["location"] == "/setup"

            # Check /setup serves setup page
            resp_setup = await client.get("/setup")
            assert resp_setup.status_code == 200
            assert "FIRST-LAUNCH ADMINISTRATOR SETUP" in resp_setup.text
    finally:
        settings.AUTH_ENABLED = orig_auth

@pytest.mark.asyncio
async def test_password_strength_policy_enforcement():
    """2. Verifies password policy rules (min 12 chars, not weak/default)."""
    # Empty / whitespace
    assert auth_service.validate_password_strength("")[0] is False
    assert auth_service.validate_password_strength("   ")[0] is False

    # Too short (< 12)
    assert auth_service.validate_password_strength("Short123!")[0] is False
    valid, reason = auth_service.validate_password_strength("Short123!")
    assert "at least 12 characters" in reason

    # Common / default patterns
    assert auth_service.validate_password_strength("admin1234567")[0] is False
    assert auth_service.validate_password_strength("password1234")[0] is False
    assert auth_service.validate_password_strength("agency_admin_2026")[0] is False
    assert auth_service.validate_password_strength("123456789012")[0] is False

    # Low entropy / repetition
    assert auth_service.validate_password_strength("aaaaaaaaaaaa")[0] is False

    # Strong passphrases
    assert auth_service.validate_password_strength("Hyperion-Secure-Passkey-2026")[0] is True
    assert auth_service.validate_password_strength("xK9#mQ2$vL8*wP4!zR7")[0] is True

@pytest.mark.asyncio
async def test_complete_setup_success(clean_user_table):
    """3. Completing first-launch setup hashes password, creates user, and sets session."""
    orig_auth = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Attempt setup with mismatched passwords
            resp_mismatch = await client.post("/api/auth/setup", json={
                "username": "admin",
                "password": "CorrectHorseBatteryStaple2026!",
                "confirm_password": "WrongPassword2026!"
            })
            assert resp_mismatch.status_code == 400
            assert "confirmation does not match" in resp_mismatch.json()["detail"].lower()

            # Attempt setup with weak password
            resp_weak = await client.post("/api/auth/setup", json={
                "username": "admin",
                "password": "admin1234567",
                "confirm_password": "admin1234567"
            })
            assert resp_weak.status_code == 400

            # Valid setup
            valid_pw = "Nexus-Alpha-Secure-9988!"
            resp = await client.post("/api/auth/setup", json={
                "username": "admin",
                "password": valid_pw,
                "confirm_password": valid_pw
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "SUCCESS"
            assert data["username"] == "admin"
            assert "agency_session" in resp.cookies

            # Verify in database: password is PBKDF2 hashed, not plaintext
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
                assert user is not None
                assert user.role == "admin"
                assert user.is_setup_completed is True
                assert user.password_hash.startswith("pbkdf2:sha256:100000$")
                assert valid_pw not in user.password_hash
                assert verify_password(valid_pw, user.password_hash) is True
    finally:
        settings.AUTH_ENABLED = orig_auth

@pytest.mark.asyncio
async def test_setup_is_one_time_only(clean_user_table):
    """4. Setup endpoint cannot be called again after completion."""
    valid_pw = "Galactic-Starlight-9944#"
    async with AsyncSessionLocal() as session:
        await auth_service.complete_setup(session, "admin", valid_pw, valid_pw)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Second call to /api/auth/setup must be rejected with 400 Bad Request
        resp = await client.post("/api/auth/setup", json={
            "username": "attacker",
            "password": "MaliciousPassword123!",
            "confirm_password": "MaliciousPassword123!"
        })
        assert resp.status_code == 400
        assert "already been completed" in resp.json()["detail"].lower()

        # Navigating to /setup now redirects to /login
        resp_setup = await client.get("/setup", follow_redirects=False)
        assert resp_setup.status_code in (302, 307)
        assert resp_setup.headers["location"] == "/login"

@pytest.mark.asyncio
async def test_login_with_database_user(clean_user_table):
    """5. Verifies login succeeds with database user and fails on invalid credentials."""
    valid_pw = "Titan-Defense-Network-4422!"
    async with AsyncSessionLocal() as session:
        await auth_service.complete_setup(session, "admin", valid_pw, valid_pw)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Bad username
        resp_bad_u = await client.post("/api/auth/login", json={
            "username": "wrong_user",
            "password": valid_pw
        })
        assert resp_bad_u.status_code == 401
        assert "Invalid username or password" in resp_bad_u.json()["detail"]

        # Bad password
        resp_bad_p = await client.post("/api/auth/login", json={
            "username": "admin",
            "password": "IncorrectPassword123!"
        })
        assert resp_bad_p.status_code == 401
        assert "Invalid username or password" in resp_bad_p.json()["detail"]

        # Correct credentials
        resp_ok = await client.post("/api/auth/login", json={
            "username": "admin",
            "password": valid_pw
        })
        assert resp_ok.status_code == 200
        data = resp_ok.json()
        assert data["status"] == "SUCCESS"
        assert data["role"] == "admin"
        assert "agency_session" in resp_ok.cookies

@pytest.mark.asyncio
async def test_change_password_lifecycle_and_session_invalidation(clean_user_table):
    """6. Change password verifies current password, updates hash, and invalidates old sessions."""
    orig_auth = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        pw1 = "Initial-Security-Phrase-1111!"
        pw2 = "Updated-Security-Phrase-2222!"

        async with AsyncSessionLocal() as session:
            await auth_service.complete_setup(session, "admin", pw1, pw1)

        # Login to obtain initial session
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_resp = await client.post("/api/auth/login", json={"username": "admin", "password": pw1})
            assert login_resp.status_code == 200
            token1 = login_resp.json()["token"]

            # Change password with wrong current password -> rejected
            client.cookies.set("agency_session", token1)
            resp_wrong = await client.post("/api/auth/change-password", json={
                "current_password": "WrongPassword999!",
                "new_password": pw2,
                "confirm_password": pw2
            })
            assert resp_wrong.status_code == 400
            assert "Current password is incorrect" in resp_wrong.json()["detail"]

            # Change password to the same password -> rejected
            resp_same = await client.post("/api/auth/change-password", json={
                "current_password": pw1,
                "new_password": pw1,
                "confirm_password": pw1
            })
            assert resp_same.status_code == 400
            assert "cannot be identical" in resp_same.json()["detail"].lower()

            # Valid change password
            resp_change = await client.post("/api/auth/change-password", json={
                "current_password": pw1,
                "new_password": pw2,
                "confirm_password": pw2
            })
            assert resp_change.status_code == 200
            assert resp_change.json()["status"] == "SUCCESS"

            # Old token1 must now be rejected as revoked/invalid (401 Unauthorized by middleware)
            client.cookies.set("agency_session", token1)
            resp_check = await client.get("/api/auth/me")
            assert resp_check.status_code == 401

            # Login with old password fails
            resp_old_login = await client.post("/api/auth/login", json={"username": "admin", "password": pw1})
            assert resp_old_login.status_code == 401

            # Login with new password succeeds
            resp_new_login = await client.post("/api/auth/login", json={"username": "admin", "password": pw2})
            assert resp_new_login.status_code == 200
            assert resp_new_login.json()["status"] == "SUCCESS"
    finally:
        settings.AUTH_ENABLED = orig_auth

@pytest.mark.asyncio
async def test_viewer_role_cannot_change_password(clean_user_table):
    """7. Users with 'viewer' role are forbidden from changing admin credentials."""
    orig_auth = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        # Create viewer session token
        viewer_token = create_session_token("viewer", role="viewer")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.cookies.set("agency_session", viewer_token)
            resp = await client.post("/api/auth/change-password", json={
                "current_password": "any",
                "new_password": "NewSecretPassphrase-2026!",
                "confirm_password": "NewSecretPassphrase-2026!"
            })
            assert resp.status_code == 403
            assert "Forbidden" in resp.json()["detail"]
    finally:
        settings.AUTH_ENABLED = orig_auth

@pytest.mark.asyncio
async def test_reset_admin_restores_setup_mode(clean_user_table):
    """8. Resetting admin user clears user from database and triggers setup mode."""
    valid_pw = "Temporary-Reset-Passkey-5555!"
    async with AsyncSessionLocal() as session:
        await auth_service.complete_setup(session, "admin", valid_pw, valid_pw)
        assert await auth_service.is_setup_required(session) is False

        # Reset admin
        success = await auth_service.reset_admin_user(session)
        assert success is True
        assert await auth_service.is_setup_required(session) is True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/status")
        assert resp.status_code == 200
        assert resp.json()["setup_required"] is True

@pytest.mark.asyncio
async def test_login_blocked_and_redirects_when_setup_required(clean_user_table):
    """9. When setup is required: /dashboard redirects to /setup, and login attempts return 400."""
    orig_auth = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Check /dashboard redirects to /setup
            resp_dash = await client.get("/dashboard", follow_redirects=False)
            assert resp_dash.status_code in (302, 307)
            assert resp_dash.headers["location"] == "/setup"

            # Check POST /api/auth/login is rejected with 401 Unauthorized
            resp_login_post = await client.post("/api/auth/login", json={
                "username": "admin",
                "password": "AnyPassword123!"
            })
            assert resp_login_post.status_code == 401
            assert "Invalid username or password" in resp_login_post.json()["detail"]
    finally:
        settings.AUTH_ENABLED = orig_auth

@pytest.mark.asyncio
async def test_unauthenticated_dashboard_redirects_to_login_not_setup_when_configured(clean_user_table):
    """10. When setup is already completed, unauthenticated requests to /dashboard and / redirect to /login, NEVER to /setup."""
    orig_auth = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        # Setup admin
        valid_pw = "Perseus-Defense-Grid-2026!"
        async with AsyncSessionLocal() as session:
            await auth_service.complete_setup(session, "admin", valid_pw, valid_pw)
            assert await auth_service.is_setup_required(session) is False

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # /dashboard redirect check: MUST be /login, NOT /setup
            resp_dash = await client.get("/dashboard", follow_redirects=False)
            assert resp_dash.status_code in (302, 307)
            assert resp_dash.headers["location"] == "/login"

            # /app redirect check: MUST be /login
            resp_app = await client.get("/app", follow_redirects=False)
            assert resp_app.status_code in (302, 307)
            assert resp_app.headers["location"] == "/login"

            # / public website check: MUST be 200
            resp_root = await client.get("/", follow_redirects=False)
            assert resp_root.status_code == 200

            # /api/auth/status must show setup_required: false
            resp_status = await client.get("/api/auth/status")
            assert resp_status.status_code == 200
            data = resp_status.json()
            assert data["setup_required"] is False
            assert data["authenticated"] is False
            assert data["status"] == "READY"
    finally:
        settings.AUTH_ENABLED = orig_auth

@pytest.mark.asyncio
async def test_logout_preserves_setup_state(clean_user_table):
    """11. Logging out clears the session cookie and leaves setup_required = False."""
    orig_auth = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        valid_pw = "Starlight-Station-Passkey-8899!"
        async with AsyncSessionLocal() as session:
            await auth_service.complete_setup(session, "admin", valid_pw, valid_pw)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Login
            login_resp = await client.post("/api/auth/login", json={"username": "admin", "password": valid_pw})
            assert login_resp.status_code == 200
            assert "agency_session" in login_resp.cookies

            # Logout
            logout_resp = await client.post("/api/auth/logout")
            assert logout_resp.status_code == 200

            # Status must STILL report setup_required = False
            status_resp = await client.get("/api/auth/status")
            assert status_resp.status_code == 200
            data = status_resp.json()
            assert data["setup_required"] is False
            assert data["authenticated"] is False

            # Navigating to /dashboard must redirect to /login, NEVER /setup
            dash_resp = await client.get("/dashboard", follow_redirects=False)
            assert dash_resp.status_code in (302, 307)
            assert dash_resp.headers["location"] == "/login"
    finally:
        settings.AUTH_ENABLED = orig_auth

@pytest.mark.asyncio
async def test_server_restart_simulation_preserves_setup(clean_user_table):
    """12. Simulating a server restart retains setup_required = False across new sessions."""
    orig_auth = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        valid_pw = "Restart-Persistence-Master-Key-4411!"
        async with AsyncSessionLocal() as session:
            await auth_service.complete_setup(session, "admin", valid_pw, valid_pw)

        # Clear in-memory caches to simulate cold process start
        auth_service.clear_cache()

        # New session (simulating post-restart query)
        async with AsyncSessionLocal() as fresh_session:
            assert await auth_service.is_setup_required(fresh_session) is False

        # New client (simulating fresh browser/client post-restart)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as new_client:
            resp = await new_client.get("/api/auth/status")
            assert resp.status_code == 200
            assert resp.json()["setup_required"] is False
            assert resp.json()["status"] == "READY"
    finally:
        settings.AUTH_ENABLED = orig_auth

@pytest.mark.asyncio
async def test_auth_status_fails_closed_on_database_error():
    """13. When database query encounters an error, status returns 503 and NEVER claims setup_required=True."""
    from unittest.mock import patch

    with patch.object(auth_service, "is_setup_required", side_effect=RuntimeError("Simulated DB lock timeout")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/auth/status")
            assert resp.status_code == 503
            data = resp.json()
            assert data["setup_required"] is False
            assert data["status"] == "ERROR"

@pytest.mark.asyncio
async def test_concurrent_setup_race_condition_safety(clean_user_table):
    """14. Concurrent setup requests are safe: only one succeeds, subsequent is rejected."""
    pw = "Concurrent-Safety-Key-7788!"
    async with AsyncSessionLocal() as session:
        # First call succeeds
        user1 = await auth_service.complete_setup(session, "admin", pw, pw)
        assert user1 is not None

        # Immediate second call within same or concurrent transaction must fail
        with pytest.raises(ValueError, match="already been completed"):
            await auth_service.complete_setup(session, "admin", pw, pw)

