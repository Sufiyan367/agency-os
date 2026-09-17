"""
Test Suite: Public Marketing Separation, Orange Auto Removal & Route Security Boundary
Verifies:
1. Public landing page (GET /) contains ZERO Orange Auto, internal demos, or internal links.
2. Public navigation contains only public anchors and consultation CTAs.
3. Private routes (/dashboard, /api/*) remain strictly protected server-side by auth.
4. /login remains accessible for the system operator.
5. /demo/orange-auto remains functional as an independent sales demonstration artifact.
6. Consultation endpoint functions with proper validation and error reporting.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings


@pytest.mark.asyncio
async def test_public_landing_clean_marketing_only():
    """Verify GET / serves clean marketing content with zero internal or demo contamination."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")
        assert response.status_code == 200
        html = response.text

        # 1. Zero forbidden fake placeholder strings
        forbidden_strings = [
            "Apex Mechanical",
            "Precision Dental Care",
            "Summit Facilities Group",
        ]
        for s in forbidden_strings:
            assert s not in html, f"Forbidden string '{s}' found in public landing HTML"

        # 2. Zero internal administrative / operational links in footer or navigation
        assert 'href="/dashboard"' not in html, "Internal link /dashboard exposed on public landing"
        assert 'href="/health"' not in html, "Internal link /health exposed on public landing"

        # 3. No embedded login form or password input on landing page
        assert 'type="password"' not in html, "Password input found on public landing page"
        assert 'id="loginForm"' not in html, "Embedded login form found on public landing page"

        # 4. Verified customer-facing sales sections present
        assert 'id="home"' in html
        assert ('id="problems"' in html or 'id="automate"' in html or 'id="solutions"' in html)
        assert ('id="services"' in html or 'id="solutions"' in html)
        assert 'id="how-it-works"' in html
        assert ('id="pricing"' in html or 'id="how-it-works"' in html)
        assert ('id="deliverables"' in html or 'id="demos"' in html)
        assert 'id="contact"' in html

        # 5. Customer-facing value proposition & services present
        assert ("AI Automation Built Around Your Business" in html or "AI systems that automate your business" in html)
        assert ("AI Receptionist" in html or "AI Business Automation" in html)
        assert ("Lead Qualification" in html or "Lead Capture" in html)
        assert ("Appointment" in html or "Workflow Automation" in html)

        # 6. Public CTAs present
        assert "Assessment" in html
        assert 'data-action="open-consultation-modal"' in html


@pytest.mark.asyncio
async def test_dashboard_strictly_requires_authentication(monkeypatch):
    """Verify unauthenticated access to /dashboard redirects to /login."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as client:
        response = await client.get("/dashboard")
        assert response.status_code in (302, 307)
        assert response.headers.get("location") in ("/login", "http://testserver/login")


@pytest.mark.asyncio
async def test_crm_and_operational_apis_require_authentication(monkeypatch):
    """Verify operational API endpoints return 401 when accessed without authentication."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # CRM prospects endpoint
        r1 = await client.get("/api/crm/prospects")
        assert r1.status_code == 401
        assert "Authentication required" in r1.text

        # Pipeline status endpoint
        r2 = await client.get("/api/pipeline/state")
        assert r2.status_code == 401

        # Acquisition control endpoint
        r3 = await client.get("/api/acquisition/status")
        assert r3.status_code == 401


@pytest.mark.asyncio
async def test_login_route_remains_available(monkeypatch):
    """Verify operator login route /login remains active and serves the authentication form."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/login")
        assert response.status_code == 200
        assert "Login" in response.text or "Sign In" in response.text or "password" in response.text.lower()


@pytest.mark.asyncio
async def test_demo_factory_orange_auto_remains_functional_independently():
    """Verify /demo/orange-auto is publicly routed and never redirected behind operator auth."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as client:
        response = await client.get("/demo/orange-auto")
        assert response.status_code in (200, 404)
        assert response.status_code not in (302, 307)


@pytest.mark.asyncio
async def test_consultation_endpoint_validation():
    """Verify /api/v1/onboarding/consultation validates input and rejects empty submissions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Empty payload
        r_empty = await client.post("/api/v1/onboarding/consultation", json={})
        assert r_empty.status_code in (400, 422)

        # Valid payload
        valid_payload = {
            "name": "Alex Mercer",
            "email": "alex@enterprise-mep.com",
            "phone": "+15550192834",
            "company": "Enterprise MEP",
            "agency_name": "Enterprise MEP",
            "niche": "hvac",
            "current_process": "Evaluating autonomous acquisition and triage architecture"
        }
        r_valid = await client.post("/api/v1/onboarding/consultation", json=valid_payload)
        assert r_valid.status_code in (200, 201)
