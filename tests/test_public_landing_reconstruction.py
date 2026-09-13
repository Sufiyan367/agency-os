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
async def test_public_landing_no_portal_link():
    """Verify 'Portal', 'Dashboard', 'Control Center', 'Login' are strictly absent from public page."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        html = response.text.lower()
        
        # Absolute Rule: ZERO mentions of portal, dashboard, control center, login
        assert "portal" not in html
        assert "dashboard" not in html
        assert "control center" not in html
        assert "login" not in html
        assert 'class="btn-portal-link"' not in html
        
        # Ensure header navigation strictly contains expected labels:
        # OSAI, Solutions, How It Works, Services, Industries, Contact, Book a Strategy Call
        assert "osai" in html
        assert ">solutions<" in html
        assert ">how it works<" in html
        assert ">services<" in html
        assert ">industries<" in html
        assert ">contact<" in html
        assert "book a strategy call" in html


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
    """Verify all 6 core sections and 3D canvas exist in DOM."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        html = response.text

        # Canvas
        assert 'id="bg-canvas-3d"' in html
        # Hero
        assert 'id="hero"' in html
        assert 'id="hero-core-widget"' in html
        # Solutions / Delivery Journey
        assert 'id="how-it-works"' in html
        assert 'id="solutions"' in html
        assert '01 // AUDIT' in html
        assert '02 // DESIGN' in html
        assert '03 // BUILD' in html
        assert '04 // TEST' in html
        assert '05 // DEPLOY' in html
        assert '06 // IMPROVE' in html
        # Interactive Simulator
        assert 'id="interactive-demo"' in html
        assert 'data-sim="missed_call"' in html
        assert 'data-sim="web_enquiry"' in html
        assert 'data-sim="lead_form"' in html
        assert 'data-sim="support_request"' in html
        # Services (6 cards)
        assert 'id="services"' in html
        assert 'service-card' in html
        assert html.count('class="service-card"') == 6
        # Industries (6 cards)
        assert 'id="industries"' in html
        assert 'industry-card' in html
        assert html.count('class="industry-card"') == 6
        # Contact Form
        assert 'id="contact"' in html
        assert 'id="contactForm"' in html
        # Consultation Modal
        assert 'id="consultationModal"' in html
        assert 'id="modalForm"' in html


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
        assert '"@type": "Organization"' in html


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
