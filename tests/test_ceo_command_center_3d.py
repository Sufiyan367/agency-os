import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings

@pytest.mark.asyncio
async def test_dashboard_3d_static_assets_serving():
    """Verify dashboard_3d.css and dashboard_3d.js are properly served with full 3D specifications."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test CSS
        r_css = await client.get("/static/dashboard_3d.css")
        assert r_css.status_code == 200
        css = r_css.text
        assert "--sidebar-width: 240px" in css
        assert "--perspective: 1200px" in css
        assert ".ceo-command-hero" in css
        assert ".ceo-core-stage" in css
        assert ".agency-os-3d-core" in css
        assert ".core-center-nucleus" in css
        assert ".core-ring-1" in css
        assert ".core-ring-2" in css
        assert ".agency-kpi-block" in css
        assert "@media (prefers-reduced-motion: reduce)" in css
        assert "@media (max-width: 768px)" in css

        # Test JS
        r_js = await client.get("/static/dashboard_3d.js")
        assert r_js.status_code == 200
        js = r_js.text
        assert "initCeoGreeting" in js
        assert "initPerspectiveCardTilts" in js
        assert "initCoreEventBridge" in js

@pytest.mark.asyncio
async def test_ceo_command_center_rendering_and_elements(monkeypatch):
    """Verify /dashboard renders the 3D Command Center with the 5 navigation groups and 3D hero."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/dashboard")
        assert r.status_code == 200
        html = r.text

        # Verify stylesheet and script integration
        assert 'href="/static/dashboard_3d.css"' in html
        assert 'src="/static/dashboard_3d.js"' in html

        # Verify 5 Canonical Navigation Groups
        assert "COMMAND" in html
        assert "GROWTH" in html
        assert "DELIVERY" in html
        assert "INTELLIGENCE" in html
        assert "SYSTEM" in html

        # Verify 3D Hero and Autonomous Core elements
        assert 'class="ceo-command-hero"' in html
        assert 'id="ceo-dynamic-greeting"' in html
        assert 'class="ceo-core-stage"' in html
        assert 'class="agency-os-3d-core"' in html
        assert 'class="core-center-nucleus"' in html
        assert 'class="core-ring core-ring-1"' in html
        assert 'class="core-ring core-ring-2"' in html
        assert 'class="core-domain-node node-acq"' in html

        # Verify all 8 core views are preserved
        expected_views = [
            "view-overview",
            "view-markets",
            "view-leads",
            "view-queue",
            "view-pipeline",
            "view-replies",
            "view-payments",
            "view-runs",
            "view-settings"
        ]
        for v in expected_views:
            assert f'id="{v}"' in html, f"Missing view: {v}"

        # Verify Live Telemetry & HUD elements
        expected_hud = [
            "worker-hud-status",
            "worker-hud-ticks",
            "worker-hud-last-tick",
            "hud-clock",
            "btn-run-cycle"
        ]
        for h in expected_hud:
            assert f'id="{h}"' in html, f"Missing HUD element: {h}"

        # Verify KPI Metric Value IDs for app.js population
        expected_kpis = [
            "val-pipeline",
            "val-won",
            "val-leads",
            "val-qualified",
            "val-outreach-sent",
            "val-reply-rate"
        ]
        for k in expected_kpis:
            assert f'id="{k}"' in html, f"Missing KPI ID: {k}"

@pytest.mark.asyncio
async def test_unauthenticated_dashboard_access_denied(monkeypatch):
    """Verify that unauthenticated access to /dashboard is strictly blocked when auth is enabled."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        r = await client.get("/dashboard")
        assert r.status_code in (302, 307)
        assert r.headers.get("location") in ("/login", "/setup")
