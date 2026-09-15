import pytest
from app.builder.models import (
    CanonicalSpec, RequirementFact, CustomerRequestItem, AIInferenceItem
)
from app.builder.spec_engine import CanonicalSpecEngine
from app.database.models import (
    Business, CustomerProject, ProjectSpecification, PipelineStage, ProjectStatus
)
from app.builder.repair_engine import MAX_REPAIR_ATTEMPTS, BuildRepairEngine


def test_canonical_spec_fields_completeness():
    spec = CanonicalSpec(
        project_id="proj_test_123",
        customer_slug="apex-roofing",
        business_name="Apex Roofing Co",
        domain="apexroofing.com",
        industry="Roofing Services",
        version=1,
        customer={"slug": "apex-roofing", "project_id": "proj_test_123"},
        business={"name": "Apex Roofing Co", "domain": "apexroofing.com", "industry": "Roofing Services"},
        problem="Addressing customer inquiry drop-off through online instant roof cost calculations.",
        requirements=["Online instant roof cost calculator", "Storm damage emergency booking"],
        required_pages=[{"screen_id": "overview", "title": "Overview", "route": "/"}],
        required_features=[{"feature_id": "calculator", "name": "Cost Estimator"}],
        branding={"primary_color": "#2563EB", "font_family": "Inter", "theme": "dark_ops"},
        integrations=["fastapi", "gemini_ai", "sqlite"],
        constraints=["mobile-first", "sub-second paint"],
        success_criteria=["20 QA gates pass", "zero placeholder leak"]
    )

    data = spec.model_dump()
    assert data["customer"]["slug"] == "apex-roofing"
    assert data["business"]["name"] == "Apex Roofing Co"
    assert len(data["requirements"]) == 2
    assert "calculator" in data["required_features"][0]["feature_id"]
    assert "mobile-first" in data["constraints"]
    assert "20 QA gates pass" in data["success_criteria"]


def test_spec_engine_to_canonical_spec():
    proj = CustomerProject(
        project_id="proj_hvac_456",
        business_id=1,
        customer_slug="summit-hvac",
        title="Summit HVAC Solutions",
        industry="HVAC",
        status=ProjectStatus.DEMO_SPEC_CREATED.value,
        current_stage="DEMO_SPEC_CREATED"
    )

    spec_model = ProjectSpecification(
        project_id=1,
        version=1,
        is_canonical=True,
        facts=[{"category": "business_identity", "description": "Verified business: Summit HVAC", "source": "crm"}],
        customer_requests=[{"request_text": "24/7 emergency dispatch scheduler", "feature_type": "booking", "priority": "high"}],
        ai_inferences=[{"inferred_need": "Frictionless scheduling", "recommended_solution": "Multi-step booking stepper", "confidence": 0.95}],
        required_screens=[{"screen_id": "booking", "title": "Online Dispatch", "route": "/booking"}],
        ai_features=[{"feature_id": "intake_assistant", "name": "HVAC Concierge"}],
        checksum="abcd1234ef5678"
    )

    biz = Business(
        id=1,
        name="Summit HVAC Solutions",
        domain="summithvac.com",
        niche="HVAC",
        pipeline_stage=PipelineStage.DEMO_SPEC_CREATED.value
    )

    canonical = CanonicalSpecEngine.to_canonical_spec(spec_model, proj, biz)
    assert canonical.project_id == "proj_hvac_456"
    assert canonical.business_name == "Summit HVAC Solutions"
    assert canonical.industry == "HVAC"
    assert len(canonical.customer_requests) == 1
    assert canonical.customer_requests[0].feature_type == "booking"
    assert canonical.requirements == ["24/7 emergency dispatch scheduler"]
    assert "summit-hvac" in canonical.customer["slug"]


def test_max_repair_attempts_constant():
    assert MAX_REPAIR_ATTEMPTS == 3
    repair_engine = BuildRepairEngine()
    classification = repair_engine.classify_failure(["PLACEHOLDER_LEAK_IN_COMPONENTS"])
    assert classification == "PLACEHOLDER_LEAK"

    classification_route = repair_engine.classify_failure(["CRITICAL_ROUTE_MISSING"])
    assert classification_route == "MISSING_ROUTE"


def test_demo_pipeline_stage_enums():
    required_states = [
        "DEMO_REQUESTED",
        "DEMO_SPEC_CREATED",
        "DEMO_BUILDING",
        "DEMO_BUILD_FAILED",
        "DEMO_QA",
        "DEMO_QA_FAILED",
        "DEMO_DEPLOYING",
        "DEMO_READY",
        "DEMO_DELIVERED"
    ]
    for state in required_states:
        assert state in PipelineStage.__members__
        assert state in ProjectStatus.__members__
