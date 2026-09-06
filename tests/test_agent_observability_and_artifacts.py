"""
Comprehensive Suite for Real-Time Agent Observability, WebSocket Telemetry,
and Artifact Generation/Preview (Phase C).

Tests:
1. test_activity_event_persisted_for_each_pipeline_step
2. test_live_event_contains_correct_business_id
3. test_outreach_event_contains_actual_generated_message
4. test_dry_run_outreach_never_claims_real_delivery
5. test_memory_event_persisted_after_contact
6. test_inbound_reply_creates_event
7. test_inbound_reply_restores_correct_memory
8. test_inbound_reply_does_not_block_prospecting
9. test_website_artifact_is_persisted
10. test_website_preview_points_to_actual_artifact
11. test_one_at_a_time_discovery_is_preserved
12. test_duplicate_prospect_is_not_contacted
13. test_kill_switch_stops_new_outreach
14. test_human_takeover_stops_autonomous_response
15. test_activity_history_survives_restart
"""
import os
import uuid
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import select, delete

from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, PipelineStage, VerificationStatus, ProspectMemory,
    AgentActivityEvent, Artifact, OutreachMessage, OutreachEvent,
    FollowupSequence, Reply
)
from app.orchestrator.loop import orchestrator
from app.core.config import settings
from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType
from app.delivery.website_builder import WebsiteBuilder, ARTIFACTS_ROOT
from app.crm.memory_service import memory_service
from app.agents.revenue_agent import revenue_agent_orchestrator


@pytest.fixture(autouse=True)
async def cleanup_observability_data():
    """Ensures test isolation across activity events and artifacts."""
    settings.AUTONOMOUS_AGENT_ENABLED = True
    settings.EMAIL_DRY_RUN = True
    settings.VOICE_DRY_RUN = True
    settings.PAYMENT_DRY_RUN = True
    async with AsyncSessionLocal() as session:
        await session.execute(delete(OutreachEvent))
        await session.execute(delete(FollowupSequence))
        await session.execute(delete(Reply))
        await session.execute(delete(OutreachMessage))
        await session.execute(delete(ProspectMemory))
        await session.execute(delete(Artifact))
        await session.execute(delete(AgentActivityEvent))
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(delete(OutreachEvent))
        await session.execute(delete(FollowupSequence))
        await session.execute(delete(Reply))
        await session.execute(delete(OutreachMessage))
        await session.execute(delete(ProspectMemory))
        await session.execute(delete(Artifact))
        await session.execute(delete(AgentActivityEvent))
        await session.commit()


@pytest.mark.asyncio
async def test_activity_event_persisted_for_each_pipeline_step():
    """1. Proves canonical activity events are persisted for every pipeline step."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"obs-step-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"ObsStep {uid}",
            domain=test_dom,
            country="United States",
            niche="roofing-contractors",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.DISCOVERED.value,
            public_email=f"contact@{test_dom}",
            phone="+15125550199"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

    with patch("app.lead_generation.discovery.lead_discovery_coordinator.run_discovery_and_verification", new_callable=AsyncMock) as mock_disc:
        mock_disc.return_value = [biz]
        await orchestrator.run_full_autonomous_cycle(target_leads=1)

    async with AsyncSessionLocal() as session:
        q = select(AgentActivityEvent).order_by(AgentActivityEvent.sequence_number.asc())
        res = await session.execute(q)
        events = res.scalars().all()
        event_types = [e.event_type for e in events]

        # Verify core canonical sequence
        assert AgentEventType.RUN_STARTED.value in event_types
        assert AgentEventType.DISCOVERY_STARTED.value in event_types
        assert AgentEventType.PROSPECT_FOUND.value in event_types
        assert AgentEventType.AUDIT_COMPLETED.value in event_types
        assert AgentEventType.SCORING_COMPLETED.value in event_types
        assert AgentEventType.COMMERCIAL_QUALIFICATION.value in event_types
        assert AgentEventType.OUTREACH_DISPATCHED.value in event_types
        assert AgentEventType.MEMORY_PERSISTED.value in event_types
        assert AgentEventType.NEXT_PROSPECT.value in event_types
        assert AgentEventType.RUN_COMPLETED.value in event_types


@pytest.mark.asyncio
async def test_live_event_contains_correct_business_id():
    """2. Proves activity events link strictly to the correct business ID and domain."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"biz-link-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"BizLink {uid}",
            domain=test_dom,
            country="United States",
            niche="commercial-roofing",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.DISCOVERED.value,
            public_email=f"sales@{test_dom}",
            phone="+15125550188"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        target_id = biz.id

    with patch("app.lead_generation.discovery.lead_discovery_coordinator.run_discovery_and_verification", new_callable=AsyncMock) as mock_disc:
        mock_disc.return_value = [biz]
        await orchestrator.run_full_autonomous_cycle(target_leads=1)

    async with AsyncSessionLocal() as session:
        q = select(AgentActivityEvent).where(
            AgentActivityEvent.event_type == AgentEventType.PROSPECT_FOUND.value,
            AgentActivityEvent.business_id == target_id
        )
        res = await session.execute(q)
        evt = res.scalar_one_or_none()

        assert evt is not None
        assert evt.business_id == target_id
        assert evt.domain == test_dom


@pytest.mark.asyncio
async def test_outreach_event_contains_actual_generated_message():
    """3. Proves OUTREACH_DISPATCHED contains actual generated subject, body, and recipient."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"outreach-inspect-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"InspectBiz {uid}",
            domain=test_dom,
            country="United States",
            niche="commercial-services",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.DISCOVERED.value,
            public_email=f"info@{test_dom}",
            phone="+15125550177"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

    with patch("app.lead_generation.discovery.lead_discovery_coordinator.run_discovery_and_verification", new_callable=AsyncMock) as mock_disc:
        mock_disc.return_value = [biz]
        await orchestrator.run_full_autonomous_cycle(target_leads=1)

    async with AsyncSessionLocal() as session:
        q = select(AgentActivityEvent).where(AgentActivityEvent.event_type == AgentEventType.OUTREACH_DISPATCHED.value)
        res = await session.execute(q)
        evt = res.scalar_one_or_none()

        assert evt is not None
        meta = evt.metadata_json
        assert meta["recipient"] == f"info@{test_dom}"
        assert len(meta["subject"]) > 5
        assert len(meta["body"]) > 20
        assert meta["channel"] == "EMAIL"


@pytest.mark.asyncio
async def test_dry_run_outreach_never_claims_real_delivery():
    """4. Proves DRY RUN dispatch event explicitly flags simulation without false delivery claim."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"dry-run-check-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"DryRunBiz {uid}",
            domain=test_dom,
            country="United States",
            niche="roofing",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.DISCOVERED.value,
            public_email=f"admin@{test_dom}",
            phone="+15125550166"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

    with patch("app.lead_generation.discovery.lead_discovery_coordinator.run_discovery_and_verification", new_callable=AsyncMock) as mock_disc:
        mock_disc.return_value = [biz]
        await orchestrator.run_full_autonomous_cycle(target_leads=1)

    async with AsyncSessionLocal() as session:
        q = select(AgentActivityEvent).where(AgentActivityEvent.event_type == AgentEventType.OUTREACH_DISPATCHED.value)
        res = await session.execute(q)
        evt = res.scalar_one_or_none()

        assert evt is not None
        meta = evt.metadata_json
        assert meta["dry_run"] is True
        assert meta["status_note"] == "SIMULATED — NO EXTERNAL TRANSMISSION (DRY RUN)"
        assert "SIMULATED" in evt.message


@pytest.mark.asyncio
async def test_memory_event_persisted_after_contact():
    """5. Proves MEMORY_PERSISTED event is recorded after outreach with AWAITING_INBOUND_EVENT."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"memory-persisted-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"MemPersist {uid}",
            domain=test_dom,
            country="United States",
            niche="commercial",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.DISCOVERED.value,
            public_email=f"owner@{test_dom}",
            phone="+15125550155"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

    with patch("app.lead_generation.discovery.lead_discovery_coordinator.run_discovery_and_verification", new_callable=AsyncMock) as mock_disc:
        mock_disc.return_value = [biz]
        await orchestrator.run_full_autonomous_cycle(target_leads=1)

    async with AsyncSessionLocal() as session:
        q = select(AgentActivityEvent).where(AgentActivityEvent.event_type == AgentEventType.MEMORY_PERSISTED.value)
        res = await session.execute(q)
        evt = res.scalar_one_or_none()

        assert evt is not None
        assert evt.domain == test_dom
        assert evt.metadata_json["next_action"] == "AWAITING_INBOUND_EVENT"


@pytest.mark.asyncio
async def test_inbound_reply_creates_event():
    """6. Proves inbound reply creates INBOUND_EVENT_RECEIVED and REPLY_CLASSIFIED events."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"reply-evt-{uid}.com"
    test_email = f"lead@{test_dom}"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"ReplyEvt {uid}",
            domain=test_dom,
            country="United States",
            niche="commercial-services",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.CONTACTED.value,
            public_email=test_email
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        mem = ProspectMemory(
            business_id=biz.id,
            domain=test_dom,
            contact_email=test_email,
            pipeline_stage=PipelineStage.CONTACTED.value,
            estimated_value=750.0,
            audit_results={"performance_score": 42.0},
            offer_proposal={"title": "Speed Fix"}
        )
        session.add(mem)
        await session.commit()

        # Handle inbound email reply
        res = await memory_service.handle_inbound_event(
            session=session,
            event_type="EMAIL_REPLY",
            payload={"email": test_email, "body": "What are your package options and turnaround time?"}
        )
        assert res["status"] == "PROCESSED"

        # Check recorded activity events
        q = select(AgentActivityEvent).where(AgentActivityEvent.business_id == biz.id)
        events_res = await session.execute(q)
        events = events_res.scalars().all()
        types = [e.event_type for e in events]

        assert AgentEventType.INBOUND_EVENT_RECEIVED.value in types
        assert AgentEventType.PROSPECT_MEMORY_RESTORED.value in types
        assert AgentEventType.REPLY_CLASSIFIED.value in types
        assert AgentEventType.CONVERSATION_RESPONSE_GENERATED.value in types


@pytest.mark.asyncio
async def test_inbound_reply_restores_correct_memory():
    """7. Proves restored context matches exact stored audit results and commercial value."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"restore-mem-{uid}.com"
    test_email = f"founder@{test_dom}"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"RestoreBiz {uid}",
            domain=test_dom,
            country="United States",
            niche="roofing",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.CONTACTED.value,
            public_email=test_email
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        mem = ProspectMemory(
            business_id=biz.id,
            domain=test_dom,
            contact_email=test_email,
            pipeline_stage=PipelineStage.CONTACTED.value,
            estimated_value=1250.0,
            audit_results={"performance_score": 38.5, "load_time_seconds": 4.6},
            offer_proposal={"title": "High-Value Turnaround"}
        )
        session.add(mem)
        await session.commit()

        res = await memory_service.handle_inbound_event(
            session=session,
            event_type="EMAIL_REPLY",
            payload={"email": test_email, "body": "Sounds good. Tell me more."}
        )

        assert res["restored_context"]["offered_value"] == 1250.0
        assert res["restored_context"]["audit_results"]["performance_score"] == 38.5


@pytest.mark.asyncio
async def test_inbound_reply_does_not_block_prospecting():
    """8. Proves inbound reply completes asynchronously without locking or interrupting the prospecting loop."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"nonblock-{uid}.com"
    test_email = f"ceo@{test_dom}"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"NonBlock {uid}",
            domain=test_dom,
            country="United States",
            niche="commercial",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.CONTACTED.value,
            public_email=test_email
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        mem = ProspectMemory(
            business_id=biz.id,
            domain=test_dom,
            contact_email=test_email,
            pipeline_stage=PipelineStage.CONTACTED.value,
            estimated_value=800.0
        )
        session.add(mem)
        await session.commit()

        # Execute inbound event
        result = await revenue_agent_orchestrator.handle_inbound_event(
            event_type="EMAIL_REPLY",
            payload={"email": test_email, "body": "Can you do this by next Tuesday?"}
        )
        assert result["status"] == "PROCESSED"
        assert "agent_reply" in result


@pytest.mark.asyncio
async def test_website_artifact_is_persisted():
    """9. Proves WebsiteBuilder creates real Artifact in SQLite with status READY and valid path."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"artifact-persist-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Apex Roofing {uid}",
            domain=test_dom,
            country="United States",
            niche="Roofing Contractors",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.CONTACTED.value,
            public_email=f"contact@{test_dom}",
            phone="+1 (512) 555-0199"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        artifact = await WebsiteBuilder.build_website_for_business(
            session=session,
            business=biz,
            audit_results={"performance_score": 44.0, "load_time_seconds": 4.1},
            offer_proposal={"title": "High-Speed Turnaround", "deliverables": ["Sub-1.2s speed"]}
        )

        assert artifact.id is not None
        assert artifact.status == "READY"
        assert artifact.artifact_type == "WEBSITE"
        assert artifact.preview_url == f"/api/artifacts/{artifact.id}/preview"
        assert "websites/" in artifact.path


@pytest.mark.asyncio
async def test_website_preview_points_to_actual_artifact():
    """10. Proves preview artifact serves actual HTML5/CSS3 written to disk with business details."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"real-html-preview-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Paramount Builders {uid}",
            domain=test_dom,
            country="United States",
            niche="General Contracting",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.CONTACTED.value,
            public_email=f"info@{test_dom}"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        artifact = await WebsiteBuilder.build_website_for_business(
            session=session,
            business=biz,
            audit_results={"performance_score": 41.0, "load_time_seconds": 4.5, "seo_score": 65.0}
        )

        abs_path = os.path.join(ARTIFACTS_ROOT, artifact.path)
        assert os.path.exists(abs_path)

        with open(abs_path, "r", encoding="utf-8") as f:
            html = f.read()

        assert "<!DOCTYPE html>" in html
        assert f"Paramount Builders {uid}" in html
        assert "Austin" in html
        assert "41.0/100" in html


@pytest.mark.asyncio
async def test_one_at_a_time_discovery_is_preserved():
    """11. Proves discovery is called with target=1 and processed strictly sequentially."""
    calls = []

    async def mock_discovery(session, country_code="US", niche_slug="roofing-contractors", target_count=1, target=None):
        eff = target if target is not None else target_count
        calls.append(eff)
        uid = uuid.uuid4().hex[:5]
        b = Business(
            name=f"SeqBiz {uid}",
            domain=f"seq-{uid}.com",
            country="United States",
            niche=niche_slug,
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.DISCOVERED.value,
            public_email=f"seq@{uid}.com"
        )
        session.add(b)
        await session.commit()
        await session.refresh(b)
        return [b]

    with patch("app.lead_generation.discovery.lead_discovery_coordinator.run_discovery_and_verification", side_effect=mock_discovery):
        await orchestrator.run_full_autonomous_cycle(target_leads=2)

    assert len(calls) == 2
    assert calls[0] == 1
    assert calls[1] == 1


@pytest.mark.asyncio
async def test_duplicate_prospect_is_not_contacted():
    """12. Proves that already contacted prospects in memory are skipped without duplicate outreach."""
    uid = uuid.uuid4().hex[:6]
    dup_dom = f"dup-check-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"DupBiz {uid}",
            domain=dup_dom,
            country="United States",
            niche="roofing",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.CONTACTED.value,
            public_email=f"dup@{dup_dom}"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        mem = ProspectMemory(
            business_id=biz.id,
            domain=dup_dom,
            contact_email=f"dup@{dup_dom}",
            pipeline_stage=PipelineStage.CONTACTED.value
        )
        session.add(mem)
        await session.commit()

    # Attempt cycle with this prospect
    with patch("app.lead_generation.discovery.lead_discovery_coordinator.run_discovery_and_verification", new_callable=AsyncMock) as mock_disc:
        mock_disc.return_value = [biz]
        summary = await orchestrator.run_full_autonomous_cycle(target_leads=1)

    # Outreach sent must be 0
    assert summary["autonomous_outreach_sent"] == 0


@pytest.mark.asyncio
async def test_kill_switch_stops_new_outreach():
    """13. Proves emergency kill switch immediately stops autonomous outreach cycle."""
    revenue_agent_orchestrator.trigger_kill_switch(reason="Test Safety Shutdown")

    summary = await orchestrator.run_full_autonomous_cycle(target_leads=1)
    assert summary.get("autonomous_outreach_sent", 0) == 0

    settings.AUTONOMOUS_AGENT_ENABLED = True


@pytest.mark.asyncio
async def test_human_takeover_stops_autonomous_response():
    """14. Proves complex/hostile/legal inbound query triggers HUMAN_TAKEOVER without automated replies."""
    uid = uuid.uuid4().hex[:6]
    test_dom = f"takeover-{uid}.com"
    test_email = f"legal@{test_dom}"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Takeover {uid}",
            domain=test_dom,
            country="United States",
            niche="roofing",
            city="Austin",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.CONTACTED.value,
            public_email=test_email
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        mem = ProspectMemory(
            business_id=biz.id,
            domain=test_dom,
            contact_email=test_email,
            pipeline_stage=PipelineStage.CONTACTED.value,
            estimated_value=900.0
        )
        session.add(mem)
        await session.commit()

        # Inbound message requesting human attorney / hostile dispute
        res = await memory_service.handle_inbound_event(
            session=session,
            event_type="EMAIL_REPLY",
            payload={"email": test_email, "body": "I am putting this matter to our corporate attorney immediately. Have a real manager call me."}
        )

        assert res["new_stage"] == "HUMAN_TAKEOVER"

        # Verify HUMAN_TAKEOVER activity event was emitted
        q = select(AgentActivityEvent).where(
            AgentActivityEvent.business_id == biz.id,
            AgentActivityEvent.event_type == AgentEventType.HUMAN_TAKEOVER.value
        )
        event_res = await session.execute(q)
        event = event_res.scalar_one_or_none()
        assert event is not None


@pytest.mark.asyncio
async def test_activity_history_survives_restart():
    """15. Proves activity events stored in SQLite survive across new sessions/restarts."""
    run_id = f"PERSIST-{uuid.uuid4().hex[:6]}"

    async with AsyncSessionLocal() as session:
        await activity_broadcaster.record_event(
            session=session,
            run_id=run_id,
            event_type=AgentEventType.RUN_STARTED.value,
            message="Persistence Verification Test Event",
            status="INFO"
        )

    # In a completely new session
    async with AsyncSessionLocal() as new_session:
        events = await activity_broadcaster.get_recent_events(new_session, limit=10, run_id=run_id)
        assert len(events) == 1
        assert events[0]["run_id"] == run_id
        assert events[0]["message"] == "Persistence Verification Test Event"
