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

        # 2. What We Build (commercial categories)
        assert "WHAT WE BUILD" in content
        assert "AI Business Automation" in content
        assert "Custom AI Software" in content or "Custom Software" in content
        assert "AI Agents" in content
        assert "Workflow Automation" in content
        assert "Ongoing Management" in content

        # 3. How We Work (Engineering progression)
        assert "HOW WE WORK" in content
        assert "UNDERSTAND" in content
        assert "DESIGN" in content
        assert "BUILD" in content

        # 4. Target Blueprints & Working Demos
        assert "WORKING DEMOS" in content
        assert "Orange Auto" in content or "Automotive" in content

        # 5. Structured Technical Assessment Request Form
        assert "inlineContactForm" in content
        assert "Request Technical Assessment" in content
        assert "We respect your privacy. Zero spam. Direct engineer response within 24 business hours." in content
        assert "Lead Capture &amp; Qualification" in content or "Lead Capture & Qualification" in content
        assert "Slow response time to leads" in content
        assert "inlineCompany" in content
        assert "inlineEmail" in content
        assert "consultationForm" in content


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


@pytest.mark.asyncio
async def test_api_contact_structured_capabilities_and_problems():
    """Verify structured capability and problem selection ingestion without triggering Demo Factory."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "company_name": "Apex Dental Group",
            "work_email": "operations@apexdental.com",
            "website": "apexdentalgroup.com",
            "capabilities": [
                "Lead Capture & Qualification",
                "Appointment & Scheduling Automation",
                "Missed-Call Recovery"
            ],
            "problems": [
                "Missed customer calls / inquiries",
                "Slow response time to leads",
                "Inefficient appointment scheduling"
            ],
            "description": "We miss 25% of patient calls during peak procedures and follow up manually next morning.",
            "message": "Automate after-hours patient bookings"
        }

        res = await client.post("/api/contact", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["inquiry"]["company"] == "Apex Dental Group"
        assert data["inquiry"]["email"] == "operations@apexdental.com"

        # Verify database record exists with QUALIFIED_REPLY stage (not DEMO_REQUESTED)
        async with AsyncSessionLocal() as session:
            q = select(Business).where(Business.public_email == "operations@apexdental.com")
            biz = (await session.execute(q)).scalars().first()
            assert biz is not None
            assert biz.name == "Apex Dental Group"
            assert biz.domain == "apexdentalgroup.com"
            # Crucial requirement: ASSESSMENT_REQUESTED != DEMO_REQUESTED
            assert biz.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value
