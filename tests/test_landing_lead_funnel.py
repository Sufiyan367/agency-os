import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.api.app import app
from app.database.connection import AsyncSessionLocal
from app.database.models import Business, PipelineStage


@pytest.mark.asyncio
async def test_landing_page_renders_commercial_positioning_sections():
    """Verify that / and /website load successfully with the realigned 9 commercial business sections."""
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
        assert "Custom Software" in content
        assert "AI Agents" in content
        assert "Workflow Automation" in content
        assert "Ongoing Management" in content

        # 3. System Examples / Use Cases (8 concrete solutions)
        assert "USE CASES" in content
        assert "Lead Qualification" in content
        assert "AI Appointment Assistant" in content
        assert "Automated Follow-Up" in content
        assert "CRM Automation" in content
        assert "Customer Support" in content
        assert "Quote &amp; Request Systems" in content
        assert "Customer Onboarding" in content
        assert "Internal Business Dashboards" in content

        # 4. How It Works (Customer journey)
        assert "HOW IT WORKS" in content
        assert "01 &mdash; TELL US THE PROBLEM" in content
        assert "02 &mdash; WE DESIGN THE SOLUTION" in content
        assert "03 &mdash; SEE A WORKING DEMO" in content
        assert "04 &mdash; WE BUILD &amp; DEPLOY" in content
        assert "05 &mdash; WE MAINTAIN &amp; IMPROVE" in content

        # 5. Who We Help (Target niches)
        assert "WHO WE HELP" in content
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
        assert "Connect Your Tools. Automate the Work." in content

        # 8. Real Proof
        assert "REAL PROOF" in content
        assert "Grounded in Real Production Telemetry" in content

        # 9. Final CTA Form
        assert "Tell Us What Is Wasting Your Team&#39;s Time" in content or "Tell Us What Is Wasting Your Team's Time" in content
        assert "contactWebsite" in content
        assert "contactProblem" in content
        assert "contactAutomated" in content


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
