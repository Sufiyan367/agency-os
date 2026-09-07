"""
Tests for Operator Dashboard Demo and Deterministic QA View — Phase 19.

Verifies:
1. Lead demo artifact retrieved safely without exposing raw paths or secrets (GET /api/leads/{lead_id}/demo).
2. Demo preview endpoint returns HTML with security headers and secret scrubbing (GET /api/leads/{lead_id}/demo/preview).
3. All 8 deterministic QA gates are returned and formatted with pass/fail.
4. Overall QA status and signature are present.
5. Missing demo handled gracefully (has_demo: False, 200 without crashing).
6. QA failure is accurately represented when a gate fails.
7. Secrets / absolute server filesystem paths are omitted from client responses.
8. Existing lead detail (GET /api/leads/{lead_id}) includes demo, QA, and proposal cleanly.
"""
import os
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.app import app
from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, Offer, Artifact, Proposal, PipelineStage
)
from app.delivery.requirements_engine import requirements_engine
from app.delivery.demo_factory import demo_factory
from app.delivery.demo_qa import demo_qa_engine
from app.payments.deal_service import deal_closing_service


created_biz_ids = []


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()
    yield
    if created_biz_ids:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Artifact).where(Artifact.business_id.in_(created_biz_ids)))
            await session.execute(delete(Proposal).where(Proposal.business_id.in_(created_biz_ids)))
            await session.execute(delete(Offer).where(Offer.business_id.in_(created_biz_ids)))
            await session.execute(delete(AuditRun).where(AuditRun.business_id.in_(created_biz_ids)))
            await session.execute(delete(Business).where(Business.id.in_(created_biz_ids)))
            await session.commit()
        created_biz_ids.clear()


async def create_demo_fixture(session: AsyncSession) -> Business:
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name=f"Apex Solar UAE {uid}",
        domain=f"apexsolar-{uid}.ae",
        country="AE",
        city="Dubai",
        niche="solar-energy",
        public_email=f"contact@apexsolar-{uid}.ae",
        email_status="verified",
        pipeline_stage=PipelineStage.QUALIFIED_REPLY.value
    )
    session.add(biz)
    await session.flush()

    # Clean up any residual artifacts or proposals for this ID from prior test runs
    await session.execute(delete(Artifact).where(Artifact.business_id == biz.id))
    await session.execute(delete(Proposal).where(Proposal.business_id == biz.id))

    audit = AuditRun(
        business_id=biz.id,
        url_audited=f"https://{biz.domain}/",
        performance_score=45.0,
        seo_score=88.0,
        a11y_score=80.0,
        ux_conversion_score=82.0,
        security_score=95.0,
        overall_health_score=58.0
    )
    session.add(audit)
    await session.flush()

    offer = Offer(
        business_id=biz.id,
        title="Commercial Web Speed & Conversion Turnaround",
        recommended_price=1250.0,
        service_type="Speed Optimization"
    )
    session.add(offer)
    await session.commit()
    await session.refresh(biz)
    created_biz_ids.append(biz.id)
    return biz


@pytest.mark.asyncio
async def test_lead_demo_api_missing_demo():
    """Validates graceful response when prospect does not yet have a turnkey demo."""
    async with AsyncSessionLocal() as session:
        biz = await create_demo_fixture(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/leads/{biz.id}/demo")
        assert res.status_code == 200
        data = res.json()
        assert data["has_demo"] is False
        assert data["demo"] is None
        assert data["qa"] is None
        assert data["proposal"] is None
        assert data["is_dry_run"] is True


@pytest.mark.asyncio
async def test_lead_demo_api_with_valid_demo_and_8_qa_gates():
    """Validates that a generated demo includes all 8 QA gates and metadata without leaking paths."""
    async with AsyncSessionLocal() as session:
        biz = await create_demo_fixture(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)
        qa_res = demo_qa_engine.validate_demo(demo_res, packet)

        art = await session.get(Artifact, demo_res.artifact_id)
        meta = dict(art.metadata_json or {})
        meta["qa_result"] = qa_res.model_dump()
        art.metadata_json = meta
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/leads/{biz.id}/demo")
        assert res.status_code == 200
        data = res.json()

        assert data["has_demo"] is True
        assert data["is_dry_run"] is True

        demo = data["demo"]
        assert demo["demo_id"] == demo_res.demo_id
        assert demo["service_title"] == packet.service_title
        assert demo["price_usd"] == packet.catalog_price_usd
        assert demo["preview_url"] == f"/api/leads/{biz.id}/demo/preview"

        # Strictly verify no raw absolute filesystem paths in demo object
        assert "html_file_path" not in demo
        assert "json_spec_path" not in demo
        assert "path" not in demo

        qa = data["qa"]
        assert qa["overall_passed"] is True
        assert qa["total_checks"] == 8
        assert qa["passed_checks"] == 8
        assert qa["failed_checks"] == 0
        assert qa["qa_signature"].startswith("QA-PASS-")

        # Verify all 8 individual gate names
        check_names = {c["name"] for c in qa["checks"]}
        expected_gates = {
            "FILE_EXISTENCE_HTML",
            "FILE_EXISTENCE_SPEC",
            "IDENTITY_INTEGRITY",
            "COMMERCIAL_ALIGNMENT",
            "ZERO_PLACEHOLDERS",
            "STRUCTURAL_VALIDITY",
            "REQUIREMENTS_COVERAGE",
            "DETERMINISTIC_CHECKSUM"
        }
        assert check_names == expected_gates
        for c in qa["checks"]:
            assert c["passed"] is True


@pytest.mark.asyncio
async def test_demo_preview_endpoint_serves_html_and_security_headers():
    """Validates safe HTML delivery with X-Frame-Options and Content-Security-Policy headers."""
    async with AsyncSessionLocal() as session:
        biz = await create_demo_fixture(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/leads/{biz.id}/demo/preview")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")

        # Frame and security headers
        assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert "frame-ancestors 'self'" in res.headers.get("Content-Security-Policy", "")
        assert res.headers.get("X-Content-Type-Options") == "nosniff"

        # Content correctness
        html = res.text
        assert biz.name in html
        assert biz.domain in html
        assert "<!DOCTYPE html>" in html or "<!doctype html>" in html


@pytest.mark.asyncio
async def test_demo_preview_scrubs_secrets():
    """Validates that secrets accidentally present in the artifact file are scrubbed before serving."""
    async with AsyncSessionLocal() as session:
        biz = await create_demo_fixture(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)

        art = await session.get(Artifact, demo_res.artifact_id)
        # Inject mock secret into the artifact HTML file
        with open(art.path, "a", encoding="utf-8") as f:
            f.write("\n<!-- api_key: sk-live-secret-999988887777 -->")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/leads/{biz.id}/demo/preview")
        assert res.status_code == 200
        html = res.text
        assert "sk-live-secret-999988887777" not in html
        assert "[REDACTED]" in html or "[REDACTED_SECRET]" in html


@pytest.mark.asyncio
async def test_no_filesystem_paths_leaked_in_qa_check_details():
    """Validates that check details do not leak absolute server drive letters or paths."""
    async with AsyncSessionLocal() as session:
        biz = await create_demo_fixture(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)
        qa_res = demo_qa_engine.validate_demo(demo_res, packet)

        art = await session.get(Artifact, demo_res.artifact_id)
        meta = dict(art.metadata_json or {})
        meta["qa_result"] = qa_res.model_dump()
        art.metadata_json = meta
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/leads/{biz.id}/demo/qa")
        assert res.status_code == 200
        data = res.json()
        assert data["overall_passed"] is True

        for chk in data["checks"]:
            details = chk["details"]
            assert ":\\" not in details, f"Drive letter path leaked in check details: {details}"
            assert "/data/artifacts/" not in details, f"Internal path leaked in check details: {details}"


@pytest.mark.asyncio
async def test_qa_failure_representation():
    """Validates accurate reporting when deterministic QA gates fail."""
    async with AsyncSessionLocal() as session:
        biz = await create_demo_fixture(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)

        # Inject failure into HTML
        demo_res.html_content += "\n<div>{{TODO_UNRESOLVED_PLACEHOLDER}}</div>"
        qa_res = demo_qa_engine.validate_demo(demo_res, packet)

        art = await session.get(Artifact, demo_res.artifact_id)
        meta = dict(art.metadata_json or {})
        meta["qa_result"] = qa_res.model_dump()
        art.metadata_json = meta
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/leads/{biz.id}/demo")
        assert res.status_code == 200
        data = res.json()
        assert data["has_demo"] is True
        qa = data["qa"]
        assert qa["overall_passed"] is False
        assert qa["failed_checks"] >= 1
        assert any(c["name"] == "ZERO_PLACEHOLDERS" and not c["passed"] for c in qa["checks"])
        assert qa["qa_signature"] == "QA-FAIL"


@pytest.mark.asyncio
async def test_get_lead_detail_includes_demo_and_proposal():
    """Validates that GET /api/leads/{lead_id} includes demo and proposal without breaking existing fields."""
    async with AsyncSessionLocal() as session:
        biz = await create_demo_fixture(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)
        qa_res = demo_qa_engine.validate_demo(demo_res, packet)

        art = await session.get(Artifact, demo_res.artifact_id)
        meta = dict(art.metadata_json or {})
        meta["qa_result"] = qa_res.model_dump()
        art.metadata_json = meta

        proposal = await deal_closing_service.create_proposal(
            session=session,
            business_id=biz.id,
            title="Comprehensive Turnaround Proposal",
            total_value=1250.0,
            advance_required=500.0,
            service_type="Speed Optimization",
            is_mock=True
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/leads/{biz.id}")
        assert res.status_code == 200
        data = res.json()

        # Existing fields intact
        assert "business" in data
        assert "audit" in data
        assert "offer" in data
        assert data["business"]["id"] == biz.id

        # Demo included
        assert data["demo"] is not None
        assert data["demo"]["demo_id"] == demo_res.demo_id
        assert data["demo"]["qa"]["overall_passed"] is True
        assert data["demo"]["qa"]["total_checks"] == 8

        # Proposal included
        assert data["proposal"] is not None
        assert data["proposal"]["id"] == proposal.id
        assert data["proposal"]["total_value"] == 1250.0
        assert data["proposal"]["advance_required"] == 500.0
        assert data["proposal"]["is_dry_run"] is True


@pytest.mark.asyncio
async def test_demo_preview_404_handling():
    """Validates clean 404 responses for nonexistent leads and leads without demos."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Nonexistent business
        res = await client.get("/api/leads/99999999/demo/preview")
        assert res.status_code == 404

        # Business exists but no demo
        async with AsyncSessionLocal() as session:
            biz = await create_demo_fixture(session)

        res = await client.get(f"/api/leads/{biz.id}/demo/preview")
        assert res.status_code == 404, f"Got {res.status_code}: {res.text}"
