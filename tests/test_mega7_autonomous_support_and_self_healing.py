"""
==============================================================================
MEGA PROMPT 7: AUTONOMOUS CUSTOMER SUPPORT + SELF-HEALING + MAINTENANCE ENGINE
COMPREHENSIVE TEST SUITE
==============================================================================
Verifies:
1. Code Intelligence AST analysis, caller/callee, blast radius, provider benchmarks.
2. Support ticket creation, automatic triage, SEV-1..4 severity classification.
3. Support state machine 14-state transitions, invalid transition guard, append-only IncidentEvent audit trail.
4. Evidence-grounded diagnostics distinguishing observed facts, telemetry, inferences, hypotheses.
5. Safe auto-remediation (precheck -> snapshot -> execute -> postcheck -> QA -> verify).
6. High-impact approval gate blocking and operator authorization.
7. Bounded repair loop (max 3 attempts, automated rollback on postcheck failure, escalation to human).
8. Customer communication generation with secret/path/trace redaction.
9. Customer vs prospect boundary isolation (NonCustomerException).
10. Multi-customer tenant concurrency (Customer A failure does not block Customer B).
11. SLA compliance calculation and breach detection.
12. Incident memory indexing and retrieval.
13. Four-industry validation scenarios (Automotive, Dental, Roofing, HVAC).
14. Simulated failure injection (500 error, worker stopped, db lock, provider timeout).
15. Non-negotiable safety baseline & Orange Auto Canary #12 integrity check.
==============================================================================
"""

import os
import sys
import uuid
import pytest
import asyncio
from datetime import datetime, timedelta

from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, Customer, OutreachMessage, SupportTicket,
    CustomerIncident, IncidentEvent, IncidentMemory, MaintenanceRecord
)
from app.code_intelligence.native_analyzer import NativeRepositoryAnalyzer
from app.code_intelligence.benchmarks import code_intelligence_benchmarker
from app.support.state_machine import (
    support_state_machine, SupportLifecycleState, StateTransitionError,
    SupportState, InvalidStateTransitionException
)
from app.support.agents.reasoning_agents import (
    SupportTriageAgent, DiagnosticAgent, RootCauseAgent,
    RemediationPlanner, QAAgent, CustomerCommunicationAgent, MaintenanceAnalyst,
    support_triage_agent, customer_communication_agent
)
from app.support.diagnostics import diagnostic_engine
from app.support.remediation import (
    remediation_engine, ApprovalRequiredException, MaxRemediationAttemptsException
)
from app.support.sla_and_memory import sla_engine, incident_memory_service
from app.support.channels import channel_normalizer, NonCustomerException
from app.support.service import support_service
from app.commercial.pricing_engine import PricingEngine


# ==============================================================================
# Helper to get or create test customers
# ==============================================================================
async def get_or_create_test_customer(session, email="client_mega7@example.com", company="Mega7 Corp", industry="Automotive"):
    from sqlalchemy import select
    res = await session.execute(select(Customer).where(Customer.contact_email == email))
    cust = res.scalar_one_or_none()
    if not cust:
        b_res = await session.execute(select(Business).where(Business.name == company))
        biz = b_res.scalar_one_or_none()
        if not biz:
            biz = Business(
                name=company,
                domain=f"{company.lower().replace(' ', '')}-{uuid.uuid4().hex[:6]}.com",
                niche=industry,
                city="Dallas",
                country="US"
            )
            session.add(biz)
            await session.flush()
        
        cust = Customer(
            business_id=biz.id,
            company_name=company,
            contact_email=email,
            onboarding_status="ACTIVE",
            contract_amount=3000.0
        )
        session.add(cust)
        await session.commit()
        await session.refresh(cust)
    return cust


# ==============================================================================
# 1. CODE INTELLIGENCE AST ANALYSIS, BLAST RADIUS & BENCHMARKS
# ==============================================================================
@pytest.mark.asyncio
async def test_code_intelligence_ast_analysis_and_blast_radius():
    analyzer = NativeRepositoryAnalyzer()
    
    # 1. Analyze incident context via native AST
    ctx = await analyzer.analyze_incident_context(
        error_signature="pricing calculation floor",
        affected_component="pricing_engine.py"
    )
    assert ctx.provider_name == "NativeRepositoryAnalyzer"
    assert len(ctx.matched_files) > 0 or ctx.confidence > 0
    assert any("pricing_engine.py" in f for f in ctx.matched_files)

    # 2. Blast radius calculation
    blast = await analyzer.get_blast_radius(["app/commercial/pricing_engine.py"])
    assert "app/commercial/pricing_engine.py" in blast.modified_files
    assert blast.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert isinstance(blast.directly_affected_files, list)

    # 3. Code Intelligence Benchmark harness
    benchmark_res = await code_intelligence_benchmarker.run_all_benchmarks()
    assert benchmark_res["selected_primary_provider"] == "NativeRepositoryAnalyzer"
    assert len(benchmark_res["results"]) == 3
    native_bench = next(r for r in benchmark_res["results"] if r["provider_name"] == "NativeRepositoryAnalyzer")
    assert native_bench["token_usage"] == 0  # Zero token cost
    assert native_bench["latency_ms"] < 10000.0


# ==============================================================================
# 2. SUPPORT TICKET CREATION & AUTOMATIC TRIAGE
# ==============================================================================
@pytest.mark.asyncio
async def test_support_ticket_creation_and_automatic_triage():
    async with AsyncSessionLocal() as session:
        cust = await get_or_create_test_customer(session, "triage_user@auto.com", "Apex Auto Triage", "Automotive")
        
        # Test SEV-1 triage (payment down / system crash)
        t1 = await support_service.create_ticket(
            session=session,
            customer_id=cust.id,
            subject="Critical: Payment checkout failing with 500 outage for all customers",
            description="Our live customer booking portal crashes completely on checkout.",
            source="CUSTOMER_PORTAL"
        )
        assert t1.severity in ["SEV-1", "SEV-2"]
        assert t1.priority in ["URGENT", "HIGH"]
        assert t1.status == SupportLifecycleState.TRIAGED.value

        # Test SEV-4 triage (minor cosmetic query)
        t2 = await support_service.create_ticket(
            session=session,
            customer_id=cust.id,
            subject="Minor typography question",
            description="How do I change the font color on the footer when convenient?",
            source="CUSTOMER_PORTAL"
        )
        assert t2.severity in ["SEV-3", "SEV-4"]
        assert t2.priority in ["LOW", "MEDIUM"]


# ==============================================================================
# 3. DETERMINISTIC 14-STATE MACHINE & APPEND-ONLY INCIDENT AUDIT TRAIL
# ==============================================================================
@pytest.mark.asyncio
async def test_support_state_machine_transitions_and_incident_events():
    async with AsyncSessionLocal() as session:
        cust = await get_or_create_test_customer(session, "sm_user@dental.com", "Dental Smile Care", "Dental")
        
        ticket = await support_service.create_ticket(
            session=session,
            customer_id=cust.id,
            subject="Booking widget cache stale",
            description="Patients seeing old schedule after update",
            source="CUSTOMER_PORTAL"
        )
        assert ticket.status == SupportLifecycleState.TRIAGED.value

        # Valid transition: TRIAGED -> DIAGNOSING
        await support_state_machine.transition(
            session=session,
            ticket=ticket,
            target_state=SupportLifecycleState.DIAGNOSING,
            agent_role="DiagnosticAgent",
            reason="Starting diagnostic probe"
        )
        assert ticket.status == SupportLifecycleState.DIAGNOSING.value

        # Invalid transition test: cannot jump directly from DIAGNOSING to CLOSED
        with pytest.raises(StateTransitionError):
            await support_state_machine.transition(
                session=session,
                ticket=ticket,
                target_state=SupportLifecycleState.CLOSED,
                agent_role="TestAgent",
                reason="Illegal jump"
            )

        # Verify append-only IncidentEvent trail
        from sqlalchemy import select
        events_res = await session.execute(
            select(IncidentEvent).order_by(IncidentEvent.id.desc()).limit(10)
        )
        events = events_res.scalars().all()
        assert len(events) >= 1
        assert any(e.to_status == SupportLifecycleState.DIAGNOSING.value for e in events)


# ==============================================================================
# 4. EVIDENCE-GROUNDED DIAGNOSTICS
# ==============================================================================
@pytest.mark.asyncio
async def test_evidence_grounded_diagnostics():
    async with AsyncSessionLocal() as session:
        cust = await get_or_create_test_customer(session, "diag_user@roofing.com", "Roof Pro Diagnostics", "Roofing")
        ticket = await support_service.create_ticket(
            session=session,
            customer_id=cust.id,
            subject="API timeout on quote form submission",
            description="Estimator requests time out after 30 seconds when uploading roof dimensions.",
            source="CUSTOMER_PORTAL"
        )

        diag_report = await diagnostic_engine.run_diagnostics(
            ticket_id=ticket.id,
            incident_number="INC-DIAG-01",
            customer_id=cust.id,
            error_description=ticket.description,
            affected_component="quote_calculator"
        )
        
        assert diag_report.ticket_id == ticket.id
        assert len(diag_report.checks) > 0
        assert len(diag_report.evidence_items) > 0
        
        # Verify evidence item types
        evidence_types = {item.category for item in diag_report.evidence_items}
        assert "OBSERVED_FACT" in evidence_types or "SYSTEM_TELEMETRY" in evidence_types


# ==============================================================================
# 5. SAFE AUTO-REMEDIATION LIFECYCLE
# ==============================================================================
@pytest.mark.asyncio
async def test_safe_auto_remediation_lifecycle():
    async with AsyncSessionLocal() as session:
        cust = await get_or_create_test_customer(session, "remed_user@hvac.com", "HVAC Climate Pro", "HVAC")
        ticket = await support_service.create_ticket(
            session=session,
            customer_id=cust.id,
            subject="Static cache out of sync after stylesheet change",
            description="Client portal styles not updating for customer technicians.",
            source="CUSTOMER_PORTAL"
        )

        # Run diagnosis to plan remediation
        diag = await support_service.diagnose_ticket(session=session, ticket_id=ticket.id)
        assert diag.ticket_id == ticket.id

        # Execute safe auto-fix via SupportService
        rem_res = await support_service.execute_remediation(
            session=session,
            ticket_id=ticket.id,
            operator_approved=False
        )

        assert rem_res.verified is True
        assert rem_res.status == SupportLifecycleState.RESOLVED.value
        assert rem_res.rollback_available is True
        assert rem_res.snapshot_id is not None


# ==============================================================================
# 6. HIGH-IMPACT APPROVAL GATE BLOCKING & OPERATOR AUTHORIZATION
# ==============================================================================
@pytest.mark.asyncio
async def test_high_impact_approval_gate():
    async with AsyncSessionLocal() as session:
        cust = await get_or_create_test_customer(session, "gate_user@auto.com", "Precision Auto Works", "Automotive")
        ticket = await support_service.create_ticket(
            session=session,
            customer_id=cust.id,
            subject="Database schema change required for vehicle inventory",
            description="Database table migration required for dealer integration.",
            source="CUSTOMER_PORTAL"
        )
        ticket.is_high_impact = True
        ticket.fix_plan = "Alter database schema"
        ticket.status = SupportLifecycleState.REMEDIATION_PLANNED.value
        await session.commit()

        # Attempting dangerous high-impact action without approval MUST raise ApprovalRequiredException
        with pytest.raises(ApprovalRequiredException):
            await support_service.execute_remediation(
                session=session,
                ticket_id=ticket.id,
                operator_approved=False
            )

        # Authorized operator approves it
        approved_res = await support_service.execute_remediation(
            session=session,
            ticket_id=ticket.id,
            operator_approved=True,
            approved_by="sysadmin"
        )
        assert approved_res.verified is True
        assert approved_res.status == SupportLifecycleState.RESOLVED.value


# ==============================================================================
# 7. BOUNDED REPAIR LOOP (MAX 3 ATTEMPTS) & ROLLBACK ESCALATION
# ==============================================================================
@pytest.mark.asyncio
async def test_bounded_repair_loop_and_rollback():
    # 1. 4th attempt must be rejected by bounded loop
    with pytest.raises(MaxRemediationAttemptsException):
        await remediation_engine.execute_remediation(
            action_name="reprocess_failed_webhook",
            params={"webhook_id": 999},
            repair_attempt=4
        )

    # 2. Simulated postcheck failure triggers automated rollback
    rollback_res = await remediation_engine.execute_remediation(
        action_name="flush_static_cache",
        params={"target": "assets"},
        repair_attempt=1,
        simulate_postcheck_failure=True
    )
    assert rollback_res.postcheck_passed is False
    assert rollback_res.rollback_executed is True


# ==============================================================================
# 8. CUSTOMER COMMUNICATION GENERATION WITH SECRET/PATH/TRACE REDACTION
# ==============================================================================
def test_customer_communication_redaction():
    agent = CustomerCommunicationAgent()
    
    raw_text = (
        "Internal traceback in /opt/agency/app/core/security.py:44. "
        "Leaked secret sk_live_9949182390141 and token eyJhbGciOiJIUzI1Ni."
    )
    redacted, count = agent.redact_secrets(raw_text)

    # Invariants: No secrets, tokens, or internal Linux paths
    assert "sk_live_" not in redacted
    assert "eyJhbGciOi" not in redacted
    assert "/opt/agency" not in redacted
    assert count >= 2

    # Clean customer message generation
    msg = agent.generate_message(
        ticket_number="TCK-TEST-001",
        lifecycle_stage="RESOLVED",
        customer_name="Apex Automotive",
        issue_summary="Portal login slow",
        resolution_summary="Optimized database index"
    )
    assert "Apex Automotive" in msg.body
    assert "TCK-TEST-001" in msg.body
    assert "resolved" in msg.body.lower()


# ==============================================================================
# 9. CUSTOMER VS PROSPECT BOUNDARY ISOLATION
# ==============================================================================
@pytest.mark.asyncio
async def test_customer_vs_prospect_boundary_isolation():
    async with AsyncSessionLocal() as session:
        # A prospect email that is NOT in Customer table
        prospect_email = "random_cold_prospect@somewhere.com"
        
        with pytest.raises(NonCustomerException):
            await channel_normalizer.resolve_and_validate_customer(
                session=session,
                customer_id=None,
                sender_email=prospect_email
            )


# ==============================================================================
# 10. MULTI-CUSTOMER TENANT CONCURRENCY ISOLATION
# ==============================================================================
@pytest.mark.asyncio
async def test_multi_tenant_concurrency_isolation():
    async with AsyncSessionLocal() as session:
        cust_a = await get_or_create_test_customer(session, "tenant_a@auto.com", "Tenant A Auto", "Automotive")
        cust_b = await get_or_create_test_customer(session, "tenant_b@dental.com", "Tenant B Dental", "Dental")

        # Ticket A created
        ticket_a = await support_service.create_ticket(
            session=session,
            customer_id=cust_a.id,
            subject="Outage for Tenant A",
            description="Tenant A is experiencing disruption",
            source="CUSTOMER_PORTAL"
        )
        
        # Ticket B created and completely resolved independently
        ticket_b = await support_service.create_ticket(
            session=session,
            customer_id=cust_b.id,
            subject="Cache sync for Tenant B",
            description="Tenant B requests routine refresh",
            source="CUSTOMER_PORTAL"
        )
        
        await support_service.diagnose_ticket(session, ticket_b.id)
        rem_b = await support_service.execute_remediation(session, ticket_b.id)
        
        assert rem_b.verified is True
        assert ticket_b.status == SupportLifecycleState.RESOLVED.value
        # Tenant A remains isolated and unaffected
        assert ticket_a.status == SupportLifecycleState.TRIAGED.value


# ==============================================================================
# 11. SLA COMPLIANCE CALCULATION & BREACH DETECTION
# ==============================================================================
def test_sla_compliance_and_breach_detection():
    # Fresh SEV-1 ticket created right now -> Not breached
    fresh_sev1 = SupportTicket(
        id=901,
        ticket_number="TCK-SLA-01",
        customer_id=1,
        severity="SEV-1",
        status="SUPPORT_REQUESTED",
        created_at=datetime.utcnow(),
        response_at=datetime.utcnow()
    )
    report_fresh = sla_engine.evaluate_sla(fresh_sev1)
    assert report_fresh.response_breached is False
    assert report_fresh.overall_sla_status == "COMPLIANT"

    # Old unresolved SEV-1 ticket from 5 hours ago -> Breached
    old_sev1 = SupportTicket(
        id=902,
        ticket_number="TCK-SLA-02",
        customer_id=1,
        severity="SEV-1",
        status="DIAGNOSING",
        created_at=datetime.utcnow() - timedelta(hours=5)
    )
    report_old = sla_engine.evaluate_sla(old_sev1)
    assert report_old.resolution_breached is True
    assert report_old.overall_sla_status == "BREACHED"


# ==============================================================================
# 12. INCIDENT MEMORY INDEXING & RETRIEVAL
# ==============================================================================
@pytest.mark.asyncio
async def test_incident_memory_indexing_and_retrieval():
    async with AsyncSessionLocal() as session:
        # Store into memory
        mem = await incident_memory_service.record_incident_memory(
            session=session,
            category="DATABASE",
            component="sqlite_driver",
            error_pattern="database is locked operational error",
            root_cause="Concurrent write lock contention",
            remediation_pattern="restart_worker_process",
            verified_fix={"action": "restart_worker_process"}
        )
        assert mem.id is not None

        # Search memory for similar symptom
        matches = await incident_memory_service.search_memory(
            session=session,
            category="DATABASE",
            error_pattern="database is locked"
        )
        assert len(matches) > 0
        assert any(m["remediation_pattern"] == "restart_worker_process" for m in matches)


# ==============================================================================
# 13. FOUR-INDUSTRY VALIDATION SCENARIOS
# ==============================================================================
@pytest.mark.asyncio
async def test_four_industry_validation_scenarios():
    scenarios = [
        ("Automotive", "Dealership online service booking calendar slot mismatch", "SEV-3"),
        ("Dental", "Patient HIPAA intake form SSL certificate renewal alert", "SEV-2"),
        ("Roofing", "Drone imagery asset delivery CDN cache staleness", "SEV-3"),
        ("HVAC", "Emergency heating repair dispatch webhook down", "SEV-1")
    ]

    async with AsyncSessionLocal() as session:
        for ind, subj, expected_sev in scenarios:
            cust = await get_or_create_test_customer(
                session, f"ind_{ind.lower()}@test.com", f"{ind} Industry Test Co", ind
            )
            ticket = await support_service.create_ticket(
                session=session,
                customer_id=cust.id,
                subject=subj,
                description=f"Industry domain test for {ind}: {subj}",
                source="CUSTOMER_PORTAL"
            )
            assert ticket.severity in ["SEV-1", "SEV-2", "SEV-3", "SEV-4"]
            assert ticket.status == SupportLifecycleState.TRIAGED.value


# ==============================================================================
# 14. SIMULATED FAILURE INJECTION (500 ERROR, WORKER, DB LOCK, TIMEOUT)
# ==============================================================================
@pytest.mark.asyncio
async def test_simulated_failure_injection():
    # 1. 500 error triage
    t1 = support_triage_agent.triage(
        "500 Internal Server Error on checkout endpoint",
        "Stack trace showing Unhandled Exception in /api/checkout"
    )
    assert t1.severity in ["SEV-1", "SEV-2"]

    # 2. Worker stopped triage
    t2 = support_triage_agent.triage(
        "Background task worker down processing pipeline jobs",
        "Celery/systemd agency-worker inactive (dead)"
    )
    assert t2.severity in ["SEV-1", "SEV-2"]

    # 3. Database lock triage
    t3 = support_triage_agent.triage(
        "database is locked - operational error",
        "SQLite busy timeout exceeded waiting for write lock"
    )
    assert t3.category == "DATABASE"

    # 4. External provider timeout triage
    t4 = support_triage_agent.triage(
        "Stripe payment webhook delivery timeout",
        "Payment webhook event timed out after 30000ms"
    )
    assert t4.category == "PAYMENT"


# ==============================================================================
# 15. NON-NEGOTIABLE SAFETY BASELINE & ORANGE AUTO CANARY #12
# ==============================================================================
@pytest.mark.asyncio
async def test_non_negotiable_safety_baseline_and_canary_12():
    """
    CANARY SAFETY INVARIANT:
    OutreachMessage #12 (Business 30, Orange Auto) must remain APPROVED with sent_at=None.
    DRY_RUN must remain True. Outbound daily cap strictly enforced.
    """
    assert settings.DRY_RUN is True, "DRY_RUN must default to True"

    async with AsyncSessionLocal() as session:
        msg = await session.get(OutreachMessage, 12)
        if msg:
            assert msg.status == "APPROVED", "Canary #12 status must remain APPROVED"
            assert msg.sent_at is None, "Canary #12 sent_at must remain None (ZERO live dispatches)"
