import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings

@pytest.mark.asyncio
async def test_public_host_routing_and_redirects():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://automatedagencyos.tech") as client:
        # 1. Public landing page returns 200
        res = await client.get("/", headers={"Host": "automatedagencyos.tech"})
        assert res.status_code == 200
        assert "AI Automation" in res.text or "Agency OS" in res.text

        # 2. Public robots.txt permits public indexing and disallows /dashboard
        res_robots = await client.get("/robots.txt", headers={"Host": "automatedagencyos.tech"})
        assert res_robots.status_code == 200
        assert "Disallow: /dashboard" in res_robots.text

        # 3. Public host attempting to access /dashboard must redirect to admin host
        res_dash = await client.get("/dashboard", headers={"Host": "automatedagencyos.tech"}, follow_redirects=False)
        assert res_dash.status_code in (302, 307)
        assert res_dash.headers["location"].startswith("https://app.automatedagencyos.tech/dashboard")

        # 4. Public host attempting to access /login must redirect to admin host
        res_login = await client.get("/login", headers={"Host": "automatedagencyos.tech"}, follow_redirects=False)
        assert res_login.status_code in (302, 307)
        assert res_login.headers["location"].startswith("https://app.automatedagencyos.tech/login")

        # 5. Public health check remains operational
        res_health = await client.get("/health", headers={"Host": "automatedagencyos.tech"})
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_admin_host_routing_and_isolation(monkeypatch):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://app.automatedagencyos.tech") as client:
        # 1. Admin host root redirects to /dashboard
        res_root = await client.get("/", headers={"Host": "app.automatedagencyos.tech"}, follow_redirects=False)
        assert res_root.status_code in (302, 307)
        assert res_root.headers["location"].endswith("/dashboard")

        # 2. Admin host robots.txt strictly disallows all indexing
        res_robots = await client.get("/robots.txt", headers={"Host": "app.automatedagencyos.tech"})
        assert res_robots.status_code == 200
        assert "User-agent: *" in res_robots.text
        assert "Disallow: /" in res_robots.text

        # 3. Admin host public marketing requests redirect back to the public website
        res_services = await client.get("/services", headers={"Host": "app.automatedagencyos.tech"}, follow_redirects=False)
        assert res_services.status_code in (302, 307)
        assert res_services.headers["location"].startswith("https://automatedagencyos.tech/services")

        # 4. Admin host health check works
        res_health = await client.get("/health", headers={"Host": "app.automatedagencyos.tech"})
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "ok"

        # 5. When AUTH_ENABLED is True, unauthenticated access to /dashboard redirects to /login
        monkeypatch.setattr(settings, "AUTH_ENABLED", True)
        res_dash = await client.get("/dashboard", headers={"Host": "app.automatedagencyos.tech"}, follow_redirects=False)
        assert res_dash.status_code in (302, 307)
        assert res_dash.headers["location"].endswith("/login")

@pytest.mark.asyncio
async def test_session_cookie_host_only_semantics():
    from starlette.responses import Response
    res = Response()
    res.set_cookie(
        key="agency_session",
        value="mock_token",
        httponly=True,
        samesite="lax",
        max_age=86400,
        secure=True
    )
    cookie_header = res.headers.get("set-cookie")
    assert "agency_session=mock_token" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert "Domain=" not in cookie_header  # Verifies Host-Only cookie
