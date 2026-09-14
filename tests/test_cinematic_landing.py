import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings

@pytest.mark.asyncio
async def test_cinematic_landing_page_rendering():
    """Verify GET / renders public cinematic video landing page with exact specification."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        html = r.text

        # 1. Exact Title
        assert "<title>Intelligence Designed To Evolve</title>" in html

        # 2. Exact Video URL
        exact_url = "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260809_012548_ef22562c-c0ae-4816-ad9d-f8922af4e6a7.mp4"
        assert exact_url in html
        assert 'class="bg-video"' in html
        assert "autoplay" in html
        assert "muted" in html
        assert "loop" in html
        assert "playsinline" in html

        # 3. Logo
        assert 'src="assets/logo.webp"' in html

        # 4. Fonts and Styles
        assert "BubbledotICG-FinePos" in html
        assert "Inter" in html
        assert "font-awesome" in html
        assert '/static/landing.css' in html
        assert 'src="/static/landing.js"' in html

        # 5. Zero references to old 3D/orbit visual language
        assert "website_3d.css" not in html
        assert "website_scroll_3d.js" not in html
        assert "three.min.js" not in html
        assert "bg-canvas-3d" not in html
        assert "spatial-grid-mesh" not in html

        # 6. Trust Row
        assert "Trusted by 2000+ Enterprises" in html
        assert "fa-microsoft" in html
        assert "fa-amazon" in html
        assert "fa-google" in html

        # 7. Headline
        assert "<span>Intelligence</span>" in html
        assert "<span>Designed To Evolve</span>" in html

        # 8. Subhead
        assert "Build applications that reason, adapt and collaborate using a modular AI platform designed for production." in html

        # 9. CTA
        assert "Get Started" in html

        # 10. 4 Product/UI Positioning Stats
        assert "Inference Time" in html
        assert 'data-target="120"' in html
        assert "ms" in html

        assert "Platform Uptime" in html
        assert 'data-target="99.99"' in html

        assert "Autonomous Runtime" in html
        assert 'data-target="24"' in html
        assert "/7" in html

        assert "Context Windows" in html
        assert 'data-target="2.4"' in html
        assert "M" in html

        # 11. Security headers
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"

@pytest.mark.asyncio
async def test_static_assets_serving():
    """Verify landing.css, landing.js, logo.webp, and GeistPixel font are served."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_css = await client.get("/static/landing.css")
        assert r_css.status_code == 200
        assert "--font-display" in r_css.text

        r_js = await client.get("/static/landing.js")
        assert r_js.status_code == 200
        assert "easeOutCubic" in r_js.text

        r_logo = await client.get("/assets/logo.webp")
        assert r_logo.status_code == 200
        assert len(r_logo.content) > 0

        r_font = await client.get("/static/fonts/GeistPixel-Circle.woff2")
        assert r_font.status_code == 200
        assert len(r_font.content) > 0

@pytest.mark.asyncio
async def test_unaffected_critical_routes(monkeypatch):
    """Verify /health, /dashboard, and /demo/* remain completely functional and untouched."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        # 1. Health
        r_health = await client.get("/health")
        assert r_health.status_code == 200

        # 2. Dashboard auth protection preserved
        r_dash = await client.get("/dashboard")
        assert r_dash.status_code in (302, 307)

        # 3. Demo factory route is public (not redirected to /login)
        r_demo = await client.get("/demo/orange-auto")
        assert r_demo.status_code in (200, 404)
        assert r_demo.status_code not in (302, 307)
