import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.api.app import app
from app.database.connection import AsyncSessionLocal
from app.database.models import Business, PipelineStage


@pytest.mark.asyncio
async def test_landing_page_renders_8_sections():
    """Verify that / and /website load successfully with the 8 specified business sections."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        content = res.text

        # 1. Hero
        assert "Your agency," in content
        assert "running like a system." in content
        assert "Request a Demo" in content
        assert "See How It Works" in content

        # 2. Operating System (10 stages)
        assert "THE OPERATING SYSTEM" in content
        assert "DISCOVERY" in content
        assert "DELIVERY" in content

        # 3. Demo Factory
        assert "DEMO FACTORY" in content
        assert "Requirements-Driven Software Generation" in content
        assert "REAL DEMO URL" in content

        # 4. Automation Systems
        assert "AUTOMATION SYSTEMS" in content
        assert "AI + n8n + Custom Software + Firebase + Agency OS Orchestration" in content

        # 5. Target Niches
        assert "TARGET NICHES" in content
        assert "Roofing Contractors" in content
        assert "HVAC &amp; Climate Control" in content
        assert "Dental &amp; Healthcare Clinics" in content

        # 6. How It Works (5 steps)
        assert "HOW IT WORKS" in content
        assert "01 &mdash; DISCOVER" in content
        assert "05 &mdash; DELIVER" in content

        # 7. Real Proof
        assert "REAL PROOF &amp; TELEMETRY" in content
        assert "208+ Real Businesses" in content
        assert "60+ Qualified Leads" in content
        assert "0 Fabricated Metrics" in content

        # 8. Demo Request Form
        assert "Request a Demo" in content
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
