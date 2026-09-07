import os
import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings
from app.core.security import create_session_token

@pytest.mark.asyncio
async def test_backend_health_endpoints():
    """Verifies that /health and /api/health are accessible without auth and return expected health structure."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for path in ("/health", "/api/health"):
                res = await client.get(path)
                assert res.status_code == 200
                data = res.json()
                assert data["status"] in ("ok", "degraded")
                assert "database" in data
                assert "worker" in data
                assert "service" in data
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_public_website_portal_entrypoint():
    """Verifies that the public website provides a clear Portal navigation entrypoint to /dashboard."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        html = res.text
        # Portal button to /dashboard
        assert 'href="/dashboard"' in html
        assert 'btn-portal-dashboard' in html
        # Preserves existing primary call to actions
        assert 'href="#services"' in html
        assert 'Explore Services' in html


@pytest.mark.asyncio
async def test_ceo_dashboard_browser_access_and_auth_redirection():
    """Verifies unauthenticated redirection to /login and authenticated access to /dashboard with health indicators."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Unauthenticated CEO access redirects to /login
            res_unauth = await client.get("/dashboard", follow_redirects=False)
            assert res_unauth.status_code in (302, 307)
            assert res_unauth.headers["location"] == "/login"

            # 2. Authenticated CEO access returns 200 with Control Center & Health UI elements
            token = create_session_token("admin", role="admin")
            cookies = {"agency_session": token}
            res_auth = await client.get("/dashboard", cookies=cookies)
            assert res_auth.status_code == 200
            html = res_auth.text

            # Live backend reachability elements in topbar & safeguards grid
            assert 'id="ceo-backend-health-pill"' in html
            assert 'id="ceo-backend-health-dot"' in html
            assert 'id="ceo-backend-health-text"' in html
            assert 'CONNECTED' in html
            assert 'retryCeoConnection()' in html
            assert 'id="ceo-sys-backend"' in html

            # Existing safeguard and telemetry elements remain intact
            assert 'id="ceo-sys-inbox"' in html
            assert 'id="ceo-sys-email"' in html
            assert 'id="ceo-sys-payment"' in html
            assert 'id="ceo-sys-worker"' in html
            assert 'id="ceo-sys-last-activity"' in html
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_ceo_overview_api_auth_and_response():
    """Verifies that /api/ceo/overview requires authentication and returns valid payload when authenticated."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Unauthenticated request to /api/ceo/overview is unauthorized/redirected
            res_unauth = await client.get("/api/ceo/overview", follow_redirects=False)
            assert res_unauth.status_code in (401, 302, 307)

            # 2. Authenticated request succeeds with 200 and executive payload
            token = create_session_token("admin", role="admin")
            cookies = {"agency_session": token}
            res_auth = await client.get("/api/ceo/overview", cookies=cookies)
            assert res_auth.status_code == 200
            data = res_auth.json()
            assert "executive_metrics" in data
            assert "system_status" in data
            assert data["system_status"]["email_mode"] == "DRY RUN"
            assert data["system_status"]["payment_mode"] == "DISABLED"
    finally:
        settings.AUTH_ENABLED = orig_auth


def test_frontend_scripts_contain_health_and_reconnect_handlers():
    """Verifies that app.js contains retryCeoConnection and setBackendHealthUI definitions."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app_js_path = os.path.join(base_dir, "app", "frontend", "static", "app.js")
    assert os.path.isfile(app_js_path)
    with open(app_js_path, "r", encoding="utf-8", errors="ignore") as f:
        js_content = f.read()
    assert "async function retryCeoConnection" in js_content
    assert "function setBackendHealthUI" in js_content
    assert "function checkBackendHealth" in js_content



def test_ceo_launcher_files_exist_and_configured():
    """Verifies that one-click desktop launchers and deployment documentation exist with proper commands."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # 1. Launch_Agency_OS.bat
    bat_path = os.path.join(base_dir, "Launch_Agency_OS.bat")
    assert os.path.isfile(bat_path), "Launch_Agency_OS.bat must exist at repo root"
    with open(bat_path, "r", encoding="utf-8", errors="ignore") as f:
        bat_content = f.read()
    assert "http://127.0.0.1:8000/health" in bat_content
    assert "http://localhost:8000/dashboard" in bat_content
    assert "app.cli serve" in bat_content

    # 2. Launch_Agency_OS.vbs
    vbs_path = os.path.join(base_dir, "Launch_Agency_OS.vbs")
    assert os.path.isfile(vbs_path), "Launch_Agency_OS.vbs must exist at repo root"
    with open(vbs_path, "r", encoding="utf-8", errors="ignore") as f:
        vbs_content = f.read()
    assert "Launch_Agency_OS.bat" in vbs_content

    # 3. Deployment documentation
    doc_path = os.path.join(base_dir, "docs", "DEPLOYMENT_AND_BROWSER_ACCESS.md")
    assert os.path.isfile(doc_path), "DEPLOYMENT_AND_BROWSER_ACCESS.md must exist in docs"
    with open(doc_path, "r", encoding="utf-8", errors="ignore") as f:
        doc_content = f.read()
    assert "agency-os-n6yx" in doc_content
    assert "Vercel" in doc_content
