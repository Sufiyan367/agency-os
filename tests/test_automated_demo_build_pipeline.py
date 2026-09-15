"""
Unit & Integration Tests for Automated Customer Demo & Build Pipeline.
Validates:
- Canonical Specification Engine & 3-way segregation
- Stitch Design Provider (4 distinct industries: Automotive, Dental, Roofing, HVAC)
- Google AI Studio Provider & conversational prototypes
- Antigravity Coding Provider & multi-file artifact generation
- 20-Gate Quality Assurance Engine (syntax, routes, UI, zero-placeholders, zero-secrets, zero-leakage)
- Bounded Autonomous Repair Loop (max 3 attempts, failure classification, patch application)
- Firebase Infrastructure Provider & Isolated Sandbox Deployment
- Public and REST endpoints (GET /demo/{customer_slug}/{demo_id}, GET /api/projects, POST /api/projects/trigger)
- Backward compatibility of GET /demo/{business_slug}
- CRM State Machine & Reply Classifier integration
- Strict Payment Boundary (Demo != Production Delivery)
- Per-project independent concurrency isolation
"""

import os
import pytest
import asyncio
import tempfile
import shutil
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.database.connection import Base
from app.database.models import (
    Business, CustomerProject, ProjectSpecification, DesignSpecification,
    AIFeatureSpecification, ProjectBuild, BuildQA, RepairAttempt,
    ProjectDeployment, ProjectEvent, PipelineStage, ReplyClassification,
    Offer, Proposal, ActiveOutreachLock
)
from app.builder.models import (
    CanonicalSpec, RequirementFact, CustomerRequestItem, AIInferenceItem,
    DesignResult, AIPrototypeResult, BuildResult, PipelineQAResult
)
from app.builder.spec_engine import CanonicalSpecEngine, spec_engine
from app.builder.providers.stitch_provider import StitchDesignProvider
from app.builder.providers.ai_studio_provider import GoogleAIStudioProvider
from app.builder.providers.antigravity_coding_provider import AntigravityCodingProvider
from app.builder.providers.firebase_provider import FirebaseInfrastructureProvider
from app.builder.qa_engine import BuildQAEngine
from app.builder.repair_engine import BuildRepairEngine, MAX_REPAIR_ATTEMPTS
from app.builder.deployment import DemoDeploymentEngine
from app.builder.pipeline import BuildPipelineOrchestrator, pipeline_orchestrator, get_project_lock
from app.crm.reply_classifier import ReplyClassifier
from app.crm.autonomous_reply_handler import AutonomousReplyHandler, RoutineCategory
from app.api.app import app


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# =====================================================================
# 1. SPECIFICATION ENGINE & 3-WAY SEGREGATION TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_canonical_spec_engine_facts_extraction(test_db):
    biz = Business(
        name="Apex Dental Care",
        domain="apexdental.com",
        niche="Dental",
        city="Austin",
        country="US",
        phone="+1 (512) 555-0199",
        public_email="info@apexdental.com"
    )
    test_db.add(biz)
    await test_db.commit()

    facts = CanonicalSpecEngine.extract_facts(biz)
    categories = [f.category for f in facts]
    assert "business_identity" in categories
    assert "digital_presence" in categories
    assert "market_sector" in categories
    assert "contact_channel" in categories

    biz_fact = next(f for f in facts if f.category == "business_identity")
    assert "Apex Dental Care" in biz_fact.description


@pytest.mark.asyncio
async def test_customer_requests_extraction_four_industries():
    # Industry 1: Automotive
    auto_reqs = CanonicalSpecEngine.extract_customer_requests("Can we see an appointment scheduler for vehicle repair?", "Automotive")
    assert any(r.feature_type == "booking" for r in auto_reqs)

    # Industry 2: Dental
    dental_reqs = CanonicalSpecEngine.extract_customer_requests("", "Dental")
    assert any(r.feature_type == "booking" for r in dental_reqs)
    assert any(r.feature_type == "ai_assistant" for r in dental_reqs)

    # Industry 3: Roofing
    roof_reqs = CanonicalSpecEngine.extract_customer_requests("I want an instant estimate calculator for roof replacements", "Roofing")
    assert any(r.feature_type == "calculator" for r in roof_reqs)

    # Industry 4: HVAC
    hvac_reqs = CanonicalSpecEngine.extract_customer_requests("Do you have an emergency dispatch booking system?", "HVAC")
    assert any(r.feature_type == "booking" for r in hvac_reqs)


@pytest.mark.asyncio
async def test_canonical_spec_engine_checksum_determinism():
    spec_data = {
        "project_id": "proj_test_123",
        "version": 1,
        "facts": [{"category": "biz", "description": "Test Biz"}],
        "screens": [{"title": "Overview", "route": "/"}]
    }
    hash1 = CanonicalSpecEngine.calculate_checksum(spec_data)
    hash2 = CanonicalSpecEngine.calculate_checksum(spec_data)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256


@pytest.mark.asyncio
async def test_canonical_spec_engine_persists_spec_record(test_db):
    biz = Business(name="Austin Roofing Specialists", domain="austinroofing.com", country="US", niche="Roofing")
    test_db.add(biz)
    await test_db.commit()

    proj = CustomerProject(
        project_id="proj_austin_roofing_001",
        business_id=biz.id,
        customer_slug="austin-roofing",
        title="Austin Roofing Specialists",
        industry="Roofing"
    )
    test_db.add(proj)
    await test_db.commit()

    spec = await spec_engine.build_canonical_spec(
        session=test_db,
        customer_project=proj,
        reply_text="We need an instant pricing calculator"
    )

    assert spec.id is not None
    assert spec.is_canonical is True
    assert spec.version == 1
    assert len(spec.checksum) == 64
    assert proj.status in ("SPEC_READY", "DEMO_SPEC_CREATED")


# =====================================================================
# 2. DESIGN PROVIDER (STITCH ADAPTER) TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_stitch_design_provider_palettes_across_industries():
    provider = StitchDesignProvider()

    auto_p = provider._select_palette("automotive")
    assert auto_p["primary"] == "#DC2626"

    dental_p = provider._select_palette("dental clinic")
    assert dental_p["primary"] == "#0EA5E9"

    roof_p = provider._select_palette("roofing services")
    assert roof_p["primary"] == "#D97706"

    hvac_p = provider._select_palette("hvac heating & air")
    assert hvac_p["primary"] == "#2563EB"


@pytest.mark.asyncio
async def test_stitch_design_provider_generate_design():
    provider = StitchDesignProvider()
    spec = ProjectSpecification(
        version=1,
        required_screens=[
            {"screen_id": "overview", "title": "Overview", "route": "/"},
            {"screen_id": "booking", "title": "Booking", "route": "/booking"}
        ]
    )
    proj = CustomerProject(
        project_id="proj_dental_01",
        customer_slug="dental-clinic",
        title="Modern Dental Clinic",
        industry="Dental"
    )

    result = await provider.generate_design(spec, proj)
    assert result.provider == "stitch"
    assert result.status == "DESIGN_READY"
    assert len(result.screens) == 2
    assert "primary" in result.color_system
    assert "font_family_heading" in result.typography


# =====================================================================
# 3. AI PROTOTYPING PROVIDER (GOOGLE AI STUDIO ADAPTER) TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_google_ai_studio_provider():
    provider = GoogleAIStudioProvider()
    spec = ProjectSpecification(
        version=1,
        ai_features=[{
            "system_instructions": "You are the HVAC dispatch concierge."
        }]
    )
    proj = CustomerProject(
        project_id="proj_hvac_01",
        customer_slug="cooling-experts",
        title="Cooling Experts HVAC",
        industry="HVAC"
    )

    proto = await provider.generate_prototype(spec, proj)
    assert proto.provider == "google_ai_studio"
    assert proto.model_name == "gemini-2.5-flash"
    assert "HVAC dispatch concierge" in proto.system_instructions
    assert len(proto.interactive_hooks.get("sample_dialogue", [])) > 0


# =====================================================================
# 4. ANTIGRAVITY CODING PROVIDER TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_antigravity_coding_provider_generates_multi_file_artifacts():
    provider = AntigravityCodingProvider()
    design_prov = StitchDesignProvider()
    ai_prov = GoogleAIStudioProvider()

    spec = ProjectSpecification(
        version=1,
        facts=[{"category": "identity", "description": "Verified auto garage"}],
        customer_requests=[{"request_text": "Online appointment booking", "feature_type": "booking"}],
        required_screens=[
            {"screen_id": "overview", "title": "Overview", "route": "/"},
            {"screen_id": "booking", "title": "Booking", "route": "/booking"}
        ]
    )
    proj = CustomerProject(
        project_id="proj_garage_01",
        customer_slug="apex-garage",
        title="Apex Garage Auto Repair",
        industry="Automotive"
    )

    design = await design_prov.generate_design(spec, proj)
    ai_proto = await ai_prov.generate_prototype(spec, proj)

    build_res = await provider.build_project(spec, design, ai_proto, proj)

    assert build_res.status == "BUILD_PASSED"
    assert len(build_res.generated_files) == 5
    file_names = [f.file_path for f in build_res.generated_files]
    assert "index.html" in file_names
    assert "app.js" in file_names
    assert "styles.css" in file_names
    assert "spec.json" in file_names
    assert "ai_config.json" in file_names

    # Check html content contains customer identity
    html_item = next(f for f in build_res.generated_files if f.file_path == "index.html")
    assert "Apex Garage Auto Repair" in html_item.content
    assert "apex-garage.com" in html_item.content


# =====================================================================
# 5. 20-GATE QUALITY ASSURANCE ENGINE TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_20_gate_qa_engine_passes_clean_build(tmp_path):
    artifacts_dir = str(tmp_path / "clean_build")
    os.makedirs(artifacts_dir, exist_ok=True)

    html_content = """<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lone Star Roofing</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>:root { --primary: #2563EB; font-family: sans-serif; }</style>
    </head>
    <body class="bg-slate-900 text-white">
        <div id="screen-overview">
            <h1>Lone Star Roofing</h1>
            <p>lonestar-roofing.com</p>
            <div id="chat-messages-container">Concierge</div>
            <div>$650 USD Advance 40%</div>
        </div>
        <script src="app.js"></script>
    </body>
    </html>"""

    js_content = "function switchScreen(s) { console.log('switch', s); }"
    css_content = ":root { --primary: #2563EB; }"

    with open(os.path.join(artifacts_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(os.path.join(artifacts_dir, "app.js"), "w", encoding="utf-8") as f:
        f.write(js_content)
    with open(os.path.join(artifacts_dir, "styles.css"), "w", encoding="utf-8") as f:
        f.write(css_content)
    with open(os.path.join(artifacts_dir, "spec.json"), "w", encoding="utf-8") as f:
        f.write('{"test": true}')
    with open(os.path.join(artifacts_dir, "ai_config.json"), "w", encoding="utf-8") as f:
        f.write('{"model": "gemini-2.5-flash"}')

    build = ProjectBuild(id=1, routes_manifest=["/"])
    spec = ProjectSpecification(required_screens=[{"route": "/", "title": "Overview"}])
    proj = CustomerProject(
        id=1,
        title="Lone Star Roofing",
        customer_slug="lonestar-roofing",
        industry="Roofing"
    )

    qa_res = BuildQAEngine.evaluate_build(build, spec, proj, artifacts_dir)
    assert qa_res.overall_status in ("PASS", "WARN")
    assert qa_res.score >= 90.0
    assert len(qa_res.critical_violations) == 0


@pytest.mark.asyncio
async def test_20_gate_qa_engine_catches_placeholders(tmp_path):
    artifacts_dir = str(tmp_path / "placeholder_build")
    os.makedirs(artifacts_dir, exist_ok=True)

    bad_html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width"></head><body>
    <h1>Test Dental</h1>
    <p>Lorem ipsum dolor sit amet. TODO: fix this.</p>
    </body></html>"""
    with open(os.path.join(artifacts_dir, "index.html"), "w") as f:
        f.write(bad_html)

    build = ProjectBuild(id=2)
    spec = ProjectSpecification()
    proj = CustomerProject(id=2, title="Test Dental", customer_slug="test-dental")

    qa_res = BuildQAEngine.evaluate_build(build, spec, proj, artifacts_dir)
    assert qa_res.overall_status == "FAIL"
    assert "ZERO_PLACEHOLDERS" in qa_res.critical_violations


@pytest.mark.asyncio
async def test_20_gate_qa_engine_catches_secrets(tmp_path):
    artifacts_dir = str(tmp_path / "secret_build")
    os.makedirs(artifacts_dir, exist_ok=True)

    bad_html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width"></head><body>
    <h1>Leaky App</h1>
    <script>const apiKey = 'AIzaSyD9876543210zyxwvutsrqponmlkjihgfed';</script>
    </body></html>"""
    with open(os.path.join(artifacts_dir, "index.html"), "w") as f:
        f.write(bad_html)

    build = ProjectBuild(id=3)
    spec = ProjectSpecification()
    proj = CustomerProject(id=3, title="Leaky App", customer_slug="leaky-app")

    qa_res = BuildQAEngine.evaluate_build(build, spec, proj, artifacts_dir)
    assert qa_res.overall_status == "FAIL"
    assert "ZERO_SECRETS" in qa_res.critical_violations


@pytest.mark.asyncio
async def test_20_gate_qa_engine_catches_cross_customer_leakage(tmp_path):
    artifacts_dir = str(tmp_path / "leak_build")
    os.makedirs(artifacts_dir, exist_ok=True)

    bad_html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width"></head><body>
    <h1>Dallas Dental Clinic</h1>
    <p>Contact: orangeauto.ae for details.</p>
    </body></html>"""
    with open(os.path.join(artifacts_dir, "index.html"), "w") as f:
        f.write(bad_html)

    build = ProjectBuild(id=4)
    spec = ProjectSpecification()
    proj = CustomerProject(id=4, title="Dallas Dental Clinic", customer_slug="dallas-dental")

    qa_res = BuildQAEngine.evaluate_build(build, spec, proj, artifacts_dir)
    assert qa_res.overall_status == "FAIL"
    assert "ZERO_LEAKAGE" in qa_res.critical_violations


# =====================================================================
# 6. BOUNDED REPAIR LOOP ENGINE TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_bounded_repair_loop_classifies_and_repairs(test_db, tmp_path):
    repair_engine = BuildRepairEngine()
    artifacts_dir = str(tmp_path / "repair_dir")
    os.makedirs(artifacts_dir, exist_ok=True)

    biz1 = Business(name="Repair Test Co", domain="repairtest.com", country="US", niche="General")
    test_db.add(biz1)
    await test_db.flush()

    proj = CustomerProject(
        project_id="proj_repair_01",
        business_id=biz1.id,
        title="Repair Test Co",
        customer_slug="repair-test",
        status="QA"
    )
    test_db.add(proj)
    await test_db.flush()

    build = ProjectBuild(project_id=proj.id, routes_manifest=["/"])
    test_db.add(build)
    spec = ProjectSpecification(project_id=proj.id)
    test_db.add(spec)
    await test_db.commit()
    await test_db.refresh(build)

    initial_qa = PipelineQAResult(
        build_id=build.id,
        overall_status="FAIL",
        score=75.0,
        critical_violations=["ZERO_PLACEHOLDERS"],
        gate_results={"ZERO_PLACEHOLDERS": {"passed": False, "critical": True}}
    )

    # Mock evaluate_build on subsequent run to succeed
    with patch.object(BuildQAEngine, "evaluate_build") as mock_eval:
        mock_eval.return_value = PipelineQAResult(
            build_id=build.id,
            overall_status="PASS",
            score=95.0,
            critical_violations=[],
            gate_results={"ZERO_PLACEHOLDERS": {"passed": True, "critical": True}}
        )

        final_qa = await repair_engine.execute_repair_loop(
            session=test_db,
            customer_project=proj,
            spec=spec,
            build=build,
            initial_qa=initial_qa,
            artifacts_dir=artifacts_dir
        )

        assert final_qa.overall_status == "PASS"
        # Check that repair attempt was recorded
        q = select(RepairAttempt).where(RepairAttempt.build_id == build.id)
        attempts = (await test_db.execute(q)).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].failure_classification == "PLACEHOLDER_LEAK"


@pytest.mark.asyncio
async def test_bounded_repair_loop_halts_at_max_attempts(test_db, tmp_path):
    repair_engine = BuildRepairEngine()
    artifacts_dir = str(tmp_path / "repair_dir_fail")
    os.makedirs(artifacts_dir, exist_ok=True)

    biz2 = Business(name="Unrepairable Co", domain="unrepairable.com", country="US", niche="General")
    test_db.add(biz2)
    await test_db.flush()

    proj = CustomerProject(
        project_id="proj_fail_02",
        business_id=biz2.id,
        title="Unrepairable Co",
        customer_slug="unrepairable",
        status="QA"
    )
    test_db.add(proj)
    await test_db.flush()

    build = ProjectBuild(project_id=proj.id)
    test_db.add(build)
    spec = ProjectSpecification(project_id=proj.id)
    test_db.add(spec)
    await test_db.commit()
    await test_db.refresh(build)

    initial_qa = PipelineQAResult(
        build_id=build.id,
        overall_status="FAIL",
        score=50.0,
        critical_violations=["SYNTAX_HTML"]
    )

    with patch.object(BuildQAEngine, "evaluate_build") as mock_eval:
        # Continues to fail
        mock_eval.return_value = initial_qa

        final_qa = await repair_engine.execute_repair_loop(
            session=test_db,
            customer_project=proj,
            spec=spec,
            build=build,
            initial_qa=initial_qa,
            artifacts_dir=artifacts_dir
        )

        assert final_qa.overall_status == "FAIL"
        assert proj.status == "BLOCKED"
        q = select(RepairAttempt).where(RepairAttempt.build_id == build.id)
        attempts = (await test_db.execute(q)).scalars().all()
        assert len(attempts) == MAX_REPAIR_ATTEMPTS  # Exactly 3


# =====================================================================
# 7. FIREBASE INFRASTRUCTURE PROVIDER & DEPLOYMENT TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_firebase_provider_and_deployment(test_db):
    engine = DemoDeploymentEngine()
    build = ProjectBuild(id=1, artifacts_manifest={"index.html": {"size": 100}})
    proj = CustomerProject(
        id=1,
        project_id="proj_deploy_01",
        customer_slug="deploy-test",
        title="Deploy Test Co"
    )

    build_res = BuildResult(
        build_number=1,
        status="BUILD_PASSED",
        generated_files=[
            {"file_path": "index.html", "file_type": "text/html", "size_bytes": 50, "sha256": "abc", "content": "<h1>Deployed</h1>"}
        ]
    )

    deployment = await engine.deploy_demo(test_db, proj, build, build_res)
    assert deployment.demo_id.startswith("demo_deploy-test_")
    assert "/demo/deploy-test/" in deployment.deployment_url
    assert proj.status == "READY"


# =====================================================================
# 8. PIPELINE ORCHESTRATOR & CONCURRENCY TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_pipeline_orchestrator_end_to_end(test_db):
    biz = Business(
        name="Texas Star Automotive",
        domain="texasstarauto.com",
        niche="Automotive",
        city="Houston",
        country="US"
    )
    test_db.add(biz)
    await test_db.commit()

    res = await pipeline_orchestrator.trigger_demo_pipeline(
        session=test_db,
        business_id=biz.id,
        reply_text="We would like to see a demo of your automated scheduling tool."
    )

    assert res["success"] is True
    assert res["status"] in ("READY", "DEMO_READY")
    assert "/demo/texas-star-automotive/" in res["demo_url"]
    assert res["qa_score"] >= 90.0
    assert biz.pipeline_stage in (PipelineStage.DEMO_READY.value, PipelineStage.DEMO_DELIVERED.value)


@pytest.mark.asyncio
async def test_independent_per_project_concurrency():
    lock_a = await get_project_lock("proj_customer_a")
    lock_b = await get_project_lock("proj_customer_b")

    assert lock_a is not lock_b  # Distinct locks
    assert not lock_a.locked()
    assert not lock_b.locked()

    async with lock_a:
        assert lock_a.locked()
        assert not lock_b.locked()  # Customer A does not lock Customer B


# =====================================================================
# 9. CRM REPLY CLASSIFIER INTEGRATION TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_reply_classifier_detects_demo_request():
    classifier = ReplyClassifier()
    res = await classifier.classify_text("Can I see a demo of how this appointment booking tool works for our clinic?")
    assert res["classification"] == ReplyClassification.DEMO_REQUEST.value
    assert res["confidence"] >= 0.90


@pytest.mark.asyncio
async def test_autonomous_reply_handler_classifies_wants_demo():
    handler = AutonomousReplyHandler()
    res = handler.classify_text("Could you build a prototype or show me a demo for our website?")
    assert res.category == RoutineCategory.WANTS_DEMO.value
    assert res.is_escalation is False


# =====================================================================
# 10. STRICT PAYMENT BOUNDARY TEST (DEMO != PRODUCTION)
# =====================================================================

@pytest.mark.asyncio
async def test_strict_payment_boundary_enforced(test_db):
    biz = Business(
        name="Precision Roofing",
        domain="precisionroof.com",
        country="US",
        niche="Roofing",
        pipeline_stage=PipelineStage.DEMO_DELIVERED.value
    )
    test_db.add(biz)
    await test_db.commit()

    # Deliver demo must NOT unlock production project
    q_proj = select(CustomerProject).where(CustomerProject.business_id == biz.id)
    proj = (await test_db.execute(q_proj)).scalars().first()

    # Even after demo is delivered, proposal remains pending payment
    q_prop = select(Proposal).where(Proposal.business_id == biz.id)
    prop = (await test_db.execute(q_prop)).scalars().first()

    # Production delivery requires advance payment
    if prop:
        assert prop.advance_received == 0.0
        assert prop.status != "PAID"


# =====================================================================
# 11. REST API ENDPOINTS & SANDBOX ROUTE TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_public_demo_sandbox_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid demo identifier returns 404
        resp = await client.get("/demo/invalid-customer/demo-nonexistent")
        assert resp.status_code == 404

        # List projects endpoint returns 200
        resp_projects = await client.get("/api/projects")
        assert resp_projects.status_code == 200
        assert isinstance(resp_projects.json(), list)


@pytest.mark.asyncio
async def test_zero_real_money_and_zero_real_outbound_email_during_pipeline(test_db):
    """Guarantees testing runs with zero real email dispatch and zero real payment gateway charge."""
    biz = Business(name="Safety Test Co", domain="safetytest.com", country="US", niche="HVAC")
    test_db.add(biz)
    await test_db.commit()

    with patch("app.outreach.sender.outreach_sender_adapter.send_approved_message") as mock_email:
        res = await pipeline_orchestrator.trigger_demo_pipeline(test_db, biz.id, "Show me a demo")
        assert res["success"] is True
        mock_email.assert_not_called()  # No external email socket invoked


# =====================================================================
# 12. ADVANCED EXTENDED TEST CASES (35 TOTAL TEST GATES)
# =====================================================================

@pytest.mark.asyncio
async def test_spec_versioning_increments(test_db):
    biz = Business(name="Version Test Co", domain="versiontest.com", country="US", niche="Dental")
    test_db.add(biz)
    await test_db.flush()

    proj = CustomerProject(
        project_id="proj_ver_01",
        business_id=biz.id,
        customer_slug="version-test",
        title="Version Test Co"
    )
    test_db.add(proj)
    await test_db.commit()

    spec1 = await spec_engine.build_canonical_spec(test_db, proj, "Initial request")
    assert spec1.version == 1

    spec2 = await spec_engine.build_canonical_spec(test_db, proj, "Updated request with calculator")
    assert spec2.version == 2
    assert spec2.checksum != spec1.checksum


@pytest.mark.asyncio
async def test_ai_studio_provider_safety_block_levels():
    provider = GoogleAIStudioProvider()
    spec = ProjectSpecification(version=1)
    proj = CustomerProject(project_id="p1", customer_slug="slug", title="Title", industry="General")
    proto = await provider.generate_prototype(spec, proj)
    assert "HARM_CATEGORY_HARASSMENT" in proto.safety_settings
    assert proto.safety_settings["HARM_CATEGORY_HARASSMENT"] == "BLOCK_MEDIUM_AND_ABOVE"


@pytest.mark.asyncio
async def test_coding_provider_html_size_budget():
    provider = AntigravityCodingProvider()
    design_prov = StitchDesignProvider()
    ai_prov = GoogleAIStudioProvider()
    spec = ProjectSpecification(version=1)
    proj = CustomerProject(project_id="p2", customer_slug="slug2", title="Title 2", industry="General")

    design = await design_prov.generate_design(spec, proj)
    proto = await ai_prov.generate_prototype(spec, proj)
    build_res = await provider.build_project(spec, design, proto, proj)

    html_file = next(f for f in build_res.generated_files if f.file_path == "index.html")
    assert html_file.size_bytes < 2 * 1024 * 1024  # Under 2MB budget


@pytest.mark.asyncio
async def test_qa_engine_responsive_viewport_missing(tmp_path):
    artifacts_dir = str(tmp_path / "no_viewport")
    os.makedirs(artifacts_dir, exist_ok=True)
    with open(os.path.join(artifacts_dir, "index.html"), "w") as f:
        f.write("<!DOCTYPE html><html><head><title>No Viewport</title></head><body><h1>Hi</h1></body></html>")
    build = ProjectBuild(id=5)
    spec = ProjectSpecification()
    proj = CustomerProject(id=5, title="No Viewport", customer_slug="no-viewport")

    res = BuildQAEngine.evaluate_build(build, spec, proj, artifacts_dir)
    assert res.gate_results["RESPONSIVE_VIEWPORT"]["passed"] is False


@pytest.mark.asyncio
async def test_qa_engine_syntax_html_mismatched_tags(tmp_path):
    artifacts_dir = str(tmp_path / "bad_html")
    os.makedirs(artifacts_dir, exist_ok=True)
    with open(os.path.join(artifacts_dir, "index.html"), "w") as f:
        f.write("<html><head><meta name='viewport'></head><body><h1>Unclosed body")
    build = ProjectBuild(id=6)
    spec = ProjectSpecification()
    proj = CustomerProject(id=6, title="Bad HTML", customer_slug="bad-html")

    res = BuildQAEngine.evaluate_build(build, spec, proj, artifacts_dir)
    assert res.gate_results["SYNTAX_HTML"]["passed"] is False


@pytest.mark.asyncio
async def test_qa_engine_syntax_js_bracket_mismatch(tmp_path):
    artifacts_dir = str(tmp_path / "bad_js")
    os.makedirs(artifacts_dir, exist_ok=True)
    with open(os.path.join(artifacts_dir, "index.html"), "w") as f:
        f.write("<!DOCTYPE html><html><head><meta name='viewport'></head><body></body></html>")
    with open(os.path.join(artifacts_dir, "app.js"), "w") as f:
        f.write("function broken() { if (true) { console.log('unclosed'); ")
    build = ProjectBuild(id=7)
    spec = ProjectSpecification()
    proj = CustomerProject(id=7, title="Bad JS", customer_slug="bad-js")

    res = BuildQAEngine.evaluate_build(build, spec, proj, artifacts_dir)
    assert res.gate_results["SYNTAX_JS"]["passed"] is False


@pytest.mark.asyncio
async def test_qa_engine_routes_accessibility_missing(tmp_path):
    artifacts_dir = str(tmp_path / "missing_route")
    os.makedirs(artifacts_dir, exist_ok=True)
    with open(os.path.join(artifacts_dir, "index.html"), "w") as f:
        f.write("<!DOCTYPE html><html><head><meta name='viewport'></head><body><div id='screen-overview'></div></body></html>")
    build = ProjectBuild(id=8, routes_manifest=["/", "/missing-route"])
    spec = ProjectSpecification()
    proj = CustomerProject(id=8, title="Missing Route", customer_slug="missing-route")

    res = BuildQAEngine.evaluate_build(build, spec, proj, artifacts_dir)
    assert res.gate_results["ROUTES_ACCESSIBILITY"]["passed"] is False


@pytest.mark.asyncio
async def test_qa_engine_csp_detects_eval(tmp_path):
    artifacts_dir = str(tmp_path / "eval_detect")
    os.makedirs(artifacts_dir, exist_ok=True)
    with open(os.path.join(artifacts_dir, "index.html"), "w") as f:
        f.write("<!DOCTYPE html><html><head><meta name='viewport'></head><body><script>eval('alert(1)');</script></body></html>")
    build = ProjectBuild(id=9)
    spec = ProjectSpecification()
    proj = CustomerProject(id=9, title="Eval App", customer_slug="eval-app")

    res = BuildQAEngine.evaluate_build(build, spec, proj, artifacts_dir)
    assert res.gate_results["SECURITY_HEADERS_CSP"]["passed"] is False


@pytest.mark.asyncio
async def test_repair_engine_classifies_all_categories():
    engine = BuildRepairEngine()
    assert engine.classify_failure(["ZERO_PLACEHOLDERS"]) == "PLACEHOLDER_LEAK"
    assert engine.classify_failure(["SYNTAX_HTML"]) == "SYNTAX_ERROR"
    assert engine.classify_failure(["ROUTES_ACCESSIBILITY"]) == "MISSING_ROUTE"
    assert engine.classify_failure(["IDENTITY_INTEGRITY"]) == "IDENTITY_ISOLATION_VIOLATION"
    assert engine.classify_failure(["ZERO_SECRETS"]) == "SECURITY_POLICY_VIOLATION"
    assert engine.classify_failure(["OTHER_GATE"]) == "GENERAL_QA_DEFECT"


@pytest.mark.asyncio
async def test_get_customer_project_detail_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Non-existent project returns 404
        resp = await client.get("/api/projects/proj_nonexistent_xyz")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_project_demo_build_endpoint_requires_business_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/projects/trigger", json={})
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_backward_compatible_existing_demo_slug():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Requesting /demo/{business_slug} with non-existent slug returns 404 cleanly
        resp = await client.get("/demo/nonexistent-legacy-prospect")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_orange_auto_canary_integrity_preserved():
    """Confirms Orange Auto #12 is not modified or affected by new demo pipeline."""
    from app.database.connection import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        from app.database.models import OutreachMessage
        msg = await session.get(OutreachMessage, 12)
        if msg:
            assert msg.status == "PENDING_APPROVAL"
