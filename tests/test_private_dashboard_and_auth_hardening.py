import pytest
import time
import hmac
import hashlib
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport

from app.api.app import app
from app.core.config import settings
from app.core.security import create_session_token, rate_limiter, webhook_replay_guard
from app.api.routes import agent_activity_websocket


@pytest.fixture(autouse=True)
async def reset_guards():
    await rate_limiter.reset()
    await webhook_replay_guard.reset()
    yield
    await rate_limiter.reset()
    await webhook_replay_guard.reset()


@pytest.mark.asyncio
async def test_anonymous_access_rejected_to_all_sensitive_endpoints():
    """Verifies that when AUTH_ENABLED=True, all sensitive endpoints return 401 or redirect to /login."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Dashboard redirects anonymous browser
            dash_resp = await client.get("/dashboard", follow_redirects=False)
            assert dash_resp.status_code in (302, 307)
            assert dash_resp.headers["location"] == "/login"

            # Sensitive API routes return 401
            sensitive_endpoints = [
                "/api/leads",
                "/api/agent/status",
                "/api/agent/activity",
                "/api/agent/safety-guardrails",
                "/api/agent/prospect-memory/1",
                "/api/agent/outreach/1",
                "/api/agent/audit-evidence/1",
                "/api/artifacts",
                "/api/artifacts/1/preview",
                "/api/deals",
                "/api/voice/calls",
                "/api/voice/appointments",
                "/api/followups/due",
                "/api/prospecting/status",
            ]
            for ep in sensitive_endpoints:
                r = await client.get(ep)
                assert r.status_code == 401, f"Expected 401 for anonymous access to {ep}, got {r.status_code}"
                assert "Authentication required" in r.json().get("detail", "")
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_authenticated_dashboard_and_api_access_succeeds():
    """Verifies valid session cookie or Bearer token grants access to authenticated endpoints."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        admin_token = create_session_token("admin", role="admin")
        cookies = {"agency_session": admin_token}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Cookie Auth on Dashboard
            dash = await client.get("/dashboard", cookies=cookies)
            assert dash.status_code == 200
            assert "Agency" in dash.text

            # 2. Cookie Auth on API
            leads_resp = await client.get("/api/leads", cookies=cookies)
            assert leads_resp.status_code == 200

            # 3. Bearer Header Auth on API
            headers = {"Authorization": f"Bearer {admin_token}"}
            status_resp = await client.get("/api/agent/status", headers=headers)
            assert status_resp.status_code == 200
            assert "status" in status_resp.json()
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_admin_only_operations_reject_viewer():
    """Verifies viewers cannot execute agent start/stop/kill, deal mutations, or backups."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        viewer_token = create_session_token("test_viewer", role="viewer")
        cookies = {"agency_session": viewer_token}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            privileged_calls = [
                ("POST", "/api/agent/start"),
                ("POST", "/api/agent/stop"),
                ("POST", "/api/agent/pause"),
                ("POST", "/api/agent/kill"),
                ("POST", "/api/agent/step"),
                ("POST", "/api/agent/build-website/1"),
                ("POST", "/api/deals/create"),
                ("POST", "/api/system/backup"),
            ]
            for method, endpoint in privileged_calls:
                r = await client.request(method, endpoint, cookies=cookies)
                assert r.status_code == 403, f"Expected 403 for viewer on {endpoint}, got {r.status_code}"
                assert "Privileged access required" in r.json().get("detail", "")
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_tampered_and_forged_tokens_rejected():
    """Verifies HMAC validation rejects tampered roles, signatures, or malformed tokens."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        # Create valid viewer token, then tamper role to 'admin'
        valid_viewer = create_session_token("test_viewer", role="viewer")
        parts = valid_viewer.split(".")
        # parts: [username, role, expires_at, sig]
        tampered_token = f"{parts[0]}.admin.{parts[2]}.{parts[3]}"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Tampered role token rejected with 401
            r1 = await client.get("/api/leads", cookies={"agency_session": tampered_token})
            assert r1.status_code == 401

            # 2. Forged random signature rejected with 401
            forged_token = f"admin.admin.{int(time.time())+86400}.deadbeef12345678"
            r2 = await client.get("/api/leads", cookies={"agency_session": forged_token})
            assert r2.status_code == 401

            # 3. Garbage token rejected with 401
            r3 = await client.get("/api/leads", cookies={"agency_session": "not-a-token"})
            assert r3.status_code == 401
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_expired_session_token_rejected():
    """Verifies that an expired session token is strictly rejected."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        # Token expired 1 hour ago
        expired_time = int(time.time()) - 3600
        data = f"admin:admin:{expired_time}"
        sig = hmac.new(settings.SESSION_SECRET.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
        expired_token = f"admin.admin.{expired_time}.{sig}"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/leads", cookies={"agency_session": expired_token})
            assert r.status_code == 401
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_path_normalization_prevents_auth_bypass():
    """Verifies double-slash, dot-segments, or query manipulation cannot bypass auth."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            bypass_attempts = [
                "//api//leads",
                "/api/../api/leads",
                "/api/leads?token=none",
                "/api/leads?bypass=true",
                "/api/agent/status?admin=1"
            ]
            for attempt in bypass_attempts:
                r = await client.get(attempt, follow_redirects=False)
                # Unauthenticated requests must either be rejected with 401 or redirected to /login
                if r.status_code in (302, 307):
                    assert r.headers.get("location") == "/login"
                else:
                    assert r.status_code == 401
                # Sensitive data (e.g. database leads) must NEVER be exposed
                assert "email_status" not in r.text and "public_email" not in r.text
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_websocket_authentication_full_matrix():
    """Verifies WebSocket /ws/agent-activity accepts authenticated and rejects unauthenticated/tampered connections."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True

        # 1. Unauthenticated -> Close code 1008
        mock_ws_anon = AsyncMock()
        mock_ws_anon.cookies = {}
        mock_ws_anon.headers = {}
        await agent_activity_websocket(mock_ws_anon, token=None)
        assert mock_ws_anon.close.called
        assert mock_ws_anon.close.call_args[1].get("code") == 1008

        # 2. Tampered token -> Close code 1008
        mock_ws_tampered = AsyncMock()
        mock_ws_tampered.cookies = {}
        mock_ws_tampered.headers = {}
        await agent_activity_websocket(mock_ws_tampered, token="admin.admin.12345.invalidsig")
        assert mock_ws_tampered.close.called
        assert mock_ws_tampered.close.call_args[1].get("code") == 1008

        # 3. Authenticated via Cookie -> Accepted
        mock_ws_cookie = AsyncMock()
        valid_token = create_session_token("admin", role="admin")
        mock_ws_cookie.cookies = {"agency_session": valid_token}
        mock_ws_cookie.headers = {}
        mock_ws_cookie.receive_text.side_effect = ["ping", Exception("disconnect")]
        try:
            await agent_activity_websocket(mock_ws_cookie, token=None)
        except Exception:
            pass
        assert mock_ws_cookie.accept.called

        # 4. Authenticated via Query Param -> Accepted
        mock_ws_query = AsyncMock()
        mock_ws_query.cookies = {}
        mock_ws_query.headers = {}
        mock_ws_query.receive_text.side_effect = ["ping", Exception("disconnect")]
        try:
            await agent_activity_websocket(mock_ws_query, token=valid_token)
        except Exception:
            pass
        assert mock_ws_query.accept.called
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_health_reports_auth_enabled_status():
    """Verifies /health accurately reports auth_enabled: true when enabled."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/health")
            assert r.status_code == 200
            data = r.json()
            assert data.get("auth_enabled") is True
            assert data.get("status") == "ok"
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_pbkdf2_hashed_password_login_verification():
    """Verifies that login succeeds against PBKDF2-hashed credentials and rejects bad passwords."""
    from app.core.security import hash_password
    orig_user = settings.DASHBOARD_USERNAME
    orig_pass = settings.DASHBOARD_PASSWORD
    orig_auth = settings.AUTH_ENABLED
    try:
        raw_password = "SuperSecret_Admin_Pass_2026!"
        settings.DASHBOARD_USERNAME = "admin"
        settings.DASHBOARD_PASSWORD = hash_password(raw_password)
        settings.AUTH_ENABLED = True

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Bad password fails
            bad_resp = await client.post("/api/auth/login", json={"username": "admin", "password": "WrongPassword!"})
            assert bad_resp.status_code == 401

            # Correct password succeeds and sets agency_session cookie
            ok_resp = await client.post("/api/auth/login", json={"username": "admin", "password": raw_password})
            assert ok_resp.status_code == 200
            assert "agency_session" in ok_resp.cookies
            assert ok_resp.json().get("role") == "admin"
    finally:
        settings.DASHBOARD_USERNAME = orig_user
        settings.DASHBOARD_PASSWORD = orig_pass
        settings.AUTH_ENABLED = orig_auth

