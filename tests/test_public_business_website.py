import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings
from app.core.security import create_session_token, rate_limiter

@pytest.mark.asyncio
async def test_public_website_anonymous_access_and_seo_metadata():
    """Verifies that the public website is accessible to anonymous visitors even when AUTH_ENABLED=True."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Root route / serves public website
            res_root = await client.get("/", follow_redirects=False)
            assert res_root.status_code == 200
            html = res_root.text

            # Verify title and meta
            assert "<title>Agency OS — AI Automation &amp; Digital Solutions</title>" in html or "Agency OS — AI Automation & Digital Solutions" in html
            assert 'name="description"' in html
            assert 'property="og:title"' in html
            assert 'property="og:description"' in html
            assert 'name="viewport"' in html
            assert 'name="theme-color"' in html

            # Verify security headers
            assert res_root.headers.get("x-content-type-options") == "nosniff"
            assert res_root.headers.get("x-frame-options") == "DENY"
            assert res_root.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

            # 2. /website route also serves public website
            res_website = await client.get("/website", follow_redirects=False)
            assert res_website.status_code == 200
            assert "AI Automation for Modern Businesses" in res_website.text
    finally:
        settings.AUTH_ENABLED = orig_auth


@pytest.mark.asyncio
async def test_public_website_content_structure_and_authenticity():
    """Verifies all required genuine sections, cards, capabilities, and absence of fake marketing claims."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        html = res.text

        # 1. Header & Navigation
        assert "AGENCY OS" in html
        assert "AI Automation &amp; Digital Solutions" in html or "AI Automation & Digital Solutions" in html
        assert 'href="#services"' in html
        assert 'href="#who-we-help"' in html
        assert 'href="#process"' in html
        assert 'href="#about"' in html
        assert 'href="#contact"' in html
        assert 'href="/app"' in html  # Client Portal link

        # 2. Hero Section
        assert "AI Automation for Modern Businesses" in html
        assert "Enterprise-Grade AI &amp; Workflow Automation" in html or "Enterprise-Grade AI & Workflow Automation" in html
        assert "Start a Conversation" in html
        assert "Explore Services" in html

        # 3. Genuine Capability Badges (Real, no fabricated stats)
        assert "Tailored Architecture" in html
        assert "Direct Engineer Access" in html
        assert "API &amp; Webhook Integrations" in html or "API & Webhook Integrations" in html
        assert "Full Code &amp; Data Ownership" in html or "Full Code & Data Ownership" in html

        # 4. Services Grid (6 Cards)
        services = [
            "AI Automation",
            "Lead &amp; Sales Automation",
            "Customer Support Automation",
            "Workflow &amp; RPA",
            "Business Dashboards &amp; Reporting",
            "Custom AI Solutions"
        ]
        for s in services:
            clean_s = s.replace("&amp;", "&")
            assert s in html or clean_s in html

        # 5. Who We Help (Problem-centric, not fake logos)
        assert "Built for Businesses That Want to Automate" in html
        assert "Lead &amp; Pipeline Handling" in html or "Lead & Pipeline Handling" in html
        assert "Customer Communications" in html
        assert "Repetitive Administrative Tasks" in html
        assert "Disconnected Tech Stacks" in html
        assert "Reporting &amp; Operational Blindspots" in html or "Reporting & Operational Blindspots" in html
        assert "Scaling Without Headcount Bloat" in html

        # 6. How We Work (4-Step Disciplined Process)
        assert "STEP 01" in html
        assert "Discover &amp; Audit" in html or "Discover & Audit" in html
        assert "STEP 02" in html
        assert "Architect &amp; Design" in html or "Architect & Design" in html
        assert "STEP 03" in html
        assert "Build &amp; Integrate" in html or "Build & Integrate" in html
        assert "STEP 04" in html
        assert "Deploy &amp; Monitor" in html or "Deploy & Monitor" in html

        # 7. About Section
        assert "Built on Engineering Integrity" in html
        assert "Reliability First" in html
        assert "Security &amp; Data Privacy" in html or "Security & Data Privacy" in html
        assert "Measurable Impact" in html

        # 8. Contact Section & Direct Details
        assert "replies@agencygrowth.co" in html
        assert "Monday – Friday" in html or "Monday" in html
        assert "contactForm" in html
        assert 'name="name"' in html
        assert 'name="email"' in html
        assert 'name="company"' in html
        assert 'name="service_interest"' in html
        assert 'name="message"' in html

        # 9. Modals (Privacy & Terms)
        assert 'id="privacyModal"' in html
        assert 'id="termsModal"' in html
        assert "Privacy Policy" in html
        assert "Terms of Service" in html

        # 10. Authenticity / Zero Fabrication Verification
        # Must NOT contain fake testimonials, fake awards, fake client names
        forbidden_phrases = [
            "John Doe, CEO of Acme",
            "Best AI Agency 2025 Award",
            "100% Guaranteed 10x ROI",
            "Over 10,000 satisfied clients",
            "Forbes 30 Under 30 Winner",
            "$10,000,000 in generated revenue for clients"
        ]
        for phrase in forbidden_phrases:
            assert phrase.lower() not in html.lower()


@pytest.mark.asyncio
async def test_contact_inquiry_api_submission_and_validation():
    """Verifies POST /api/contact validates inputs, stores inquiry, and respects outbound safety."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Missing fields should return 400
        invalid_payload = {
            "name": "Jane Smith",
            "email": "jane@example.com",
            "company": "",
            "service_interest": "",
            "message": ""
        }
        res_bad = await client.post("/api/contact", json=invalid_payload)
        assert res_bad.status_code == 400
        assert "required" in res_bad.json().get("detail", "").lower()

        # 2. Invalid email format should return 400
        bad_email_payload = {
            "name": "Jane Smith",
            "email": "not-an-email",
            "company": "Acme Inc",
            "service_interest": "ai_automation",
            "message": "We need help automating lead routing."
        }
        res_email = await client.post("/api/contact", json=bad_email_payload)
        assert res_email.status_code == 400
        assert "valid business email" in res_email.json().get("detail", "").lower()

        # 3. Valid submission should succeed with 200
        valid_payload = {
            "name": "Sarah Connor",
            "email": "sarah@cybertech.io",
            "company": "CyberTech Systems",
            "service_interest": "sales_automation",
            "message": "We want to integrate our CRM with an automated outreach pipeline."
        }
        res_ok = await client.post("/api/contact", json=valid_payload)
        assert res_ok.status_code == 200
        data = res_ok.json()
        assert data["success"] is True
        assert "24 business hours" in data["message"]
        assert data["inquiry"]["company"] == "CyberTech Systems"
        assert data["inquiry"]["service_interest"] == "sales_automation"


@pytest.mark.asyncio
async def test_public_vs_private_route_separation():
    """Verifies strict separation: / and /website are public, while /dashboard and /app require authentication."""
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Anonymous access to public website: OK (200)
            res_pub1 = await client.get("/", follow_redirects=False)
            assert res_pub1.status_code == 200

            res_pub2 = await client.get("/website", follow_redirects=False)
            assert res_pub2.status_code == 200

            # Anonymous access to private dashboard: Redirects to /login (302/307)
            res_dash = await client.get("/dashboard", follow_redirects=False)
            assert res_dash.status_code in (302, 307)
            assert res_dash.headers["location"] == "/login"

            res_app = await client.get("/app", follow_redirects=False)
            assert res_app.status_code in (302, 307)
            assert res_app.headers["location"] == "/login"

            # Authenticated access to private dashboard: OK (200)
            token = create_session_token("admin", role="admin")
            cookies = {"agency_session": token}

            auth_dash = await client.get("/dashboard", cookies=cookies)
            assert auth_dash.status_code == 200
            # Dashboard index.html contains the dashboard view elements
            assert "view-overview" in auth_dash.text or "Agency" in auth_dash.text

            auth_app = await client.get("/app", cookies=cookies)
            assert auth_app.status_code == 200
            assert "view-overview" in auth_app.text or "Agency" in auth_app.text
    finally:
        settings.AUTH_ENABLED = orig_auth
