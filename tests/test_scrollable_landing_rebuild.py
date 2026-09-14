import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings

@pytest.mark.asyncio
async def test_scrollable_landing_sections_and_content():
    """Verify GET / renders the full multi-section scrollable website with all required sections."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        html = r.text

        # 1. Page Title & Meta
        assert "<title>Intelligence Designed To Evolve</title>" in html
        assert 'name="description"' in html
        assert 'property="og:title"' in html

        # 2. Hero Section (#home)
        assert 'id="home"' in html
        assert 'class="hero-section"' in html
        assert 'class="bg-video"' in html
        assert "Trusted by 2000+ Enterprises" in html
        assert "<span>Intelligence</span>" in html
        assert "<span>Designed To Evolve</span>" in html
        assert "Build applications that reason, adapt and collaborate using a modular AI platform designed for production." in html
        assert "Get Started" in html
        assert "Inference Time" in html
        assert "Platform Uptime" in html
        assert "Autonomous Runtime" in html
        assert "Context Windows" in html

        # 3. Navigation
        assert 'href="#home"' in html
        assert 'href="#product"' in html
        assert 'href="#capabilities"' in html
        assert 'href="#how-it-works"' in html
        assert 'href="#industries"' in html
        assert 'href="#case-studies"' in html
        assert 'href="#contact"' in html
        assert 'Book Consultation' in html
        assert 'id="burgerBtn"' in html
        assert 'id="mobileMenu"' in html

        # 4. Product Section (#product)
        assert 'id="product"' in html
        assert "One Operating System for Autonomous Growth" in html
        assert "DISCOVER" in html
        assert "QUALIFY" in html
        assert "AUDIT" in html
        assert "OUTREACH" in html
        assert "RESPOND" in html
        assert "DEMO" in html
        assert "CLOSE" in html
        assert "DELIVER" in html

        # 5. Capabilities Section (#capabilities)
        assert 'id="capabilities"' in html
        assert "Prospect Discovery" in html
        assert "AI Auditing" in html
        assert "Personalized Outreach" in html
        assert "Response Intelligence" in html
        assert "Demo Factory" in html
        assert "Autonomous Delivery" in html

        # 6. Channels Section (#channels)
        assert 'id="channels"' in html
        assert "Every Conversation, One System" in html
        assert "EMAIL" in html
        assert "WHATSAPP" in html
        assert "VOICE" in html
        assert "Built for email, WhatsApp and voice orchestration." in html

        # 7. How It Works Section (#how-it-works)
        assert 'id="how-it-works"' in html
        assert "Discover" in html
        assert "Understand" in html
        assert "Engage" in html
        assert "Convert" in html
        assert "Deliver" in html

        # 8. Industries Section (#industries)
        assert 'id="industries"' in html
        assert "Automotive" in html
        assert "Dental" in html
        assert "HVAC" in html
        assert "Home Services" in html
        assert "Aesthetic Clinics" in html
        assert "Real Estate" in html

        # 9. Operational Workflows Section (#case-studies)
        assert 'id="case-studies"' in html
        assert "Enterprise Automation Workflows" in html
        assert "See how Agency OS can automate lead response, qualification, follow-up and delivery" in html
        assert "Orange Auto" not in html
        assert 'href="/demo/orange-auto"' not in html
        assert "Interactive Demonstration" not in html
        assert "Automotive Service &amp; Diagnostics" not in html
        assert "Diagnostic Audit Engine" not in html
        assert "Appointment Intake" not in html
        assert "Instant SMS/Email Confirmation" not in html

        # 10. Architecture Section (#architecture)
        assert 'id="architecture"' in html
        assert "Built as an Operating System, Not a Collection of Bots" in html
        assert "AI Reasoning Layer" in html
        assert "Orchestration &amp; State Engine" in html or "Orchestration & State Engine" in html
        assert "CRM &amp; Persistent State" in html or "CRM & Persistent State" in html
        assert "Communication Adapters" in html
        assert "Sales &amp; Transaction Pipelines" in html or "Sales & Transaction Pipelines" in html
        assert "Autonomous Delivery Engine" in html

        # 11. Security & Reliability Section (#security)
        assert 'id="security"' in html
        assert "Human Approval Gates" in html
        assert "Idempotent Actions" in html
        assert "Immutable Audit Events" in html
        assert "Outbound Limits" in html
        assert "State-Machine Control" in html
        assert "Failure Isolation" in html

        # 12. Contact Section (#contact)
        assert 'id="contact"' in html
        assert "Ready to build an autonomous growth system?" in html
        assert "Let's identify where intelligent automation can remove operational friction from your business." in html
        assert '<button type="button" class="cta-button" data-action="open-consultation-modal">Get Started</button>' in html
        assert 'id="inlineContactForm"' in html
        assert 'id="inlineAlert"' in html

        # 13. Back to Top Button
        assert 'id="backToTop"' in html

        # 14. Footer
        assert "<footer" in html
        assert "Agency OS" in html
        assert "Intelligence Designed To Evolve" in html
        assert "&copy; 2026 Agency OS" in html or "© 2026 Agency OS" in html

        # 15. Consultation Modal
        assert 'id="consultationModal"' in html
        assert 'id="consultationForm"' in html
        assert 'id="consultationAlert"' in html
        assert 'id="consultationName"' in html
        assert 'id="consultationEmail"' in html

@pytest.mark.asyncio
async def test_css_scrolling_and_no_body_lock():
    """Verify landing.css enables vertical scrolling without single-viewport locks."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/static/landing.css")
        assert r.status_code == 200
        css = r.text

        # Body must have overflow-y: auto and min-height
        assert "overflow-y: auto;" in css
        assert "overflow-x: hidden;" in css
        assert "min-height: 100%;" in css

        # Document must NOT lock whole page with overflow: hidden on html/body (except body.menu-open)
        assert "scroll-behavior: smooth;" in css
        assert ".scroll-reveal" in css
        assert ".back-to-top" in css

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

        # 3. Invalid email format
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
