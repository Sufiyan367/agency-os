import pytest
import re
from httpx import AsyncClient, ASGITransport
from app.api.app import app


@pytest.mark.asyncio
async def test_public_landing_page_renders_200():
    """Verify the root landing page / returns 200 OK."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_public_landing_navigation_and_auth():
    """Verify header navigation contains specified links, Sign in, and CEO dashboard controls are absent."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        html = response.text
        
        # Ensure internal CEO dashboard controls are strictly absent
        assert "CEO Command Center" not in html
        assert "Kill Switch" not in html
        assert "portal-link" not in html
        
        # Ensure header navigation strictly contains specified links:
        # Home, Product, Case Studies, Contact, Sign in
        assert ">Home<" in html
        assert ">Product<" in html
        assert ">Case Studies<" in html
        assert ">Contact<" in html
        assert "Sign in" in html
        assert "/login" in html


@pytest.mark.asyncio
async def test_public_landing_no_raw_svg_text():
    """Verify no raw literal text 'svg' appears as visible text content."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        html = response.text

        # Search for >svg< or > svg < which indicates raw text between tags
        raw_svg_matches = re.findall(r'>\s*svg\s*<', html, re.IGNORECASE)
        assert len(raw_svg_matches) == 0, f"Found raw svg text tags: {raw_svg_matches}"


@pytest.mark.asyncio
async def test_public_landing_required_sections():
    """Verify single-viewport cinematic layout: header, hero, stats, and background video."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        html = response.text

        # Full-Bleed Video Background
        exact_url = "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260809_012548_ef22562c-c0ae-4816-ad9d-f8922af4e6a7.mp4"
        assert exact_url in html
        assert 'class="bg-video"' in html

        # Hero
        assert "Trusted by 2000+ Enterprises" in html
        assert "Intelligence" in html
        assert "Designed To Evolve" in html
        assert "Build applications that reason, adapt and collaborate" in html
        assert "Get Started" in html

        # Stats
        assert "Inference Time" in html
        assert "Platform Uptime" in html
        assert "Autonomous Runtime" in html
        assert "Context Windows" in html

        # Zero 3D canvas / orbit leftovers
        assert "bg-canvas-3d" not in html
        assert "spatial-grid-mesh" not in html
        assert "three.min.js" not in html


@pytest.mark.asyncio
async def test_public_landing_seo_and_schema():
    """Verify canonical, meta tags, and structured JSON-LD."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        html = response.text

        assert '<link rel="canonical" href="https://automatedagencyos.tech/">' in html
        assert 'name="description"' in html
        assert 'property="og:title"' in html
        assert 'application/ld+json' in html
        assert '"name": "Agency OS"' in html


@pytest.mark.asyncio
async def test_dashboard_remains_protected(monkeypatch):
    """Verify /dashboard is unaffected and strictly protected from unauthenticated public visitors when AUTH_ENABLED is active."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "DASHBOARD_PASSWORD", "testpass")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/dashboard", follow_redirects=False)
        # Either redirect to login (302/303/307) or 401/403
        assert response.status_code in [302, 303, 307, 401, 403]
