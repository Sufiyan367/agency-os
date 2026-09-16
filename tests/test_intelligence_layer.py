"""
Agency OS — Comprehensive Test Suite for Real Intelligence Layer.
Verifies Persistent Knowledge Model, Epistemic Separation, Structured Research,
Opportunity Engine, Solution Capability Catalog, N8N Intelligence & Empirical Learning Loop,
Demo Factory Tool Selection, Bounded Self-Repair Policy, Strict Commercial Gate Enforcement,
and Operator Feedback & Downstream Outcome Tracing.
"""

import pytest
import pytest_asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, Payment, KnowledgeFact, WorkflowExecutionLog,
    OperatorFeedbackLog, OutcomeTrace, PipelineStage
)
from app.intelligence.knowledge_model import (
    Observation, Inference, Recommendation, ExplainableIntelligence,
    SourceTier, store_fact, get_facts_for_entity, calculate_source_confidence
)
from app.intelligence.capability_catalog import capability_catalog, SolutionCapability
from app.intelligence.structured_research import structured_research_engine
from app.intelligence.opportunity_engine import opportunity_engine
from app.intelligence.n8n_intelligence import n8n_intelligence_engine
from app.intelligence.tool_selector import demo_tool_selector, ToolType
from app.intelligence.operator_learning import (
    operator_learning_engine, CommercialGateViolation
)
from app.builder.models import CanonicalSpec
from app.builder.pipeline import pipeline_orchestrator


@pytest.mark.asyncio
async def test_persistent_knowledge_model_and_provenance():
    """Verifies that atomic facts are stored with verifiable provenance and epistemic status."""
    async with AsyncSessionLocal() as session:
        obs = Observation(
            entity_type="business",
            entity_id="101",
            category="tech_stack",
            fact_key="cms_platform",
            fact_value={"platform": "WordPress", "version": "6.4.2"},
            source="wappalyzer_probe",
            source_tier=SourceTier.DIRECT_HTTP_AUDIT,
            raw_evidence="Meta generator tag matched 'WordPress 6.4.2'",
            provenance={"url": "https://sample-client.com", "run_id": "run_audit_001"}
        )

        assert obs.confidence == 0.95
        assert calculate_source_confidence(SourceTier.OFFICIAL_DNS_REGISTRY) == 0.99
        assert calculate_source_confidence(SourceTier.SCRAPED_CONTENT) == 0.85

        saved_fact = await store_fact(session, obs)
        assert saved_fact.id is not None
        assert saved_fact.entity_id == "101"
        assert saved_fact.category == "tech_stack"
        assert saved_fact.fact_key == "cms_platform"
        assert saved_fact.epistemic_status == "OBSERVED_FACT"
        assert saved_fact.confidence == 0.95

        fetched = await get_facts_for_entity(session, "business", "101")
        assert len(fetched) >= 1
        assert fetched[0].fact_value["platform"] == "WordPress"


@pytest.mark.asyncio
async def test_structured_research_engine_epistemic_separation():
    """Verifies clear separation of Observation vs Inference vs Recommendation with explainability."""
    audit_data = {
        "http_status": 200,
        "tech_stack": ["WordPress", "Gravity Forms"],
        "performance_score": 45.0,
        "ux_conversion_score": 48.0
    }
    res = structured_research_engine.analyze_business_research(
        business_id=202,
        domain="dallasplumbingpros.com",
        business_name="Dallas Plumbing Pros",
        niche="Plumbing Services",
        audit_data=audit_data
    )

    observations = res["observations"]
    inferences = res["inferences"]
    recommendations = res["recommendations"]
    explainable: ExplainableIntelligence = res["explainable_summary"]

    assert len(observations) >= 4
    assert any(o.fact_key == "domain_active" for o in observations)
    assert any(o.fact_key == "booking_mechanism" for o in observations)

    assert len(inferences) >= 1
    assert any("friction" in inf.category or "conversion" in inf.category for inf in inferences)
    for inf in inferences:
        assert len(inf.supporting_observation_keys) > 0
        assert inf.confidence > 0.0

    assert len(recommendations) >= 1
    top_rec = recommendations[0]
    assert top_rec.target_price_usd >= 500.0

    assert explainable.observation != ""
    assert explainable.belief != ""
    assert explainable.rationale != ""
    assert explainable.recommendation != ""
    assert len(explainable.evidence) >= 4
    assert explainable.confidence > 0.60
    assert explainable.ceo_gate_required is False


@pytest.mark.asyncio
async def test_opportunity_engine_and_catalog_mapping():
    """Verifies that research inferences convert into high-margin commercial opportunities."""
    research_res = structured_research_engine.analyze_business_research(
        business_id=303,
        domain="austinroofdoctors.com",
        business_name="Austin Roof Doctors",
        niche="Roofing Services",
        audit_data={"http_status": 200, "tech_stack": ["WordPress"], "performance_score": 40.0}
    )

    opp = opportunity_engine.generate_opportunity(research_res)

    assert opp.business_id == 303
    assert opp.domain == "austinroofdoctors.com"
    assert opp.deal_value_usd >= 500.0, "Violates commercial pricing floor"
    assert opp.advance_required_usd == round(opp.deal_value_usd * 0.40, 2)
    assert opp.p_win_estimate >= 0.40
    assert opp.roi_estimate["roi_multiple"] >= 1.0

    opp_dict = opp.to_dict()
    assert "capability_id" in opp_dict
    assert "explainable_summary" in opp_dict
    assert opp_dict["decision_trace"]["pricing_floor_enforced"] is True


@pytest.mark.asyncio
async def test_n8n_intelligence_selection_ranking_and_composition():
    """Verifies capability matching, license gating, secret scanning, and pipeline composition."""
    async with AsyncSessionLocal() as session:
        candidates = await n8n_intelligence_engine.select_and_rank_workflows(session)
        assert len(candidates) > 0

        # All candidates must have permissible licenses and clean security
        for cand in candidates:
            assert cand.license_status in ("LICENSE_ALLOWED", "LICENSE_REQUIRES_ATTRIBUTION")
            assert cand.security_status == "SECURITY_PASSED"
            assert cand.overall_rank_score > 0.0

        # Test multi-workflow composition
        composed = n8n_intelligence_engine.compose_workflow_pipeline(candidates[:2])
        assert composed["total_stages"] == 2
        assert composed["status"] == "COMPOSITION_READY"
        assert composed["data_contracts_validated"] is True


@pytest.mark.asyncio
async def test_n8n_empirical_telemetry_and_bayesian_learning():
    """Verifies that execution telemetry logs update empirical success probabilities without hallucination."""
    async with AsyncSessionLocal() as session:
        test_template = "AGY-SCORE-LeadQualification-CommercialFloor-v1.0"

        # Initially, prior is Beta(1,1) -> (0+1)/(0+2) = 0.50
        baseline_perf = await n8n_intelligence_engine.get_empirical_performance(session, test_template)

        # Log 3 successful executions
        for _ in range(3):
            await n8n_intelligence_engine.log_execution(
                session=session,
                workflow_name="Lead Qualification Engine",
                template_id=test_template,
                execution_status="SUCCESS",
                duration_ms=145.0
            )

        # Log 1 failed execution
        await n8n_intelligence_engine.log_execution(
            session=session,
            workflow_name="Lead Qualification Engine",
            template_id=test_template,
            execution_status="FAILURE",
            duration_ms=210.0,
            failure_category="TIMEOUT",
            error_message="Gateway timeout waiting for upstream CRM"
        )

        updated_perf = await n8n_intelligence_engine.get_empirical_performance(session, test_template)
        assert updated_perf["total_runs"] >= 4
        assert updated_perf["successes"] >= 3
        assert updated_perf["failures"] >= 1
        assert updated_perf["avg_duration_ms"] > 0.0

        # Check empirical smoothed probability (successes+1)/(total+2)
        expected_smoothed = (updated_perf["successes"] + 1.0) / (updated_perf["total_runs"] + 2.0)
        assert abs(updated_perf["smoothed_p_success"] - expected_smoothed) < 0.001


@pytest.mark.asyncio
async def test_demo_factory_tool_selection_and_plan():
    """Verifies intelligent tool assignment across Stitch, Gemini, Antigravity, and Firebase."""
    spec = CanonicalSpec(
        project_id="proj_solar_789",
        customer_slug="sunburst-solar",
        business_name="Sunburst Solar",
        domain="sunburstsolar.com",
        industry="Solar Installation",
        version=1,
        customer={"slug": "sunburst-solar", "project_id": "proj_solar_789"},
        business={"name": "Sunburst Solar", "domain": "sunburstsolar.com", "industry": "Solar Installation"},
        problem="Homeowners need instant solar savings calculations.",
        requirements=["Online Solar ROI Estimator", "24/7 Dispatch Booking"],
        required_pages=[
            {"screen_id": "home", "title": "Overview", "route": "/"},
            {"screen_id": "calculator", "title": "Solar Calculator", "route": "/calculator"}
        ],
        required_features=[
            {"feature_id": "solar_quote_bot", "name": "Instant Quote Concierge"}
        ],
        integrations=["fastapi", "gemini_ai", "firebase_auth"],
        constraints=["mobile-first"],
        success_criteria=["Sub-second paint", "Pass 20 QA gates"]
    )

    plan = demo_tool_selector.generate_demo_plan(spec)

    assert plan.project_id == "proj_solar_789"
    assert ToolType.STITCH in plan.tool_allocations
    assert "/" in plan.tool_allocations[ToolType.STITCH]
    assert "/calculator" in plan.tool_allocations[ToolType.STITCH]

    assert ToolType.GEMINI in plan.tool_allocations
    assert "solar_quote_bot" in plan.tool_allocations[ToolType.GEMINI]

    assert ToolType.ANTIGRAVITY in plan.tool_allocations
    assert "fastapi_backend_routes" in plan.tool_allocations[ToolType.ANTIGRAVITY]

    assert ToolType.FIREBASE in plan.tool_allocations
    assert len(plan.tool_allocations[ToolType.FIREBASE]) > 0

    assert plan.bounded_repair_limit == 3
    assert "CEO_REQUIRED" in plan.ceo_gate_escalation_rule


@pytest.mark.asyncio
async def test_commercial_gate_enforcement():
    """
    Verifies strict commercial gate:
    Production build is BLOCKED until advance or full payment is verified.
    """
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Apex Electricians",
            domain="apexelectric.com",
            country="United States",
            niche="Electricians",
            pipeline_stage=PipelineStage.DEMO_READY.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # 1. Attempt production build without verified payment -> Must raise CommercialGateViolation
        with pytest.raises(CommercialGateViolation) as exc_info:
            await pipeline_orchestrator.authorize_production_build(
                session=session,
                business_id=biz.id,
                project_id=1
            )
        assert "Commercial Gate Enforced" in str(exc_info.value)
        assert "Advance payment has not been received and verified" in str(exc_info.value)

        # 2. Add verified advance payment
        payment = Payment(
            business_id=biz.id,
            amount=400.0,
            currency="USD",
            payment_type="ADVANCE",
            status="COMPLETED",
            reference_id="ref_pay_apex_001"
        )
        session.add(payment)
        await session.commit()

        # 3. Re-attempt production build -> Commercial gate opens
        authorized = await pipeline_orchestrator.authorize_production_build(
            session=session,
            business_id=biz.id,
            project_id=1
        )
        assert authorized is True


@pytest.mark.asyncio
async def test_operator_feedback_and_downstream_outcome_tracing():
    """Verifies that human operator decisions and commercial revenue outcomes are recorded."""
    async with AsyncSessionLocal() as session:
        # 1. Record operator feedback
        feedback = await operator_learning_engine.record_feedback(
            session=session,
            entity_type="business",
            entity_id="404",
            stage="OPPORTUNITY_SELECTION",
            system_recommendation={"service_id": "CAP-002", "price_usd": 1200.0},
            operator_decision="MODIFIED",
            operator_reason="Adjusted price from $1200 to $1400 based on multi-location fleet."
        )
        assert feedback.id is not None
        assert feedback.operator_decision == "MODIFIED"
        assert "fleet" in feedback.operator_reason

        # 2. Trace downstream outcome to revenue
        trace = await operator_learning_engine.trace_commercial_outcome(
            session=session,
            business_id=404,
            lead_source="web_discovery",
            initial_service_recommended="CAP-002-BOOKING-AUTOMATION",
            demo_project_id="proj_apex_404",
            proposal_id=12,
            proposal_amount=1400.0,
            advance_paid=True,
            advance_amount=560.0,
            won=True,
            downstream_revenue=1400.0
        )
        assert trace.id is not None
        assert trace.advance_paid is True
        assert trace.won is True
        assert trace.downstream_revenue == 1400.0
        assert trace.feedback_loop_incorporated is True
