import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app

@pytest.mark.asyncio
async def test_dashboard_template_rendering_and_elements():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        html = res.text

        # Verify page title and fonts
        assert "JARVIS Command Center" in html
        assert "Orbitron" in html
        assert "Rajdhani" in html
        assert "JetBrains" in html

        # Verify all 8 view containers exist
        expected_views = [
            "view-overview",
            "view-markets",
            "view-leads",
            "view-queue",
            "view-pipeline",
            "view-replies",
            "view-payments",
            "view-runs"
        ]
        for v in expected_views:
            assert f'id="{v}"' in html

        # Verify Live System / Agency Status HUD telemetry elements exist
        expected_hud_elems = [
            "worker-hud-status",
            "worker-hud-ticks",
            "worker-hud-last-tick",
            "hud-clock",
            "btn-run-cycle"
        ]
        for elem in expected_hud_elems:
            assert f'id="{elem}"' in html

        # Verify all KPI metric IDs exist
        expected_kpis = [
            "val-pipeline",
            "val-won",
            "val-leads",
            "val-qualified",
            "val-outreach-sent",
            "val-reply-rate"
        ]
        for kpi in expected_kpis:
            assert f'id="{kpi}"' in html

        # Verify mobile drawer and bottom navigation exist
        assert 'id="mobile-drawer"' in html
        assert 'class="mobile-bottom-nav"' in html
        assert 'id="lead-modal"' in html

@pytest.mark.asyncio
async def test_dashboard_css_stylesheet_and_responsive_breakpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/static/style.css")
        assert res.status_code == 200
        css = res.text

        # Verify design tokens and fonts
        assert "--hud-cyan:" in css
        assert "--hud-emerald:" in css
        assert "--hud-amber:" in css
        assert "--hud-crimson:" in css
        assert "Orbitron" in css
        assert "Rajdhani" in css

        # Verify responsive breakpoints for 1920px, 1440px, 1024px, 768px, and 390px
        assert "@media (max-width: 1440px)" in css
        assert "@media (max-width: 1024px)" in css
        assert "@media (max-width: 768px)" in css
        assert "@media (max-width: 480px)" in css

        # Verify modal active state exists
        assert ".modal-overlay.active" in css

@pytest.mark.asyncio
async def test_dashboard_js_client_and_handlers():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/static/app.js")
        assert res.status_code == 200
        js = res.text

        # Verify key UI controllers and event handlers
        assert "initHudClock" in js
        assert "loadDashboardMetrics" in js
        assert "switchView" in js
        assert "toggleMobileDrawer" in js
        assert "navToView" in js
        assert "viewLeadDetail" in js
        assert "viewAuditReport" in js
        assert "closeModal" in js
        assert "approveMessage" in js
        assert "rejectMessage" in js
        assert "createCheckoutLink" in js

@pytest.mark.asyncio
async def test_login_template_rendering():
    from app.core.config import settings
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/login")
            assert res.status_code == 200
            html = res.text
            assert "JARVIS // Operator Authorization" in html
            assert 'id="username"' in html
            assert 'id="password"' in html
            assert 'id="login-error"' in html
    finally:
        settings.AUTH_ENABLED = orig_auth

@pytest.mark.asyncio
async def test_settings_and_onboarding_ui_rendering():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        html = res.text

        # Verify Settings view and badges exist
        assert 'id="view-settings"' in html
        assert 'id="badge-email-status"' in html
        assert 'id="badge-payment-status"' in html
        assert 'id="email-settings-form"' in html
        assert 'id="payment-settings-form"' in html
        assert 'id="setting-live-email-toggle"' in html

        # Verify Commercial Proposal modal exists
        assert 'id="proposal-modal"' in html
        assert 'id="prop-total-value"' in html
        assert 'id="prop-advance-pct"' in html
        assert 'id="prop-calc-advance"' in html
        assert 'id="prop-calc-remaining"' in html
