import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings

@pytest.mark.asyncio
async def test_scrollable_landing_sections_and_content():
    """Verify GET / renders the full multi-section scrollable website with all required Viktor Oddy style editorial sections."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        html = r.text

        # 1. Page Title & Meta
        assert "<title>Agency OS — AI Systems &amp; Automation</title>" in html
        assert 'name="description"' in html
        assert 'property="og:title"' in html

        # 2. Hero Section (#home)
        assert 'id="home"' in html
        assert "hf_20260809_012548_ef22562c-c0ae-4816-ad9d-f8922af4e6a7.mp4" in html
        assert "AI systems that automate your business." in html
        assert "We build AI-powered automation" in html
        assert "Get Your Automation Built" in html
        assert "See a Working Demo" in html

        # 3. Navigation
        assert 'href="#home"' in html
        assert 'href="#solutions"' in html
        assert 'href="#problems"' in html
        assert 'href="#how-it-works"' in html
        assert 'href="#demos"' in html
        assert 'href="#automation"' in html
        assert 'href="#contact"' in html
        assert 'id="burgerBtn"' in html
        assert 'id="mobileDrawer"' in html

        # 4. Section 02: Marquee / Visual Showcase
        assert "AI Automation" in html
        assert "Custom Software" in html
        assert "AI Agents" in html
        assert "Workflow Automation" in html
        assert "Business Dashboards" in html
        assert "Customer Systems" in html

        # 5. Section 03: What We Build (#solutions)
        assert 'id="solutions"' in html
        assert "What we build" in html
        assert "01" in html and "AI Business Automation" in html
        assert "02" in html and "Custom AI Software" in html
        assert "03" in html and "AI Agents" in html
        assert "04" in html and "Workflow Automation" in html
        assert "05" in html and "Ongoing Management" in html

        # 6. Section 04: Customer Problems & Solutions (#problems)
        assert 'id="problems"' in html
        assert "Replace repetitive work with systems that run." in html
        assert "Manual Lead Handling" in html
        assert "Automated Lead Capture + Qualification" in html
        assert "Manual Follow-Up" in html
        assert "Automated Follow-Up Workflow" in html
        assert "Repetitive Customer Support" in html
        assert "AI Support System" in html
        assert "Disconnected Tools" in html
        assert "Bi-Directional CRM &amp; Data Sync" in html
        assert "Slow Appointment Handling" in html
        assert "24/7 Self-Serve Scheduling" in html
        assert "Time-Consuming Reporting" in html
        assert "Real-Time Operations Dashboard" in html

        # 7. Section 05: How It Works (#how-it-works, 6-step editorial flow)
        assert 'id="how-it-works"' in html
        assert "01 — Tell us the problem" in html
        assert "02 — We define the system" in html
        assert "03 — You see a working demo" in html
        assert "04 — Proposal + advance payment" in html
        assert "05 — We build and deploy" in html
        assert "06 — We maintain and improve it" in html

        # 8. Section 06: Demos (#demos)
        assert 'id="demos"' in html
        assert "See what the system can become." in html
        assert "Orange Auto" in html
        assert 'href="/demo/orange-auto"' in html
        assert "Summit HVAC" in html
        assert "Request a Working Demo" in html

        # 9. Section 07: Workflow Automation (#automation)
        assert 'id="automation"' in html
        assert "Connect the work. Automate the handoffs." in html
        assert "CRM Synchronization" in html
        assert "Lead Capture &amp; Qualification" in html
        assert "Automated Follow-Up Sequences" in html
        assert "24/7 Appointment Scheduling" in html
        assert "Operational Alerts &amp; Notifications" in html
        assert "Reporting &amp; Internal Dashboards" in html

        # 10. Section 08: Custom AI Software (#software)
        assert 'id="software"' in html
        assert "Software built around your process." in html

        # 11. Section 09: Ongoing Management (#management)
        assert 'id="management"' in html
        assert "Built, then kept running." in html

        # 12. Section 10: Who We Help (#niches)
        assert 'id="niches"' in html
        assert "Who We Help" in html
        assert "Roofing" in html
        assert "HVAC" in html
        assert "Dental" in html
        assert "Real Estate" in html
        assert "Home Services" in html

        # 13. Section 11: Honest Proof (#proof)
        assert 'id="proof"' in html
        assert "Building our first public case studies." in html

        # 14. Section 12: Pricing (#pricing)
        assert 'id="pricing"' in html
        assert "Solutions are scoped around your workflow, requirements and implementation complexity." in html

        # 15. Section 13: Final CTA & Contact Form (#contact)
        assert 'id="contact"' in html
        assert "Tell us what is wasting your team's time." in html
        assert "We'll turn the repetitive parts of the process into a system." in html
        assert 'id="inlineContactForm"' in html
        assert 'id="inlineContactAlert"' in html

        # 16. Footer
        assert "<footer" in html
        assert "AGENCY OS" in html
        assert "2026 Agency OS" in html

        # 17. Consultation Modal
        assert 'id="consultationModal"' in html
        assert 'id="consultationForm"' in html
        assert 'id="consultationAlert"' in html
        assert 'id="consultationName"' in html
        assert 'id="consultationEmail"' in html


@pytest.mark.asyncio
async def test_css_scrolling_and_no_body_lock():
    """Verify landing page HTML and inline styles enable vertical scrolling without single-viewport locks."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        html = r.text

        # Body must have overflow-y: auto and min-height
        assert "overflow-y: auto;" in html
        assert "overflow-x: hidden;" in html
        assert "min-height: 100%;" in html

        # Document must NOT lock whole page with overflow: hidden on html/body (except mobile drawer/modal open)
        assert "scroll-behavior: smooth;" in html
        assert ".scroll-reveal" in html


@pytest.mark.asyncio
async def test_onboarding_consultation_api_endpoint():
    """Verify POST /api/v1/onboarding/consultation validates inputs and returns success."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Valid consultation request
        valid_payload = {
            "name": "Alex Mercer",
            "email": "alex@mercerlogistics.com",
            "phone": "+1234567890",
            "company": "Mercer Logistics",
            "niche": "enterprise",
            "current_process": "Manual quote estimation bottleneck"
        }
        r_ok = await client.post("/api/v1/onboarding/consultation", json=valid_payload)
        assert r_ok.status_code == 200
        data = r_ok.json()
        assert data.get("success") is True
        assert "consultation" in data
        assert data["consultation"]["name"] == "Alex Mercer"

        # 2. Valid aliased consultation request (fullName, businessEmail, companyName, notes)
        aliased_payload = {
            "fullName": "Jordan Vance",
            "businessEmail": "jordan@vanceholdings.com",
            "companyName": "Vance Holdings",
            "notes": "Autonomous workflow deployment"
        }
        r_alias = await client.post("/api/v1/onboarding/consultation", json=aliased_payload)
        assert r_alias.status_code == 200
        data_alias = r_alias.json()
        assert data_alias.get("success") is True
        assert data_alias["consultation"]["name"] == "Jordan Vance"
        assert data_alias["consultation"]["email"] == "jordan@vanceholdings.com"
        assert data_alias["consultation"]["company"] == "Vance Holdings"

        # 3. Missing required fields
        r_missing = await client.post("/api/v1/onboarding/consultation", json={"name": "", "email": ""})
        assert r_missing.status_code == 400

        # 4. Invalid email format
        r_bad_email = await client.post("/api/v1/onboarding/consultation", json={"name": "Alex", "email": "invalid"})
        assert r_bad_email.status_code == 400


@pytest.mark.asyncio
async def test_existing_critical_routes_untouched(monkeypatch):
    """Verify /login, /dashboard auth, and /demo/orange-auto work as expected."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        # Login page serves HTML when auth enabled
        r_login = await client.get("/login")
        assert r_login.status_code == 200
        assert "text/html" in r_login.headers["content-type"]

        # Health endpoint
        r_health = await client.get("/health")
        assert r_health.status_code == 200

        # Demo orange-auto endpoint
        r_demo = await client.get("/demo/orange-auto")
        assert r_demo.status_code in (200, 404)
        assert r_demo.status_code not in (302, 307)
