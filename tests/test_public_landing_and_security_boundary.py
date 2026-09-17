import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings

@pytest.mark.asyncio
async def test_public_landing_page_rendering():
    """Verify GET / renders public cinematic landing page and no internal controls."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "Agency OS" in r.text
        # Ensure CEO dashboard internal controls are not exposed
        assert "CEO Command Center" not in r.text
        assert "Kill Switch" not in r.text

@pytest.mark.asyncio
async def test_public_informational_pages():
    """Verify GET /about, /services, /contact render properly."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/about", "/services", "/contact"):
            r = await client.get(path)
            assert r.status_code == 200
            assert "Agency OS" in r.text

@pytest.mark.asyncio
async def test_public_legal_pages():
    """Verify GET /privacy and /terms render properly."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_priv = await client.get("/privacy")
        assert r_priv.status_code == 200
        assert "Privacy Policy" in r_priv.text

        r_terms = await client.get("/terms")
        assert r_terms.status_code == 200
        assert "Terms of Service" in r_terms.text

@pytest.mark.asyncio
async def test_robots_txt_directive():
    """Verify GET /robots.txt provides crawler directives and disallows private routes."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/robots.txt")
        assert r.status_code == 200
        assert "User-agent" in r.text
        assert "Disallow: /dashboard" in r.text
        assert "Disallow: /api/" in r.text

@pytest.mark.asyncio
async def test_sitemap_xml():
    """Verify GET /sitemap.xml is valid XML and lists public marketing URLs."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/sitemap.xml")
        assert r.status_code == 200
        assert "<urlset" in r.text
        assert "https://automatedagencyos.tech/" in r.text
        assert "https://automatedagencyos.tech/privacy" in r.text
        assert "https://automatedagencyos.tech/terms" in r.text

@pytest.mark.asyncio
async def test_static_assets_serving():
    """Verify landing.css and landing.js are served statically."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_css = await client.get("/static/landing.css")
        assert r_css.status_code == 200
        assert "--font-display" in r_css.text

        r_js = await client.get("/static/landing.js")
        assert r_js.status_code == 200
        assert len(r_js.text) > 0

@pytest.mark.asyncio
async def test_unauthenticated_dashboard_redirect(monkeypatch):
    """Verify unauthenticated GET /dashboard and /app redirect to /login."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        r1 = await client.get("/dashboard")
        assert r1.status_code in (302, 307)
        assert r1.headers.get("location") in ("/login", "/setup")

        r2 = await client.get("/app")
        assert r2.status_code in (302, 307)
        assert r2.headers.get("location") in ("/login", "/setup")

@pytest.mark.asyncio
async def test_unauthenticated_client_portal_redirect(monkeypatch):
    """Verify unauthenticated GET /client redirects to /login."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        r = await client.get("/client")
        assert r.status_code in (302, 307)
        assert r.headers.get("location") == "/login"

@pytest.mark.asyncio
async def test_unauthenticated_api_rejection(monkeypatch):
    """Verify unauthenticated calls to operational APIs return 401 JSON."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/deals", headers={"Accept": "application/json"})
        assert r.status_code == 401
        data = r.json()
        assert "detail" in data

@pytest.mark.asyncio
async def test_unauthenticated_privileged_mutation_rejection(monkeypatch):
    """Verify unauthenticated calls to privileged mutation endpoints return 401."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/deals/create", json={"name": "test"}, headers={"Accept": "application/json"})
        assert r.status_code == 401

@pytest.mark.asyncio
async def test_public_contact_submission_success():
    """Verify POST /api/contact succeeds with valid payload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "Jane Enterprise",
            "email": "jane@enterprise.com",
            "company": "Enterprise Corp",
            "service_interest": "Autonomous Systems Audit",
            "message": "Testing public audit request pipeline."
        }
        r = await client.post("/api/contact", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True
        assert "message" in data

@pytest.mark.asyncio
async def test_public_contact_submission_validation():
    """Verify POST /api/contact validates required name and email."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test empty required fields
        payload = {
            "name": "",
            "email": "",
            "company": "Example",
            "service_interest": "Audit",
            "message": "Hello"
        }
        r = await client.post("/api/contact", json=payload)
        assert r.status_code == 400
        assert "detail" in r.json()

        # Test malformed / missing payload schema returns 400 or 422
        r_empty = await client.post("/api/contact", json={})
        assert r_empty.status_code in (400, 422)


@pytest.mark.asyncio
async def test_static_and_sensitive_file_protection():
    """Verify requests to sensitive file extensions (.env, .db, .sqlite, .py) return 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for forbidden in ("/.env", "/database.sqlite", "/app/api/app.py", "/backup.sql", "/app.log"):
            r = await client.get(forbidden)
            assert r.status_code == 404

@pytest.mark.asyncio
async def test_custom_404_handler():
    """Verify 404 returns custom HTML for browser and JSON for API requests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Browser request
        r_html = await client.get("/non-existent-page-xyz", headers={"Accept": "text/html"})
        assert r_html.status_code == 404
        assert "System Coordinates Not Found" in r_html.text or "404" in r_html.text

        # API request
        r_api = await client.get("/api/non-existent-endpoint-xyz", headers={"Accept": "application/json"})
        assert r_api.status_code == 404
        assert r_api.headers.get("content-type", "").startswith("application/json")
