import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.api.app import app
from app.database.connection import AsyncSessionLocal
from app.database.models import Business, PipelineStage


@pytest.mark.asyncio
async def test_landing_page_renders_commercial_positioning_sections():
    """Verify that / loads successfully with the commercial Viktor Oddy editorial sections."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        content = res.text

        # 1. Hero: Customer proposition, no internal toolchain
        assert "AI systems that" in content
        assert "automate your business." in content
        assert "Get Your Automation Built" in content
        assert "See a Working Demo" in content

        # Verify internal implementation details are NOT exposed in customer hero
        assert "Stitch" not in content
        assert "Google AI Studio" not in content
        assert "Antigravity" not in content
        assert "Firebase" not in content

        # 2. What We Build (5 commercial categories)
        assert "WHAT WE BUILD" in content
        assert "AI Business Automation" in content
        assert "Custom AI Software" in content or "Custom Software" in content
        assert "AI Agents" in content
        assert "Workflow Automation" in content
        assert "Ongoing Management" in content

        # 3. Customer Problems & Solutions (Friction elimination)
        assert "Replace repetitive work with systems that run." in content
        assert "Manual Lead Handling" in content
        assert "Automated Lead Capture + Qualification" in content
        assert "Manual Follow-Up" in content
        assert "Automated Follow-Up Workflow" in content

        # 4. How It Works (Customer journey)
        assert "HOW IT WORKS" in content
        assert "01 — Tell us the problem" in content
        assert "02 — We define the system" in content
        assert "03 — You see a working demo" in content
        assert "04 — Proposal + advance payment" in content
        assert "05 — We build and deploy" in content
        assert "06 — We maintain and improve it" in content

        # 5. Who We Help (Target niches)
        assert "Who We Help" in content
        assert "Roofing" in content
        assert "HVAC" in content
        assert "Dental" in content
        assert "Real Estate" in content
        assert "Home Services" in content

        # 6. Working Demos (Problem -> Solution -> Working result)
        assert "WORKING DEMOS" in content
        assert "Problem:" in content
        assert "Solution:" in content
        assert "Working Result:" in content

        # 7. Workflow Automation
        assert "WORKFLOW AUTOMATION" in content
        assert "Connect the work. Automate the handoffs." in content

        # 8. Honest Proof
        assert "Building our first public case studies." in content

        # 9. Final CTA Form
        assert "Tell us what is wasting your team's time." in content
        assert "inlineContactForm" in content
        assert "inlineWebsite" in content
        assert "inlineProblem" in content
        assert "inlineAutomated" in content


@pytest.mark.asyncio
async def test_api_contact_persists_to_business_database():
    """Verify that submitting /api/contact directly inserts a real lead into the Business table."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "Marcus Vance",
            "email": "marcus@vancehvac.com",
            "company": "Vance HVAC Services",
            "website": "vancehvac.com",
            "service_interest": "HVAC Emergency Booking",
            "problem": "Lost late-night emergency heating and AC calls to competitors.",
            "what_they_want_automated": "24/7 automated intake scheduler with customer SMS dispatch.",
            "message": "Need urgent demo for commercial HVAC operations."
        }

        res = await client.post("/api/contact", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "lead_id" in data["inquiry"]

        # Verify database record exists
        async with AsyncSessionLocal() as session:
            q = select(Business).where(Business.public_email == "marcus@vancehvac.com")
            biz = (await session.execute(q)).scalars().first()
            assert biz is not None
            assert biz.name == "Vance HVAC Services"
            assert biz.domain == "vancehvac.com"
            assert biz.pipeline_stage in (PipelineStage.QUALIFIED_REPLY.value, PipelineStage.DISCOVERED.value)
