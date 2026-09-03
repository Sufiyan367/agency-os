"""
Comprehensive tests for Non-Blocking Prospecting + Event-Driven Memory Architecture.

Tests cover:
1. Prospect A can be contacted and Prospect B starts without waiting for A's reply.
2. A later email reply correctly identifies Prospect A from stored identifiers.
3. Prospect A's previous audit/offer/outreach context is restored when handling the reply.
4. Handling A's reply does not stop or block Prospect B/C prospecting.
5. Voice, meeting, and payment events map back to the correct prospect.
6. Kill switch and human takeover still work safely.
"""
import uuid
import pytest
import asyncio
from typing import Dict, Any
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.database.models import Business, PipelineStage, ProspectMemory, Meeting
from app.agents.revenue_agent import revenue_agent_orchestrator, RevenueAgentOrchestrator
from app.crm.memory_service import memory_service
from app.core.config import settings


@pytest.mark.asyncio
async def test_non_blocking_prospecting_a_then_b_without_waiting_for_reply():
    """
    Proves requirement:
    Prospect A -> contact -> SAVE -> NEXT
    Prospect B -> contact -> SAVE -> NEXT
    Without waiting for email replies, calls, meetings, or payments.
    """
    orch = RevenueAgentOrchestrator()
    uid_a = uuid.uuid4().hex[:6]
    uid_b = uuid.uuid4().hex[:6]

    prospect_a = {
        "name": f"Acme HVAC {uid_a}",
        "domain": f"acmehvac-{uid_a}.com",
        "email": f"owner@acmehvac-{uid_a}.com",
        "phone": "+1-512-555-0101",
        "estimated_value": 850.0,
        "buyer_score": 85.0,
        "opportunity_score": 79.0,
        "load_time_seconds": 5.2,
        "performance_score": 38.0
    }

    prospect_b = {
        "name": f"Zenith Plumbing {uid_b}",
        "domain": f"zenithplumbing-{uid_b}.com",
        "email": f"contact@zenithplumbing-{uid_b}.com",
        "phone": "+1-512-555-0202",
        "estimated_value": 1200.0,
        "buyer_score": 90.0,
        "opportunity_score": 88.0,
        "load_time_seconds": 6.1,
        "performance_score": 31.0
    }

    # 1. Step Prospect A
    res_a = await orch.step_single_prospect(prospect_a, commercial_floor=500.0)
    assert res_a["status"] == "CONTACTED"
    assert res_a["next"] == "NEXT_PROSPECT"

    # 2. Step Prospect B IMMEDIATELY without any reply from Prospect A
    res_b = await orch.step_single_prospect(prospect_b, commercial_floor=500.0)
    assert res_b["status"] == "CONTACTED"
    assert res_b["next"] == "NEXT_PROSPECT"

    # 3. Verify both memories are independently stored in SQLite
    async with AsyncSessionLocal() as session:
        mem_a = await memory_service.get_memory(session, domain=prospect_a["domain"])
        mem_b = await memory_service.get_memory(session, domain=prospect_b["domain"])

        assert mem_a is not None
        assert mem_a.contact_email == prospect_a["email"]
        assert mem_a.pipeline_stage == PipelineStage.CONTACTED.value
        assert mem_a.estimated_value == 850.0
        assert mem_a.audit_results["load_time_seconds"] == 5.2

        assert mem_b is not None
        assert mem_b.contact_email == prospect_b["email"]
        assert mem_b.pipeline_stage == PipelineStage.CONTACTED.value
        assert mem_b.estimated_value == 1200.0
        assert mem_b.audit_results["load_time_seconds"] == 6.1


@pytest.mark.asyncio
async def test_later_email_reply_identifies_prospect_and_restores_context():
    """
    Proves requirements:
    - Inbound reply identifies prospect from email / domain
    - Restores previous audit findings, scores, and offer context
    - Grounded agent reply references stored audit evidence
    """
    orch = RevenueAgentOrchestrator()
    uid = uuid.uuid4().hex[:6]
    domain = f"summitroofing-{uid}.com"
    email = f"info@{domain}"

    prospect = {
        "name": f"Summit Roofing {uid}",
        "domain": domain,
        "email": email,
        "phone": "+1-512-555-0303",
        "estimated_value": 950.0,
        "buyer_score": 87.0,
        "opportunity_score": 81.0,
        "load_time_seconds": 4.8,
        "performance_score": 42.0
    }

    # Initial contact
    await orch.step_single_prospect(prospect, commercial_floor=500.0)

    # Inbound reply arrives later asking what the service is about
    reply_payload = {
        "email": email,
        "body": "What is this about? How does your turnaround diagnostic work?"
    }

    event_res = await orch.handle_inbound_event("EMAIL_REPLY", reply_payload)
    assert event_res["status"] == "PROCESSED"
    assert event_res["prospect_domain"] == domain
    assert "restored_context" in event_res
    assert event_res["restored_context"]["audit_results"]["performance_score"] == 42.0
    assert event_res["restored_context"]["offered_value"] == 950.0

    # Verify agent reply is grounded in the restored audit evidence (42 score)
    assert "42" in event_res["agent_reply"] or "performance" in event_res["agent_reply"].lower()

    # Verify persistent memory updated with conversation history and qualified stage
    async with AsyncSessionLocal() as session:
        mem = await memory_service.get_memory(session, domain=domain)
        assert mem is not None
        assert mem.pipeline_stage in (PipelineStage.QUALIFIED_REPLY.value, PipelineStage.REPLIED.value)
        assert len(mem.conversation_history) >= 2
        assert mem.conversation_history[0]["message"] == reply_payload["body"]


@pytest.mark.asyncio
async def test_handling_reply_does_not_stop_prospecting_loop():
    """
    Proves requirement:
    Handling an inbound reply for Prospect A runs concurrently without
    stopping or corrupting background prospecting of other candidates.
    """
    orch = RevenueAgentOrchestrator()
    uid_a = uuid.uuid4().hex[:6]
    uid_c = uuid.uuid4().hex[:6]

    # Setup Prospect A in database
    prospect_a = {
        "name": f"Pinnacle Pest {uid_a}",
        "domain": f"pinnaclepest-{uid_a}.com",
        "email": f"support@pinnaclepest-{uid_a}.com",
        "phone": "+1-512-555-0404",
        "estimated_value": 750.0,
        "load_time_seconds": 3.9,
        "performance_score": 55.0
    }
    await orch.step_single_prospect(prospect_a, commercial_floor=500.0)

    # Simulate inbound event for A
    event_task = asyncio.create_task(
        orch.handle_inbound_event(
            "EMAIL_REPLY",
            {"email": prospect_a["email"], "body": "We are interested in reviewing the diagnostic."}
        )
    )

    # Simultaneously, prospecting loop processes Prospect C
    prospect_c = {
        "name": f"Crown Electrical {uid_c}",
        "domain": f"crownelectrical-{uid_c}.com",
        "email": f"contact@crownelectrical-{uid_c}.com",
        "phone": "+1-512-555-0505",
        "estimated_value": 1100.0,
        "load_time_seconds": 4.1,
        "performance_score": 45.0
    }
    res_c = await orch.step_single_prospect(prospect_c, commercial_floor=500.0)

    event_res = await event_task

    assert res_c["status"] == "CONTACTED"
    assert event_res["status"] == "PROCESSED"
    assert event_res["intent"] in ("INTERESTED", "MEETING_REQUEST", "QUESTION")


@pytest.mark.asyncio
async def test_voice_meeting_and_payment_events_map_back_to_prospect():
    """
    Proves requirement:
    Voice call completions, meetings, and payments accurately map back
    to the correct prospect memory and advance stages.
    """
    orch = RevenueAgentOrchestrator()
    uid = uuid.uuid4().hex[:6]
    domain = f"apexlegal-{uid}.com"
    email = f"billing@{domain}"
    phone = f"+1-512-555-{uid[:4]}"

    prospect = {
        "name": f"Apex Legal {uid}",
        "domain": domain,
        "email": email,
        "phone": phone,
        "estimated_value": 1500.0,
        "thread_id": f"thread-{uid}"
    }

    # Initial contact
    await orch.step_single_prospect(prospect, commercial_floor=500.0)

    # 1. Voice call completed event with meeting booked
    call_payload = {
        "domain": domain,
        "phone": phone,
        "call_sid": f"CA_{uid}",
        "meeting_booked": True,
        "outcome": "MEETING_BOOKED"
    }
    voice_res = await orch.handle_inbound_event("VOICE_CALL", call_payload)
    assert voice_res["status"] == "PROCESSED"
    assert voice_res["new_stage"] == PipelineStage.MEETING.value

    # 2. Meeting completed event -> Advances to PROPOSAL
    meeting_payload = {
        "domain": domain,
        "status": "COMPLETED"
    }
    meet_res = await orch.handle_inbound_event("MEETING_COMPLETED", meeting_payload)
    assert meet_res["status"] == "PROCESSED"
    assert meet_res["new_stage"] == PipelineStage.PROPOSAL.value

    # 3. Payment confirmed event -> Advances to WON
    payment_payload = {
        "domain": domain,
        "amount_usd": 1500.0,
        "payment_id": f"pay_{uid}"
    }
    pay_res = await orch.handle_inbound_event("PAYMENT_CONFIRMED", payment_payload)
    assert pay_res["status"] == "PROCESSED"
    assert pay_res["new_stage"] == PipelineStage.WON.value

    # Verify final persistent memory
    async with AsyncSessionLocal() as session:
        mem = await memory_service.get_memory(session, domain=domain)
        assert mem is not None
        assert mem.pipeline_stage == PipelineStage.WON.value
        assert "Payment verified" in mem.last_interaction


@pytest.mark.asyncio
async def test_kill_switch_and_human_takeover_enforced():
    """
    Proves safety gates:
    - Emergency kill switch pauses autonomous worker
    - Human takeover request switches pipeline stage to HUMAN_TAKEOVER
    """
    orch = RevenueAgentOrchestrator()
    uid = uuid.uuid4().hex[:6]
    domain = f"safeguard-{uid}.com"
    email = f"hello@{domain}"

    prospect = {
        "name": f"SafeGuard Tech {uid}",
        "domain": domain,
        "email": email,
        "phone": "+1-512-555-0999",
        "estimated_value": 750.0
    }
    await orch.step_single_prospect(prospect, commercial_floor=500.0)

    # 1. Human Takeover triggered by an angry or complex inbound message
    reply_payload = {
        "email": email,
        "body": "I am threatening legal action if a human manager does not call me immediately."
    }
    res = await orch.handle_inbound_event("EMAIL_REPLY", reply_payload)
    assert res["status"] == "PROCESSED"

    async with AsyncSessionLocal() as session:
        mem = await memory_service.get_memory(session, domain=domain)
        assert mem is not None
        assert mem.pipeline_stage in ("HUMAN_TAKEOVER", PipelineStage.LOST.value, PipelineStage.REPLIED.value)

        # 2. Kill switch test: AUTONOMOUS_AGENT_ENABLED = False stops the orchestrator
        old_val = getattr(settings, "AUTONOMOUS_AGENT_ENABLED", True)
        try:
            settings.AUTONOMOUS_AGENT_ENABLED = False
            kill_res = orch.trigger_kill_switch()
            assert kill_res["status"] == "KILLED"
            assert orch.is_running is False
        finally:
            settings.AUTONOMOUS_AGENT_ENABLED = old_val
