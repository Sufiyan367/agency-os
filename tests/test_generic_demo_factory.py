"""
Tests for Universal Generic Demo Factory & Client-Facing Renderer — Phase 19.

Proves that:
1. Four distinct business niches (Automotive, Roofing, Dental, HVAC/Clean Energy)
   render through the exact same generic Demo Factory and Renderer without changing renderer code.
2. All 8 deterministic QA gates pass for every niche.
3. Zero internal operational data is leaked (no internal IDs, no pipeline stages, no server paths).
4. Public endpoint /demo/{business-slug} serves customized client-facing demos safely without login.
5. Invalid slugs return 404 cleanly.
"""
import os
import json
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.app import app
from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, Offer, Artifact, PipelineStage
)
from app.delivery.requirements_engine import requirements_engine, RequirementsPacket
from app.delivery.demo_factory import demo_factory
from app.delivery.demo_qa import demo_qa_engine
from app.delivery.demo_models import InteractiveScenarioType, ClientSafeDemoConfig


created_biz_ids = []


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()
    yield
    if created_biz_ids:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Artifact).where(Artifact.business_id.in_(created_biz_ids)))
            await session.execute(delete(Offer).where(Offer.business_id.in_(created_biz_ids)))
            await session.execute(delete(AuditRun).where(AuditRun.business_id.in_(created_biz_ids)))
            await session.execute(delete(Business).where(Business.id.in_(created_biz_ids)))
            await session.commit()
        created_biz_ids.clear()


async def create_niche_fixture(
    session: AsyncSession,
    name: str,
    domain: str,
    niche: str,
    city: str,
    country: str,
    service_title: str,
    service_type: str,
    price: float,
    performance_score: float = 55.0
) -> Business:
    uid = uuid.uuid4().hex[:6]
    unique_domain = f"{domain.split('.')[0]}-{uid}.{domain.split('.')[-1]}"
    biz = Business(
        name=f"{name} {uid}",
        domain=unique_domain,
        country=country,
        city=city,
        niche=niche,
        public_email=f"service@{unique_domain}",
        phone="+971-4-1234567" if country == "AE" else "+1-555-0199",
        email_status="verified",
        pipeline_stage=PipelineStage.QUALIFIED_REPLY.value
    )
    session.add(biz)
    await session.flush()

    audit = AuditRun(
        business_id=biz.id,
        url_audited=f"https://{biz.domain}/",
        performance_score=performance_score,
        seo_score=85.0,
        a11y_score=82.0,
        ux_conversion_score=80.0,
        security_score=90.0,
        overall_health_score=65.0
    )
    session.add(audit)
    await session.flush()

    offer = Offer(
        business_id=biz.id,
        title=service_title,
        recommended_price=price,
        service_type=service_type,
        estimated_delivery_days=4
    )
    session.add(offer)
    await session.commit()
    await session.refresh(biz)
    created_biz_ids.append(biz.id)
    return biz


@pytest.mark.asyncio
async def test_multi_niche_rendering_through_same_factory():
    """
    Validates that automotive, roofing, dental, and HVAC businesses all render
    through the exact same generic Demo Factory and Renderer without any code modification.
    """
    niches_test_data = [
        # Niche 1: Automotive (Orange Auto canary fixture)
        {
            "name": "Orange Auto Dubai",
            "domain": "orangeauto.ae",
            "niche": "automotive-repair",
            "city": "Dubai",
            "country": "AE",
            "service_title": "AI Receptionist & After-Hours Call Recovery",
            "service_type": "Voice Intake",
            "price": 1200.0,
            "expected_scenario": InteractiveScenarioType.CALL_SIMULATOR
        },
        # Niche 2: Roofing Contractor
        {
            "name": "Apex Roofing Systems",
            "domain": "apexroofingpro.com",
            "niche": "roofing-contractor",
            "city": "Dallas",
            "country": "US",
            "service_title": "AI Lead Qualification & Scope Intake",
            "service_type": "Lead Operations",
            "price": 1000.0,
            "expected_scenario": InteractiveScenarioType.CHAT_SIMULATOR
        },
        # Niche 3: Dental Practice
        {
            "name": "Beacon Dental Care",
            "domain": "beacondentalcare.com",
            "niche": "dental-practice",
            "city": "Chicago",
            "country": "US",
            "service_title": "Appointment Automation & CRM Integration",
            "service_type": "Scheduling Operations",
            "price": 1100.0,
            "expected_scenario": InteractiveScenarioType.WORKFLOW_STEPPER
        },
        # Niche 4: Commercial HVAC / Energy
        {
            "name": "Horizon Energy & HVAC",
            "domain": "horizonenergy.ae",
            "niche": "solar-energy",
            "city": "Abu Dhabi",
            "country": "AE",
            "service_title": "Commercial Web Speed & Performance Turnaround",
            "service_type": "Speed Optimization",
            "price": 1350.0,
            "expected_scenario": InteractiveScenarioType.SPEED_COMPARATOR
        }
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with AsyncSessionLocal() as session:
            for item in niches_test_data:
                biz = await create_niche_fixture(
                    session=session,
                    name=item["name"],
                    domain=item["domain"],
                    niche=item["niche"],
                    city=item["city"],
                    country=item["country"],
                    service_title=item["service_title"],
                    service_type=item["service_type"],
                    price=item["price"]
                )

                packet = await requirements_engine.build_requirements_packet(session, biz.id)
                demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)
                assert demo_res.success is True
                assert demo_res.html_content is not None
                assert len(demo_res.html_content) > 500

                # 1. Deterministic QA Engine Validation (All 8 Gates Must Pass)
                qa_res = demo_qa_engine.validate_demo(demo_res, packet)
                assert qa_res.overall_passed is True, f"QA failed for {biz.name}: {qa_res.error_summary}"
                assert qa_res.total_checks == 8
                assert qa_res.passed_checks == 8
                assert qa_res.failed_checks == 0
                assert qa_res.qa_signature.startswith("QA-PASS-")

                # 2. Strict Zero Operational Data Leakage Check
                leak_res = demo_qa_engine.verify_zero_internal_leakage(demo_res.html_content)
                assert leak_res["passed"] is True, f"Internal leakage detected in {biz.name}: {leak_res['leaks']}"

                # 3. Content Correctness
                html = demo_res.html_content
                assert biz.name in html
                assert biz.domain in html
                assert item["service_title"] in html
                assert f"${item['price']:,.2f}" in html
                assert "<!DOCTYPE html>" in html

                # 4. Client-Safe Spec Validation
                with open(demo_res.metadata.json_spec_path, "r", encoding="utf-8") as f:
                    spec_data = json.load(f)
                client_config = ClientSafeDemoConfig.model_validate(spec_data)
                assert client_config.identity.business_name == biz.name
                assert client_config.identity.domain == biz.domain
                assert client_config.identity.niche == item["niche"]
                assert client_config.scenario.scenario_type == item["expected_scenario"]
                assert len(client_config.identity.verified_facts) >= 2
                assert len(client_config.opportunity.diplomatic_observations) >= 2

                # 5. Public Endpoint Serving (/demo/{business-slug})
                slug = client_config.identity.slug
                public_res = await client.get(f"/demo/{slug}")
                assert public_res.status_code == 200
                assert "text/html" in public_res.headers.get("content-type", "")
                assert public_res.headers.get("X-Frame-Options") == "SAMEORIGIN"
                assert public_res.headers.get("X-Content-Type-Options") == "nosniff"
                assert biz.name in public_res.text


@pytest.mark.asyncio
async def test_public_demo_endpoint_404_on_unknown_slug():
    """Validates that nonexistent or malicious demo slugs return clean HTTP 404 without leaking stack traces."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/demo/completely-nonexistent-slug-xyz-999")
        assert res.status_code == 404
        assert "No demonstration package found" in res.text


@pytest.mark.asyncio
async def test_zero_raw_audit_deficiency_leakage_in_client_demo():
    """
    Validates that raw internal operational deficiency scores and raw database IDs
    are never leaked into the prospect-facing demo HTML.
    """
    async with AsyncSessionLocal() as session:
        biz = await create_niche_fixture(
            session=session,
            name="Precision Auto Body",
            domain="precisionautobody.com",
            niche="automotive-repair",
            city="Houston",
            country="US",
            service_title="AI Receptionist & Booking Turnaround",
            service_type="Voice Intake",
            price=1250.0,
            performance_score=41.2
        )
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)

    html = demo_res.html_content

    # Internal operational assertions:
    assert "business_id" not in html
    assert "audit_run_id" not in html
    assert "overall_health_score" not in html
    assert "UX_CONVERSION" not in html
    assert "DISCOVERED" not in html
    assert "PENDING_APPROVAL" not in html
    assert "QUALIFIED_REPLY" not in html
    assert ":\\" not in html
    assert "/opt/agency/" not in html
