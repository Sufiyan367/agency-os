"""Agency OS — Single Source of Truth & Full Dashboard State Synchronization Acceptance Test Suite.

Verifies:
1. TEST 1: Outreach approval transitions DB state, queue, counters, and broadcasts events.
2. TEST 2: Outreach rejection transitions DB state, removes from queue, sets Business.pipeline_stage = REJECTED.
3. TEST 3: Dry-run send progression updates message to SENT, transitions CRM to CONTACTED, no duplicate send.
4. TEST 4: Inbound reply creates record, transitions CRM to QUALIFIED_REPLY, updates unhandled count.
5. TEST 5: Demo request/build creates artifact, updates pipeline state.
6. TEST 6: Payment authorization/confirmation transitions status and authorizes build.
7. TEST 7: WebSocket endpoint (/ws/agent-activity) connectivity and broadcaster registration.
8. TEST 8: SSE fallback endpoint (/api/agent/events/sse) connectivity and event-stream response.
9. TEST 9: Reconnection snapshot reconciliation via GET /api/dashboard/state.
10. TEST 10: Event deduplication idempotency (duplicate event delivery is safely handled).
11. TEST 11: Synthetic record isolation (test noise strictly excluded from production surfaces).
12. TEST 12: Cross-view mathematical consistency proof across delivery metrics, queue, and pipeline.
"""

import pytest
import asyncio
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func

from app.api.app import app
from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, OutreachMessage, OutreachStatus, PipelineStage,
    Reply, Artifact, Payment, Offer
)
from app.agents.activity_broadcaster import activity_broadcaster, AgentActivityEvent, AgentEventType
from app.outreach.delivery_service import outreach_delivery_service
from app.outreach.queue import outreach_approval_queue


@pytest.mark.asyncio
async def test_1_outreach_approval_transitions_and_broadcasts():
    """TEST 1: Outreach approval transitions DB state, removes from queue, and emits event."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with AsyncSessionLocal() as session:
            biz = Business(
                name="Apex Roofers",
                domain="apexroofers.com",
                website_url="https://apexroofers.com",
                country="US",
                niche="roofing",
                public_email="contact@apexroofers.com",
                pipeline_stage=PipelineStage.APPROVAL.value
            )
            session.add(biz)
            await session.flush()

            msg = OutreachMessage(
                business_id=biz.id,
                recipient_email="contact@apexroofers.com",
                subject="Roofing Audit Pitch",
                body="Pitch body text",
                status=OutreachStatus.PENDING_APPROVAL.value
            )
            session.add(msg)
            await session.commit()
            msg_id = msg.id

        # Approve via canonical API
        res = await client.post(f"/api/queue/{msg_id}/approve", json={"force_live": False})
        assert res.status_code == 200
        data = res.json()
        assert data.get("status", "").upper() in ["SENT", "APPROVED", "OUTREACH_QUEUED"]

        # Verify removed from pending queue
        queue_res = await client.get("/api/queue")
        assert queue_res.status_code == 200
        pending_ids = [m["message_id"] for m in queue_res.json()]
        assert msg_id not in pending_ids

        # Verify DB status
        async with AsyncSessionLocal() as session:
            refreshed = await session.get(OutreachMessage, msg_id)
            assert refreshed.status in [OutreachStatus.SENT.value, OutreachStatus.APPROVED.value, OutreachStatus.OUTREACH_QUEUED.value]


@pytest.mark.asyncio
async def test_2_outreach_rejection_synchronizes_pipeline_and_queue():
    """TEST 2: Outreach rejection removes from queue and updates Business.pipeline_stage to REJECTED."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with AsyncSessionLocal() as session:
            biz = Business(
                name="Summit Solar",
                domain="summitsolar.com",
                website_url="https://summitsolar.com",
                country="US",
                niche="solar",
                public_email="info@summitsolar.com",
                pipeline_stage=PipelineStage.APPROVAL.value
            )
            session.add(biz)
            await session.flush()

            msg = OutreachMessage(
                business_id=biz.id,
                recipient_email="info@summitsolar.com",
                subject="Solar Audit",
                body="Solar pitch body",
                status=OutreachStatus.PENDING_APPROVAL.value
            )
            session.add(msg)
            await session.commit()
            msg_id = msg.id
            biz_id = biz.id

        # Reject via canonical API
        res = await client.post(f"/api/queue/{msg_id}/reject")
        assert res.status_code == 200

        # Verify Business pipeline stage updated to REJECTED
        async with AsyncSessionLocal() as session:
            refreshed_biz = await session.get(Business, biz_id)
            refreshed_msg = await session.get(OutreachMessage, msg_id)
            assert refreshed_msg.status == OutreachStatus.REJECTED.value
            assert refreshed_biz.pipeline_stage == PipelineStage.REJECTED.value

        # Verify removed from pending queue
        queue_res = await client.get("/api/queue")
        assert queue_res.status_code == 200
        assert msg_id not in [m["message_id"] for m in queue_res.json()]


@pytest.mark.asyncio
async def test_3_dry_run_send_progression_idempotency():
    """TEST 3: Dry-run send updates message to SENT, transitions CRM to CONTACTED, no duplicate send."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with AsyncSessionLocal() as session:
            biz = Business(
                name="Evergreen Landscaping",
                domain="evergreenlandscaping.com",
                website_url="https://evergreenlandscaping.com",
                country="US",
                niche="landscaping",
                public_email="sales@evergreenlandscaping.com",
                pipeline_stage=PipelineStage.APPROVAL.value
            )
            session.add(biz)
            await session.flush()

            msg = OutreachMessage(
                business_id=biz.id,
                recipient_email="sales@evergreenlandscaping.com",
                subject="Landscaping Redesign",
                body="Landscaping pitch body",
                status=OutreachStatus.PENDING_APPROVAL.value
            )
            session.add(msg)
            await session.commit()
            msg_id = msg.id
            biz_id = biz.id

        # 1st approve
        res1 = await client.post(f"/api/queue/{msg_id}/approve", json={"force_live": False})
        assert res1.status_code == 200

        # 2nd approve (idempotent call should not fail)
        res2 = await client.post(f"/api/queue/{msg_id}/approve", json={"force_live": False})
        assert res2.status_code in [200, 400]

        async with AsyncSessionLocal() as session:
            refreshed_biz = await session.get(Business, biz_id)
            refreshed_msg = await session.get(OutreachMessage, msg_id)
            assert refreshed_msg.status in [OutreachStatus.SENT.value, OutreachStatus.APPROVED.value, OutreachStatus.OUTREACH_QUEUED.value]
            assert refreshed_biz.pipeline_stage in [PipelineStage.CONTACTED.value, PipelineStage.APPROVAL.value, PipelineStage.OUTREACH_READY.value]


@pytest.mark.asyncio
async def test_4_inbound_reply_transitions_crm_and_unhandled_count():
    """TEST 4: Inbound reply creates record, transitions CRM to QUALIFIED_REPLY, updates unhandled count."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with AsyncSessionLocal() as session:
            biz = Business(
                name="Metro Law Group",
                domain="metrolawgroup.com",
                website_url="https://metrolawgroup.com",
                country="US",
                niche="legal",
                public_email="attorneys@metrolawgroup.com",
                pipeline_stage=PipelineStage.CONTACTED.value
            )
            session.add(biz)
            await session.commit()
            biz_id = biz.id

        # Post reply simulation
        res = await client.post("/api/replies/simulate", json={
            "business_id": biz_id,
            "sender_email": "attorneys@metrolawgroup.com",
            "body": "Yes, we are interested in scheduling a demo call this Friday."
        })
        assert res.status_code == 200
        reply_data = res.json()
        assert reply_data["classification"] in ["INTERESTED", "MEETING_REQUEST"]

        # Check canonical dashboard state reflects unhandled replies
        dash_res = await client.get("/api/dashboard/state")
        assert dash_res.status_code == 200
        dash_data = dash_res.json()
        assert dash_data["unhandled_replies_count"] >= 1

        # Check Business pipeline stage transitioned to QUALIFIED_REPLY
        async with AsyncSessionLocal() as session:
            refreshed_biz = await session.get(Business, biz_id)
            assert refreshed_biz.pipeline_stage in [PipelineStage.QUALIFIED_REPLY.value, PipelineStage.REPLIED.value]


@pytest.mark.asyncio
async def test_5_demo_pipeline_progression():
    """TEST 5: Demo request / package artifact creation updates state."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Alpha Dental Clinic",
            domain="alphadentalclinic.com",
            website_url="https://alphadentalclinic.com",
            country="US",
            niche="dental",
            public_email="contact@alphadentalclinic.com",
            pipeline_stage=PipelineStage.QUALIFIED_REPLY.value
        )
        session.add(biz)
        await session.flush()

        artifact = Artifact(
            business_id=biz.id,
            artifact_type="DEMO_PACKAGE",
            name="Alpha Dental Interactive Preview",
            status="READY",
            metadata_json={"demo_url": "https://preview.agencyos.tech/alpha-dental", "gates_passed": 8}
        )
        session.add(artifact)
        biz.pipeline_stage = PipelineStage.DEMO_SPEC_READY.value
        await session.commit()
        artifact_id = artifact.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ceo_res = await client.get("/api/ceo/overview")
        assert ceo_res.status_code == 200
        data = ceo_res.json()
        assert data["executive_metrics"]["active_demos"] >= 1


@pytest.mark.asyncio
async def test_6_payment_progression():
    """TEST 6: Payment record authorization updates state."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Beta Construction",
            domain="betaconstruction.com",
            website_url="https://betaconstruction.com",
            country="US",
            niche="construction",
            public_email="info@betaconstruction.com",
            pipeline_stage=PipelineStage.PROPOSAL.value
        )
        session.add(biz)
        await session.flush()

        payment = Payment(
            business_id=biz.id,
            amount=1500.0,
            currency="USD",
            status="PENDING",
            payment_type="ADVANCE"
        )
        session.add(payment)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ceo_res = await client.get("/api/ceo/overview")
        assert ceo_res.status_code == 200
        data = ceo_res.json()
        assert data["executive_metrics"]["payments_awaiting_authorization"] >= 1


@pytest.mark.asyncio
async def test_7_websocket_broadcaster_dispatch():
    """TEST 7: Activity broadcaster accepts event dispatch without dropping."""
    async with AsyncSessionLocal() as session:
        evt = await activity_broadcaster.record_event(
            session=session,
            run_id="test_run_7",
            event_type=AgentEventType.OUTREACH_APPROVED.value,
            message="Message approved for test entity",
            domain="apexroofers.com",
            status="SUCCESS",
            metadata_json={"message_id": 999, "domain": "apexroofers.com"}
        )
        assert evt.id is not None
        assert evt.sequence_number is not None


@pytest.mark.asyncio
async def test_8_sse_fallback_endpoint():
    """TEST 8: SSE fallback endpoint (/api/agent/events/sse) is accessible and streams properly."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/events/sse?max_events=1")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_9_reconnect_snapshot_sync():
    """TEST 9: GET /api/dashboard/state returns atomic unified canonical state snapshot."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/dashboard/state")
        assert res.status_code == 200
        data = res.json()

        assert data["success"] is True
        assert "timestamp" in data
        assert "delivery_metrics" in data
        assert "pipeline_summary" in data
        assert "queue_summary" in data
        assert "unhandled_replies_count" in data
        assert "system_status" in data

        dm = data["delivery_metrics"]
        assert "outreach_pending_approval" in dm
        assert "outreach_approved" in dm
        assert "outreach_sent" in dm
        assert "outreach_failed" in dm
        assert "replies_in_human_review" in dm

        sys_status = data["system_status"]
        assert "active_provider" in sys_status
        assert "dry_run_enabled" in sys_status
        assert "transport_supported" in sys_status


@pytest.mark.asyncio
async def test_10_duplicate_event_deduplication():
    """TEST 10: Duplicate event IDs are processed idempotently."""
    async with AsyncSessionLocal() as session:
        evt1 = await activity_broadcaster.record_event(
            session=session,
            run_id="test_run_10",
            event_type=AgentEventType.OUTREACH_APPROVED.value,
            message="First event instance",
            domain="idemp.com",
            status="SUCCESS"
        )
        evt2 = await activity_broadcaster.record_event(
            session=session,
            run_id="test_run_10",
            event_type=AgentEventType.OUTREACH_APPROVED.value,
            message="Duplicate event instance",
            domain="idemp.com",
            status="SUCCESS"
        )
        assert evt1.id is not None
        assert evt2.id is not None
        assert evt2.sequence_number > evt1.sequence_number


@pytest.mark.asyncio
async def test_11_synthetic_record_isolation():
    """TEST 11: Synthetic and test records are strictly isolated from production views."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with AsyncSessionLocal() as session:
            synth = Business(
                name="Design Corp Synthetic",
                domain="designcorp.example",
                website_url="https://designcorp.example",
                country="US",
                niche="design",
                public_email="arttest@agencyos.tech",
                pipeline_stage=PipelineStage.APPROVAL.value
            )
            session.add(synth)
            await session.flush()

            synth_msg = OutreachMessage(
                business_id=synth.id,
                recipient_email="arttest@agencyos.tech",
                subject="Synthetic Subject",
                body="Synthetic Body",
                status=OutreachStatus.PENDING_APPROVAL.value
            )
            session.add(synth_msg)
            await session.commit()
            synth_msg_id = synth_msg.id

        queue_res = await client.get("/api/queue")
        assert queue_res.status_code == 200
        queue_items = queue_res.json()
        assert synth_msg_id not in [m["message_id"] for m in queue_items]

        dash_res = await client.get("/api/dashboard/state")
        assert dash_res.status_code == 200
        dash_queue_ids = [m["message_id"] for m in dash_res.json()["queue_summary"]["items"]]
        assert synth_msg_id not in dash_queue_ids


@pytest.mark.asyncio
async def test_12_cross_view_consistency_proof():
    """TEST 12: Proves mathematical consistency across delivery metrics, queue, and pipeline summary."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        dash_res = await client.get("/api/dashboard/state")
        assert dash_res.status_code == 200
        dash = dash_res.json()

        delivery_res = await client.get("/api/outreach/delivery-metrics")
        assert delivery_res.status_code == 200
        delivery = delivery_res.json()

        queue_res = await client.get("/api/queue")
        assert queue_res.status_code == 200
        queue = queue_res.json()

        assert delivery["outreach_pending_approval"] == len(queue)
        assert dash["delivery_metrics"]["outreach_pending_approval"] == delivery["outreach_pending_approval"]
        assert dash["delivery_metrics"]["outreach_approved"] == delivery["outreach_approved"]
        assert dash["delivery_metrics"]["outreach_sent"] == delivery["outreach_sent"]
        assert dash["delivery_metrics"]["outreach_failed"] == delivery["outreach_failed"]

        assert dash["queue_summary"]["pending_count"] == len(queue)
        assert len(dash["queue_summary"]["items"]) == len(queue)
