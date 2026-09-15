import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app

@pytest.mark.asyncio
async def test_axion_landing_page_structure_and_content():
    """Validates that the public landing page strictly matches the Axion Studio editorial specification."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        html = res.text

        # 1. Full-screen Video Background & Atmosphere
        assert "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260809_012548_ef22562c-c0ae-4816-ad9d-f8922af4e6a7.mp4" in html
        assert 'class="bg-video"' in html
        assert 'id="heroAtmosphereGlow"' in html

        # 2. Pill Floating Navbar
        assert 'class="site-header-container"' in html
        assert 'class="site-header"' in html
        assert 'class="nav-pill"' in html
        assert 'class="brand-text">AGENCY OS' in html
        assert 'href="#services"' in html
        assert 'href="#who-we-help"' in html
        assert 'href="#process"' in html
        assert 'href="#about"' in html
        assert 'href="#contact"' in html
        assert 'href="/login"' in html

        # 3. Section 1 — Hero
        assert "Your agency," in html
        assert "running like a system." in html
        assert "From prospect discovery to delivery, Agency OS connects and automates the entire agency lifecycle" in html
        assert 'class="cta-pill-button"' in html
        assert 'class="cta-primary-text"' in html
        assert 'class="cta-secondary-text"' in html
        assert 'class="cta-arrow-circle"' in html
        assert "Continuous Autonomous Pipeline" in html

        # 4. Section 2 — 01 THE OPERATING SYSTEM
        assert "01" in html
        assert "THE OPERATING SYSTEM" in html
        assert "From prospect discovery to delivery,<br>Agency OS connects the workflow." in html or "From prospect discovery to delivery," in html
        # 10 Stages
        for stage in ["DISCOVERY", "RESEARCH", "AUDIT", "QUALIFICATION", "OUTREACH", "REPLY", "DEMO", "PROPOSAL", "PAYMENT", "DELIVERY"]:
            assert stage in html

        # 5. Section 3 — 02 THE SYSTEM
        assert "02" in html
        assert "THE SYSTEM" in html
        assert "One pipeline. One source of truth." in html
        assert "Lead &amp; Sales Automation" in html or "Lead & Sales Automation" in html
        assert "Customer Support Automation" in html
        assert "Workflow &amp; RPA" in html or "Workflow & RPA" in html
        assert "AUDIT_TELEMETRY // LIVE PROSPECT" in html
        assert "DISPATCH_CONTROLLER // SAFETY ACTIVE" in html
        assert "COMMERCIAL_PROGRESSION // STRIPE" in html

        # 6. Section 4 & 5 — Who We Help & About
        assert "Built for Businesses That Want to Automate" in html
        assert "Built on Engineering Integrity" in html
        assert "Reliability First" in html
        assert "Security &amp; Data Privacy" in html or "Security & Data Privacy" in html

        # 7. Section 6 — 03 CONSULTATION & DEPLOYMENT
        assert "03" in html
        assert "CONSULTATION &amp; DEPLOYMENT" in html or "CONSULTATION & DEPLOYMENT" in html
        assert "Project Consultation Channel" in html
        assert 'id="contactForm"' in html
        assert 'id="consultationModal"' in html
        assert 'id="privacyModal"' in html
        assert 'id="termsModal"' in html

@pytest.mark.asyncio
async def test_axion_landing_static_assets():
    """Validates that landing.css and landing.js are served with correct status and contain required interaction rules."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # CSS check
        css_res = await client.get("/static/landing.css")
        assert css_res.status_code == 200
        css = css_res.text
        assert ".cta-pill-button:hover .cta-arrow-circle" in css
        assert "rotate(-45deg)" in css
        assert "@media (prefers-reduced-motion: reduce)" in css
        assert "--mouse-shift-x" in css

        # JS check
        js_res = await client.get("/static/landing.js")
        assert js_res.status_code == 200
        js = js_res.text
        assert "heroAtmosphereGlow" in js
        assert "requestAnimationFrame" in js
        assert "prefers-reduced-motion" in js
        assert "visibilitychange" in js
