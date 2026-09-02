import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings
from app.core.security import (
    create_session_token,
    verify_session_token,
    verify_login_credentials,
    verify_api_key
)

def test_session_token_lifecycle():
    token = create_session_token("admin_test", expires_in_days=1)
    assert token is not None
    assert "admin_test" in token

    # Verify valid token
    verified_user = verify_session_token(token)
    assert verified_user == "admin_test"

    # Verify tampered token fails
    tampered = token[:-4] + "dead"
    assert verify_session_token(tampered) is None

    # Verify malformed token fails
    assert verify_session_token("not.a.valid.token") is None
    assert verify_session_token("") is None

def test_credential_verification():
    valid = verify_login_credentials(settings.DASHBOARD_USERNAME, settings.DASHBOARD_PASSWORD)
    assert valid is True

    invalid_user = verify_login_credentials("wrong_user", settings.DASHBOARD_PASSWORD)
    assert invalid_user is False

    invalid_pass = verify_login_credentials(settings.DASHBOARD_USERNAME, "wrong_password")
    assert invalid_pass is False

def test_api_key_verification():
    assert verify_api_key(settings.API_SECRET_KEY) is True
    assert verify_api_key("fake_key") is False
    assert verify_api_key("") is False

@pytest.mark.asyncio
async def test_auth_login_and_logout_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Invalid login attempt
        bad_res = await ac.post("/api/auth/login", json={"username": "bad", "password": "bad"})
        assert bad_res.status_code == 401

        # 2. Valid login attempt
        good_res = await ac.post("/api/auth/login", json={
            "username": settings.DASHBOARD_USERNAME,
            "password": settings.DASHBOARD_PASSWORD
        })
        assert good_res.status_code == 200
        data = good_res.json()
        assert data["status"] == "SUCCESS"
        assert "agency_session" in good_res.cookies

        # 3. Check auth me with session cookie
        me_res = await ac.get("/api/auth/me", cookies=good_res.cookies)
        assert me_res.status_code == 200
        assert me_res.json()["authenticated"] is True

        # 4. Logout
        logout_res = await ac.post("/api/auth/logout")
        assert logout_res.status_code == 200

@pytest.mark.asyncio
async def test_public_health_endpoints_accessible():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        health_res = await ac.get("/api/health")
        assert health_res.status_code == 200
        data = health_res.json()
        assert data["status"] in ("ok", "degraded")
        assert data["cloud_mode"] is True
        assert "worker" in data
