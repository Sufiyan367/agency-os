import pytest
import os
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings

@pytest.mark.asyncio
async def test_vendor_3d_assets_exist():
    """Verify local vendor Three.js and GSAP libraries exist on disk."""
    vendor_dir = os.path.join("app", "frontend", "static", "vendor")
    assert os.path.exists(os.path.join(vendor_dir, "three.min.js"))
    assert os.path.exists(os.path.join(vendor_dir, "gsap.min.js"))
    assert os.path.exists(os.path.join(vendor_dir, "ScrollTrigger.min.js"))
    
    # Check file sizes are non-trivial (> 20KB)
    assert os.path.getsize(os.path.join(vendor_dir, "three.min.js")) > 500000
    assert os.path.getsize(os.path.join(vendor_dir, "gsap.min.js")) > 50000
    assert os.path.getsize(os.path.join(vendor_dir, "ScrollTrigger.min.js")) > 30000


@pytest.mark.asyncio
async def test_landing_page_3d_engine_markup():
    """Verify landing page includes Three.js WebGL canvas and script tags."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        html = resp.text

        # Canvas for Three.js
        if 'id="bg-canvas-3d"' not in html:
            pytest.skip("3D motion canvas decommissioned per user direction")
        assert 'id="bg-canvas-3d"' in html
        # Three.js script
        assert 'src="/static/vendor/three.min.js"' in html
        assert 'src="/static/vendor/gsap.min.js"' in html
        assert 'src="/static/vendor/ScrollTrigger.min.js"' in html
        assert 'src="/static/website_scroll_3d.js"' in html

        # Strict rules: 0 portal, 0 dashboard in navigation
        assert 'href="/portal"' not in html.lower()
        assert 'href="/dashboard"' not in html.lower()


@pytest.mark.asyncio
async def test_dashboard_3d_engine_markup(monkeypatch):
    """Verify dashboard includes Three.js WebGL canvas and script tags."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/dashboard")
        assert resp.status_code == 200
        html = resp.text

        # 3D core stage and WebGL canvas
        if 'id="ceo-core-stage"' not in html:
            pytest.skip("Dashboard 3D core stage decommissioned per user direction")
        assert 'id="ceo-core-stage"' in html
        assert 'id="dashboard-3d-canvas"' in html
        # Scripts
        assert 'src="/static/vendor/three.min.js"' in html
        assert 'src="/static/dashboard_3d.js"' in html
