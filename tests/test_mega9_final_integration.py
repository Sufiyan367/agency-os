"""
==============================================================================
MEGA PROMPT 9: FINAL AUTONOMOUS AGENCY INTEGRATION
COMPREHENSIVE TEST SUITE
==============================================================================
Verifies:
1. Canonical 21-state forward progression (DISCOVERED -> RETAINED).
2. Exception states & invalid transition prevention.
3. Bidirectional schema adapters (Business, Customer, Project, SupportIncident).
4. Unified Event Bus publish/subscribe, correlation tracking, and idempotency deduplication.
5. Autonomous Priority Scheduler (Tier 0 SEV-1 > Tier 1 > Tier 2 Sales > Tier 3 > Tier 4 Discovery).
6. Capacity Governor & strict daily outbound canary cap (1/day limit).
7. Backpressure throttling under active SEV-1 incident.
8. Core Unified Orchestrator system status & telemetry aggregation.
9. Orchestrator deterministic next-best-action & lifecycle stepping.
10. End-to-End simulation of a single prospect across all 21 stages.
11. Multi-prospect concurrency: 10 simultaneous independent prospects.
12. Multi-customer concurrency: 4 simultaneous customers with strict data isolation.
13. Failure Matrix: AI provider unavailable fallback to deterministic rules.
14. Failure Matrix: QA gate failure reverts state to BUILDING.
15. Failure Matrix: Payment failure transitions to PAYMENT_FAILED with delivery blocked.
16. Failure Matrix: Deployment failure triggers rollback and halts progression to LIVE.
17. Four-Industry validation configurations (Automotive, Dental, Roofing, HVAC).
18. Unified API Routes (/api/orchestration/status, /capacity, /simulation/run, /api/ceo/unified-control).
19. Production Safety Invariant: Canary #12 strictly untouched (status='APPROVED', sent_at=None).
==============================================================================
"""

import os
import sys
import uuid
import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any

from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, Customer, Project, SupportTicket, CustomerIncident,
    OutreachMessage, PipelineEvent, Payment, Proposal, PipelineStage
)
from app.lifecycle.canonical_lifecycle import (
    CanonicalLifecycleStage, CanonicalTransitionAudit,
    CanonicalLifecycleManager, canonical_lifecycle_manager
)
from app.core.event_bus import AgencyEvent, UnifiedEventBus, event_bus
from app.orchestration.scheduler import (
    JobPriorityTier, ScheduledJob, CapacityReport,
    DeterministicScheduler, deterministic_scheduler
)
from app.orchestrator.unified_orchestrator import UnifiedAgencyOrchestrator, unified_orchestrator
from app.simulation.end_to_end_simulator import (
    EndToEndSimulator, end_to_end_simulator, EndToEndSimulationResult
)


@pytest.mark.asyncio
async def test_01_canonical_forward_21_states_order():
    """1. Test that canonical lifecycle forward flow transitions correctly in sequence."""
    forward_flow = [
        CanonicalLifecycleStage.DISCOVERED,
        CanonicalLifecycleStage.QUALIFIED,
        CanonicalLifecycleStage.PRIORITIZED,
        CanonicalLifecycleStage.CONTACTABLE,
        CanonicalLifecycleStage.OUTREACH_ELIGIBLE,
        CanonicalLifecycleStage.OUTREACH_SENT,
        CanonicalLifecycleStage.RESPONSE_RECEIVED,
        CanonicalLifecycleStage.POSITIVE,
        CanonicalLifecycleStage.DEMO_ELIGIBLE,
        CanonicalLifecycleStage.DEMO_READY,
        CanonicalLifecycleStage.PROPOSAL_READY,
        CanonicalLifecycleStage.PROPOSAL_ACCEPTED,
        CanonicalLifecycleStage.PAYMENT_PENDING,
        CanonicalLifecycleStage.PAYMENT_VERIFIED,
        CanonicalLifecycleStage.DELIVERY_UNLOCKED,
        CanonicalLifecycleStage.ONBOARDING,
        CanonicalLifecycleStage.BUILDING,
        CanonicalLifecycleStage.QA,
        CanonicalLifecycleStage.DEPLOYING,
        CanonicalLifecycleStage.LIVE,
        CanonicalLifecycleStage.RETAINED
    ]
    assert len(forward_flow) == 21
    assert forward_flow[0] == CanonicalLifecycleStage.DISCOVERED
    assert forward_flow[-1] == CanonicalLifecycleStage.RETAINED

    # Test sequential forward validity
    for i in range(len(forward_flow) - 1):
        curr_stage = forward_flow[i]
        next_stage = forward_flow[i + 1]
        valid, msg = canonical_lifecycle_manager.can_transition(curr_stage, next_stage)
        assert valid is True, f"Failed valid transition: {curr_stage.value} -> {next_stage.value}: {msg}"


@pytest.mark.asyncio
async def test_02_invalid_transitions_and_exception_states():
    """2. Test that illegal jumps are rejected and exception state transitions are handled."""
    # Illegal direct jump: DISCOVERED -> LIVE
    valid, msg = canonical_lifecycle_manager.can_transition(CanonicalLifecycleStage.DISCOVERED, CanonicalLifecycleStage.LIVE)
    assert valid is False
    assert "Invalid transition" in msg

    # Illegal direct jump: DISCOVERED -> PAYMENT_PENDING
    valid, _ = canonical_lifecycle_manager.can_transition(CanonicalLifecycleStage.DISCOVERED, CanonicalLifecycleStage.PAYMENT_PENDING)
    assert valid is False

    # Illegal jump: PAYMENT_PENDING -> DELIVERY_UNLOCKED without verified payment
    valid, _ = canonical_lifecycle_manager.can_transition(CanonicalLifecycleStage.PAYMENT_PENDING, CanonicalLifecycleStage.DELIVERY_UNLOCKED)
    assert valid is False

    # Illegal backward jump: LIVE -> DISCOVERED
    valid, _ = canonical_lifecycle_manager.can_transition(CanonicalLifecycleStage.LIVE, CanonicalLifecycleStage.DISCOVERED)
    assert valid is False

    # Valid exception transition: RESPONSE_RECEIVED -> UNSUBSCRIBED
    valid, _ = canonical_lifecycle_manager.can_transition(CanonicalLifecycleStage.RESPONSE_RECEIVED, CanonicalLifecycleStage.UNSUBSCRIBED)
    assert valid is True

    # Valid exception transition: PAYMENT_PENDING -> PAYMENT_FAILED
    valid, _ = canonical_lifecycle_manager.can_transition(CanonicalLifecycleStage.PAYMENT_PENDING, CanonicalLifecycleStage.PAYMENT_FAILED)
    assert valid is True

    # Valid recovery from PAYMENT_FAILED -> PAYMENT_PENDING
    valid, _ = canonical_lifecycle_manager.can_transition(CanonicalLifecycleStage.PAYMENT_FAILED, CanonicalLifecycleStage.PAYMENT_PENDING)
    assert valid is True

    # Valid exception: LIVE -> SUPPORT_INCIDENT
    valid, _ = canonical_lifecycle_manager.can_transition(CanonicalLifecycleStage.LIVE, CanonicalLifecycleStage.SUPPORT_INCIDENT)
    assert valid is True

    # Valid recovery: SUPPORT_INCIDENT -> LIVE
    valid, _ = canonical_lifecycle_manager.can_transition(CanonicalLifecycleStage.SUPPORT_INCIDENT, CanonicalLifecycleStage.LIVE)
    assert valid is True


@pytest.mark.asyncio
async def test_03_bidirectional_adapters():
    """3. Test mapping between legacy DB model fields and canonical lifecycle stages."""
    # Business mapping
    biz_lead = Business(pipeline_stage="DISCOVERED", domain="test-map-1.com", country="AE", niche="Dental")
    assert canonical_lifecycle_manager.map_to_canonical(biz_lead) == CanonicalLifecycleStage.DISCOVERED

    biz_contacted = Business(pipeline_stage="CONTACTED", domain="test-map-2.com", country="AE", niche="Dental")
    assert canonical_lifecycle_manager.map_to_canonical(biz_contacted) == CanonicalLifecycleStage.OUTREACH_SENT

    biz_won = Business(pipeline_stage="WON", domain="test-map-3.com", country="AE", niche="Dental")
    assert canonical_lifecycle_manager.map_to_canonical(biz_won) == CanonicalLifecycleStage.PAYMENT_VERIFIED

    # Customer mapping precedence
    cust_active = Customer(company_name="Active Corp", onboarding_status="LIVE")
    assert canonical_lifecycle_manager.map_to_canonical(biz_won, customer=cust_active) == CanonicalLifecycleStage.LIVE

    cust_building = Customer(company_name="Build Corp", onboarding_status="BUILDING")
    assert canonical_lifecycle_manager.map_to_canonical(biz_won, customer=cust_building) == CanonicalLifecycleStage.BUILDING

    # Active Incident takes highest precedence
    inc_active = CustomerIncident(incident_number="INC-1", title="Down", severity="SEV-1", is_resolved=False)
    assert canonical_lifecycle_manager.map_to_canonical(biz_won, customer=cust_active, active_incident=inc_active) == CanonicalLifecycleStage.SUPPORT_INCIDENT


@pytest.mark.asyncio
async def test_04_event_bus_pub_sub_and_idempotency():
    """4. Test unified event bus publish/subscribe, correlation ID propagation, and idempotency deduplication."""
    bus = UnifiedEventBus()
    received_events = []

    async def handler(event: AgencyEvent):
        received_events.append(event)

    bus.subscribe("LIFECYCLE_TRANSITION", handler)

    # First event
    ev1 = AgencyEvent(
        event_type="LIFECYCLE_TRANSITION",
        entity_type="business",
        entity_id=999,
        correlation_id="corr-test-1",
        idempotency_key="idemp-12345",
        actor="test_runner",
        payload={"from_stage": "DISCOVERED", "to_stage": "QUALIFIED"}
    )
    res1 = await bus.publish(ev1)
    assert res1 is True
    assert len(received_events) == 1

    # Duplicate event with same idempotency_key
    ev2 = AgencyEvent(
        event_type="LIFECYCLE_TRANSITION",
        entity_type="business",
        entity_id=999,
        correlation_id="corr-test-2",
        idempotency_key="idemp-12345",
        actor="test_runner",
        payload={"from_stage": "DISCOVERED", "to_stage": "QUALIFIED"}
    )
    res2 = await bus.publish(ev2)
    # Should be rejected / deduplicated
    assert res2 is False
    assert len(received_events) == 1

    # Query event history
    history = bus.get_history(limit=10)
    assert len(history) == 1
    assert history[0].correlation_id == "corr-test-1"


@pytest.mark.asyncio
async def test_05_priority_scheduler_and_ordering():
    """5. Test deterministic priority scheduler ordering (SEV-1 > SEV-2 > Sales > Discovery)."""
    scheduler = DeterministicScheduler()

    # Enqueue in reverse priority order
    j_disc = ScheduledJob(
        priority_tier=JobPriorityTier.BACKGROUND_DISCOVERY,
        job_type="discovery_sweep",
        entity_type="niche",
        entity_id=1,
        commercial_value_usd=0.0
    )
    j_sales = ScheduledJob(
        priority_tier=JobPriorityTier.COMMERCIAL_SALES,
        job_type="generate_proposal",
        entity_type="business",
        entity_id=101,
        commercial_value_usd=5000.0
    )
    j_sev2 = ScheduledJob(
        priority_tier=JobPriorityTier.HIGH_SEV2_PAYMENT,
        job_type="unlock_delivery",
        entity_type="payment",
        entity_id=202,
        commercial_value_usd=2500.0
    )
    j_sev1 = ScheduledJob(
        priority_tier=JobPriorityTier.CRITICAL_SEV1,
        job_type="hotfix_incident",
        entity_type="incident",
        entity_id=303,
        commercial_value_usd=10000.0
    )

    scheduler.enqueue(j_disc)
    scheduler.enqueue(j_sales)
    scheduler.enqueue(j_sev2)
    scheduler.enqueue(j_sev1)

    assert len(scheduler.get_queued_jobs()) == 4

    # Capacity report with no constraints
    cap = CapacityReport(active_incidents_sev1=0)

    # Pop order must be: SEV1 -> SEV2/Payment -> Commercial Sales -> Discovery
    first = scheduler.pop_next_job(cap)
    assert first.priority_tier == JobPriorityTier.CRITICAL_SEV1
    assert first.entity_id == 303

    second = scheduler.pop_next_job(cap)
    assert second.priority_tier == JobPriorityTier.HIGH_SEV2_PAYMENT
    assert second.entity_id == 202

    third = scheduler.pop_next_job(cap)
    assert third.priority_tier == JobPriorityTier.COMMERCIAL_SALES
    assert third.entity_id == 101

    fourth = scheduler.pop_next_job(cap)
    assert fourth.priority_tier == JobPriorityTier.BACKGROUND_DISCOVERY
    assert fourth.entity_id == 1


@pytest.mark.asyncio
async def test_06_capacity_governor_and_canary_limits():
    """6. Test capacity governor limits: evaluation reflects database constraints."""
    async with AsyncSessionLocal() as session:
        report = await deterministic_scheduler.evaluate_capacity(session)
        expected_cap = getattr(settings, "MAX_OUTREACH_PER_DAY", 1)
        assert report.outbound_quota_daily == expected_cap
        assert report.outbound_available >= 0
        assert isinstance(report.bottlenecks, list)
        assert report.max_worker_concurrency == 4


@pytest.mark.asyncio
async def test_07_backpressure_under_sev1_incident():
    """7. Test that when an active SEV-1 incident is present, routine jobs are backpressured."""
    scheduler = DeterministicScheduler()

    # Enqueue a routine commercial sales job
    j_sales = ScheduledJob(
        priority_tier=JobPriorityTier.COMMERCIAL_SALES,
        job_type="draft_outreach",
        entity_type="business",
        entity_id=555,
        commercial_value_usd=1500.0
    )
    scheduler.enqueue(j_sales)

    # Capacity report WITH active SEV-1 incident
    constrained_cap = CapacityReport(active_incidents_sev1=1, is_constrained=True)

    # Attempting to pop while SEV-1 is active should return None (routine job skipped)
    job = scheduler.pop_next_job(constrained_cap)
    assert job is None, "Routine sales job must be throttled during active SEV-1 incident"

    # Enqueue a SEV-1 emergency fix
    j_sev1 = ScheduledJob(
        priority_tier=JobPriorityTier.CRITICAL_SEV1,
        job_type="restore_database",
        entity_type="incident",
        entity_id=777,
        commercial_value_usd=0.0
    )
    scheduler.enqueue(j_sev1)

    # SEV-1 job MUST be popped immediately even under SEV-1 constraint
    popped_sev1 = scheduler.pop_next_job(constrained_cap)
    assert popped_sev1 is not None
    assert popped_sev1.priority_tier == JobPriorityTier.CRITICAL_SEV1
    assert popped_sev1.entity_id == 777

    # After SEV-1 is resolved (active_incidents_sev1=0), routine job can run
    resolved_cap = CapacityReport(active_incidents_sev1=0, is_constrained=False)
    popped_routine = scheduler.pop_next_job(resolved_cap)
    assert popped_routine is not None
    assert popped_routine.priority_tier == JobPriorityTier.COMMERCIAL_SALES
    assert popped_routine.entity_id == 555


@pytest.mark.asyncio
async def test_08_unified_orchestrator_system_status():
    """8. Test unified orchestrator get_system_status returns telemetry and healthy state."""
    async with AsyncSessionLocal() as session:
        status = await unified_orchestrator.get_system_status(session)
        assert status["status"] == "OPERATIONAL"
        assert "capacity" in status
        assert "pipeline_stage_counts" in status
        assert "revenue" in status
        assert "maintenance" in status
        expected_cap = getattr(settings, "MAX_OUTREACH_PER_DAY", 1)
        assert status["capacity"]["outbound_quota_daily"] == expected_cap


@pytest.mark.asyncio
async def test_09_orchestrator_lifecycle_stepping_and_policy_guards():
    """9. Test orchestrator deterministic next-best-action and transition stepping."""
    async with AsyncSessionLocal() as session:
        unique_domain = f"test-step-{uuid.uuid4().hex[:8]}.com"
        biz = Business(
            name="Orchestrator Test Dental Clinic",
            domain=unique_domain,
            website_url=f"https://{unique_domain}",
            country="AE",
            niche="dental",
            pipeline_stage="lead",
            city="Dubai"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Step 1: DISCOVERED -> QUALIFIED
        step_1 = await unified_orchestrator.step_prospect_lifecycle(session, biz.id)
        await session.commit()
        assert step_1["current_stage"] == CanonicalLifecycleStage.QUALIFIED.value

        # Step 2: QUALIFIED -> PRIORITIZED
        step_2 = await unified_orchestrator.step_prospect_lifecycle(session, biz.id)
        await session.commit()
        assert step_2["current_stage"] == CanonicalLifecycleStage.PRIORITIZED.value

        # Step 3: PRIORITIZED -> CONTACTABLE
        step_3 = await unified_orchestrator.step_prospect_lifecycle(session, biz.id)
        await session.commit()
        assert step_3["current_stage"] == CanonicalLifecycleStage.CONTACTABLE.value


@pytest.mark.asyncio
async def test_10_end_to_end_single_prospect_simulation():
    """10. Test end-to-end simulation progressing a prospect through all 21 canonical stages."""
    async with AsyncSessionLocal() as session:
        sim_res = await end_to_end_simulator.simulate_single_prospect_full_loop(
            session=session,
            industry="automotive",
            business_name="Apex Performance Auto Works"
        )
        await session.commit()

        assert sim_res.success is True
        assert sim_res.final_stage == CanonicalLifecycleStage.RETAINED.value
        assert sim_res.zero_emails_sent is True
        assert sim_res.zero_live_payments is True
        assert sim_res.deal_value_usd > 0
        assert sim_res.incident_resolved is True
        assert len(sim_res.stages_traversed) >= 20


@pytest.mark.asyncio
async def test_11_multi_prospect_concurrency_10_prospects():
    """11. Test 10 simultaneous independent prospects running concurrently with state isolation."""
    async with AsyncSessionLocal() as session:
        results = await end_to_end_simulator.simulate_multi_prospect_concurrency(session=session, count=10)
        await session.commit()

        assert len(results) == 10
        assert all(r.success is True for r in results)
        assert all(r.final_stage == CanonicalLifecycleStage.RETAINED.value for r in results)

        # Ensure distinct businesses
        biz_ids = {r.business_id for r in results}
        assert len(biz_ids) == 10


@pytest.mark.asyncio
async def test_12_multi_customer_concurrency_4_customers():
    """12. Test 4 simultaneous customers across distinct lifecycle branches with strict data isolation."""
    async with AsyncSessionLocal() as session:
        concurrency_report = await end_to_end_simulator.simulate_multi_customer_concurrency(session)
        await session.commit()

        assert concurrency_report["data_isolation_verified"] is True
        assert concurrency_report["customer_a"]["status"] == "SEV-1"
        assert concurrency_report["customer_b"]["status"] == "NORMAL_SUPPORT"
        assert concurrency_report["customer_c"]["status"] == "BUILDING"
        assert concurrency_report["customer_d"]["status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_13_failure_matrix_ai_provider_down():
    """13. Test failure resilience: AI provider unavailable cleanly falls back to deterministic rules."""
    async with AsyncSessionLocal() as session:
        res = await end_to_end_simulator.simulate_failure_matrix_and_rollback(session, "AI_PROVIDER_UNAVAILABLE")
        await session.commit()

        assert res["handled"] is True
        assert res["fallback_strategy"] == "DETERMINISTIC_RULES"
        assert res["score_produced"] is True


@pytest.mark.asyncio
async def test_14_failure_matrix_qa_gate_failure():
    """14. Test failure resilience: QA gate failure reverts state to BUILDING, blocking DEPLOYING."""
    async with AsyncSessionLocal() as session:
        res = await end_to_end_simulator.simulate_failure_matrix_and_rollback(session, "QA_GATE_FAILURE")
        await session.commit()

        assert res["handled"] is True
        assert res["remediation"] == "REVERTED_TO_BUILDING_REPAIR"
        assert res["current_stage"] == CanonicalLifecycleStage.BUILDING.value


@pytest.mark.asyncio
async def test_15_failure_matrix_payment_failed():
    """15. Test failure resilience: Payment failure enters PAYMENT_FAILED and keeps delivery blocked."""
    async with AsyncSessionLocal() as session:
        res = await end_to_end_simulator.simulate_failure_matrix_and_rollback(session, "PAYMENT_FAILED")
        await session.commit()

        assert res["handled"] is True
        assert res["current_stage"] == CanonicalLifecycleStage.PAYMENT_FAILED.value
        assert res["delivery_blocked"] is True


@pytest.mark.asyncio
async def test_16_failure_matrix_deployment_rollback():
    """16. Test failure resilience: Deployment smoke test failure triggers rollback and DELIVERY_BLOCKED."""
    async with AsyncSessionLocal() as session:
        res = await end_to_end_simulator.simulate_failure_matrix_and_rollback(session, "DEPLOYMENT_ROLLBACK")
        await session.commit()

        assert res["handled"] is True
        assert res["current_stage"] == CanonicalLifecycleStage.DELIVERY_BLOCKED.value
        assert res["rolled_back"] is True
        assert res["incident_created"].startswith("INC-")


@pytest.mark.asyncio
async def test_17_four_industry_validation_configurations():
    """17. Test four default industry configurations: Automotive, Dental, Roofing, HVAC."""
    defaults = end_to_end_simulator.INDUSTRY_DEFAULTS
    assert "automotive" in defaults
    assert "dental" in defaults
    assert "roofing" in defaults
    assert "hvac" in defaults

    for ind, cfg in defaults.items():
        assert cfg["deal_value"] >= 500.0
        assert len(cfg["service"]) > 0
        assert len(cfg["mock_reply"]) > 0


@pytest.mark.asyncio
async def test_18_unified_api_routes():
    """18. Test unified API endpoints (/api/orchestration/status, /capacity, /simulation/run, /api/ceo/unified-control)."""
    from httpx import AsyncClient, ASGITransport
    from app.api.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Orchestration status
        r_status = await ac.get("/api/orchestration/status")
        assert r_status.status_code == 200
        data_status = r_status.json()
        assert data_status["status"] == "OPERATIONAL"
        assert "capacity" in data_status

        # 2. Capacity
        r_cap = await ac.get("/api/orchestration/capacity")
        assert r_cap.status_code == 200
        data_cap = r_cap.json()
        expected_cap = getattr(settings, "MAX_OUTREACH_PER_DAY", 1)
        assert data_cap["outbound_quota_daily"] == expected_cap

        # 3. CEO unified control
        r_ceo = await ac.get("/api/ceo/unified-control")
        assert r_ceo.status_code == 200
        data_ceo = r_ceo.json()
        assert "capacity" in data_ceo
        assert "revenue" in data_ceo
        assert "maintenance" in data_ceo

        # 4. Simulation run endpoint
        r_sim = await ac.post(
            "/api/orchestration/simulation/run",
            json={"industry": "dental", "business_name": "API Test Dental Clinic"}
        )
        assert r_sim.status_code == 200
        data_sim = r_sim.json()
        assert data_sim["success"] is True
        assert data_sim["final_stage"] == CanonicalLifecycleStage.RETAINED.value
        assert data_sim["zero_emails_sent"] is True


@pytest.mark.asyncio
async def test_19_production_canary_invariant():
    """19. Test Production Safety Invariant: Orange Auto Canary #12 must be APPROVED and sent_at=None."""
    assert settings.DRY_RUN is True, "DRY_RUN must default to True in production test environment!"

    async with AsyncSessionLocal() as session:
        msg_12 = await session.get(OutreachMessage, 12)
        if msg_12 is not None:
            assert msg_12.status == "APPROVED", "Canary #12 status must remain 'APPROVED'!"
            assert msg_12.sent_at is None, "Canary #12 sent_at must remain NULL (never sent)!"
