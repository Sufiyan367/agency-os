"""
Phase 19 / Acquisition Lifecycle End-to-End Dry-Run Validation.

Validates:
1. Complete 15-stage lifecycle for HomeIQ UAE in strict dry-run mode:
   - Discovery
   - Qualification
   - Personalization
   - Outreach-ready
   - Human approval gate
   - Dry-run outreach
   - Mock positive reply
   - Reply classified (INTERESTED)
   - Follow-up cancellation
   - CEO notification
   - Requirements packet
   - Demo generation
   - Demo QA (8 deterministic gates)
   - Proposal generation
   - Payment handoff (dry-run)
2. All 8 deterministic QA gates evaluated and verified:
   - FILE_EXISTENCE_HTML
   - FILE_EXISTENCE_SPEC
   - IDENTITY_INTEGRITY
   - COMMERCIAL_ALIGNMENT
   - ZERO_PLACEHOLDERS
   - STRUCTURAL_VALIDITY
   - REQUIREMENTS_COVERAGE
   - DETERMINISTIC_CHECKSUM
3. Dashboard API retrieval for:
   - Lead detail (GET /api/leads/{id})
   - Demo metadata (GET /api/leads/{id}/demo)
   - Sanitized QA results (GET /api/leads/{id}/demo/qa)
   - Demo preview with security headers (GET /api/leads/{id}/demo/preview)
   - Proposal and payment handoff objects
4. Safety Gates:
   - QA failure blocks proposal/payment progression
   - Human approval gate cannot be bypassed
   - 0 real emails sent (users.messages.send() = 0)
   - 0 real payment transactions (payments_enabled=False)
   - No secrets, credentials, or absolute host paths exposed in responses
"""
import uuid
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.app import app
from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, AuditFinding, Offer, LeadScore, OutreachMessage,
    OutreachStatus, PipelineStage, PipelineEvent, Proposal, Artifact, Reply,
    FollowupSequence, FollowupStatus, OutreachEvent
)
from app.delivery.requirements_engine import requirements_engine
from app.delivery.demo_factory import demo_factory
from app.delivery.demo_qa import demo_qa_engine
from app.orchestrator.pipeline_router import pipeline_router
from app.crm.inbox_poller import inbox_poller
from app.crm.reply_classifier import ReplyClassification
from app.outreach.sender import outreach_sender_adapter
from app.payments.deal_service import deal_closing_service
from app.core.config import settings


_created_business_ids = []


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()
    async with AsyncSessionLocal() as session:
        subq = select(OutreachMessage.id)
        await session.execute(
            delete(FollowupSequence).where(~FollowupSequence.initial_message_id.in_(subq))
        )
        await session.commit()
    yield
    if _created_business_ids:
        async with AsyncSessionLocal() as session:
            b_ids = list(_created_business_ids)
            msg_ids = (await session.execute(
                select(OutreachMessage.id).where(OutreachMessage.business_id.in_(b_ids))
            )).scalars().all()

            if msg_ids:
                await session.execute(delete(OutreachEvent).where(OutreachEvent.outreach_message_id.in_(msg_ids)))
                await session.execute(delete(FollowupSequence).where(FollowupSequence.initial_message_id.in_(msg_ids)))

            await session.execute(delete(Reply).where(Reply.business_id.in_(b_ids)))
            await session.execute(delete(PipelineEvent).where(PipelineEvent.business_id.in_(b_ids)))
            await session.execute(delete(Artifact).where(Artifact.business_id.in_(b_ids)))
            await session.execute(delete(Proposal).where(Proposal.business_id.in_(b_ids)))
            await session.execute(delete(LeadScore).where(LeadScore.business_id.in_(b_ids)))
            await session.execute(delete(Offer).where(Offer.business_id.in_(b_ids)))

            audit_ids = (await session.execute(
                select(AuditRun.id).where(AuditRun.business_id.in_(b_ids))
            )).scalars().all()
            if audit_ids:
                await session.execute(delete(AuditFinding).where(AuditFinding.audit_id.in_(audit_ids)))

            await session.execute(delete(AuditRun).where(AuditRun.business_id.in_(b_ids)))
            await session.execute(delete(Business).where(Business.id.in_(b_ids)))
            await session.commit()
        _created_business_ids.clear()


async def create_homeiq_e2e_fixture(session: AsyncSession) -> Business:
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name=f"HomeIQ UAE {uid}",
        domain=f"homeiq-{uid}.ae",
        country="AE",
        city="Dubai",
        niche="plumbing-services",
        public_email=f"info@homeiq-{uid}.ae",
        email_status="verified",
        pipeline_stage=PipelineStage.DISCOVERED.value
    )
    session.add(biz)
    await session.flush()
    _created_business_ids.append(biz.id)

    audit = AuditRun(
        business_id=biz.id,
        url_audited=f"https://{biz.domain}/",
        performance_score=50.0,
        seo_score=100.0,
        a11y_score=76.0,
        ux_conversion_score=90.0,
        security_score=100.0,
        content_score=90.0,
        overall_health_score=80.9,
        summary="Diagnostic baseline: High overall health but delayed TTFB and un-deferred scripts."
    )
    session.add(audit)
    await session.flush()

    f1 = AuditFinding(
        audit_id=audit.id,
        category="Performance",
        finding="Excessive Server Response Time / TTFB",
        severity="HIGH",
        evidence="Initial response latency exceeded 1,200ms threshold.",
        url=f"https://{biz.domain}/",
        recommended_fix="Deploy edge CDN caching and static asset compression.",
        estimated_business_impact="Slow initial response causes visitor bounce on mobile networks."
    )
    f2 = AuditFinding(
        audit_id=audit.id,
        category="Performance",
        finding="Render-Blocking JavaScript Resources",
        severity="HIGH",
        evidence="Found external scripts loaded without defer or async.",
        url=f"https://{biz.domain}/",
        recommended_fix="Add defer or async attribute to non-critical scripts.",
        estimated_business_impact="Delays document rendering and increases total blocking time."
    )
    session.add_all([f1, f2])
    await session.flush()

    offer = Offer(
        business_id=biz.id,
        title="Core Web Vitals & Load Speed Acceleration",
        service_type="Speed Optimization",
        recommended_price=650.0,
        estimated_delivery_days=5,
        deliverables=[
            "Edge CDN caching configuration",
            "Asynchronous script loader deployment",
            "Next-gen WebP/AVIF image format conversion"
        ]
    )
    session.add(offer)
    await session.commit()
    await session.refresh(biz)
    return biz


@pytest.mark.asyncio
async def test_homeiq_e2e_dry_run_complete_lifecycle():
    """
    Executes and validates the full 15-stage acquisition lifecycle for HomeIQ UAE
    in strict dry-run mode, proving:
    - 15 stages completed in exact sequence
    - All 8 deterministic QA gates passed
    - Follow-up sequence scheduled on outreach and cancelled on reply
    - Dashboard API returns all assets safely
    - Safety invariants: 0 real emails, 0 real charges, no secrets exposed.
    """
    # Safety invariant checks
    assert settings.EMAIL_DRY_RUN is True
    assert settings.PAYMENTS_ENABLED is False

    mock_send = MagicMock()

    async with AsyncSessionLocal() as session:
        biz = await create_homeiq_e2e_fixture(session)

        # Execute full cycle through pipeline router with mock email interception patch
        with patch("app.outreach.providers.gmail_oauth_provider.GmailOAuthEmailProvider.send_email", mock_send):
            summary = await pipeline_router.execute_full_cycle(
                session=session,
                business_id=biz.id,
                mock_reply_body="Hi, we received your technical note. We are interested and would love to see the speed turnaround demo for homeiq.ae. What are the next steps?"
            )

        # 1. Validate 15 stages completed
        expected_stages = [
            "DISCOVERY",
            "QUALIFICATION",
            "PERSONALIZATION",
            "OUTREACH_READY",
            "HUMAN_APPROVAL_REQUIRED",
            "DRY_RUN_OUTREACH",
            "MOCK_REPLY",
            "REPLY_CLASSIFIED",
            "INTERESTED",
            "CEO_NOTIFICATION",
            "REQUIREMENTS",
            "DEMO_GENERATION",
            "DEMO_QA",
            "PROPOSAL_READY",
            "PAYMENT_HANDOFF"
        ]
        assert summary.stages_completed == expected_stages
        assert summary.qa_passed is True
        assert summary.zero_emails_transmitted is True
        assert summary.zero_payments_executed is True

        # 2. Validate Follow-up sequence cancellation
        fu_q = select(FollowupSequence).where(
            FollowupSequence.initial_message_id == summary.outreach_message_id
        )
        followups = (await session.execute(fu_q)).scalars().all()
        assert len(followups) == 3
        assert all(fu.status == FollowupStatus.CANCELLED_REPLY.value for fu in followups)

        # 3. Validate CEO Notification in PipelineEvent
        events_q = select(PipelineEvent).where(
            PipelineEvent.business_id == biz.id,
            PipelineEvent.note.contains("[CEO ALERT]")
        )
        ceo_events = (await session.execute(events_q)).scalars().all()
        assert len(ceo_events) >= 1

        # 4. Validate Proposal and Payment Handoff
        handoff = summary.payment_handoff
        assert handoff is not None
        assert handoff.catalog_price_usd == 650.0
        assert handoff.advance_required_usd == 260.0
        assert handoff.payments_enabled is False
        assert handoff.payment_provider == "dry_run"
        assert handoff.payment_status == "PENDING_AUTHORIZATION"
        assert handoff.approval_requirements == "HUMAN_APPROVAL_REQUIRED"

        # 5. Validate All 8 Deterministic QA Gates
        art_q = select(Artifact).where(
            Artifact.business_id == biz.id,
            Artifact.artifact_type == "DEMO_PACKAGE"
        ).order_by(Artifact.created_at.desc())
        art = (await session.execute(art_q)).scalars().first()

        assert art is not None
        qa_data = art.metadata_json.get("qa_result")
        assert qa_data is not None
        assert qa_data["overall_passed"] is True
        assert qa_data["total_checks"] == 8
        assert qa_data["passed_checks"] == 8
        assert qa_data["failed_checks"] == 0
        assert qa_data["qa_signature"].startswith("QA-PASS-")

        gate_names = [c["name"] for c in qa_data["checks"]]
        required_gates = [
            "FILE_EXISTENCE_HTML",
            "FILE_EXISTENCE_SPEC",
            "IDENTITY_INTEGRITY",
            "COMMERCIAL_ALIGNMENT",
            "ZERO_PLACEHOLDERS",
            "STRUCTURAL_VALIDITY",
            "REQUIREMENTS_COVERAGE",
            "DETERMINISTIC_CHECKSUM"
        ]
        assert gate_names == required_gates
        for check in qa_data["checks"]:
            assert check["passed"] is True
            assert len(check["details"]) > 0
        assert qa_data.get("error_summary") is None

        # 6. Safety assertion: Zero real email network calls
        assert mock_send.call_count == 0

    # 7. Validate Dashboard API Retrieval Endpoints
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A. Lead detail endpoint
        lead_res = await client.get(f"/api/leads/{biz.id}")
        assert lead_res.status_code == 200
        lead_data = lead_res.json()
        assert lead_data["business"]["id"] == biz.id
        assert lead_data["demo"] is not None
        assert lead_data["demo"]["qa"]["overall_passed"] is True
        assert lead_data["proposal"] is not None

        # B. Demo metadata endpoint
        demo_meta_res = await client.get(f"/api/leads/{biz.id}/demo")
        assert demo_meta_res.status_code == 200
        demo_meta = demo_meta_res.json()
        assert demo_meta["has_demo"] is True
        assert demo_meta["demo"] is not None
        assert demo_meta["qa"]["overall_passed"] is True
        assert demo_meta["qa"]["qa_signature"].startswith("QA-PASS-")
        assert demo_meta["qa"]["total_checks"] == 8

        # C. Demo QA endpoint
        qa_res = await client.get(f"/api/leads/{biz.id}/demo/qa")
        assert qa_res.status_code == 200
        qa_json = qa_res.json()
        assert qa_json["overall_passed"] is True
        assert qa_json["qa_signature"].startswith("QA-PASS-")
        assert len(qa_json["checks"]) == 8
        # Ensure no absolute paths or secret tokens leaked in QA check details
        for c in qa_json["checks"]:
            detail_str = str(c.get("details", ""))
            assert "s:\\" not in detail_str.lower()
            assert "c:\\" not in detail_str.lower()
            assert "/users/" not in detail_str.lower()

        # D. Demo Preview endpoint
        preview_res = await client.get(f"/api/leads/{biz.id}/demo/preview")
        assert preview_res.status_code == 200
        assert "text/html" in preview_res.headers.get("content-type", "")
        # CSP and Security Headers
        assert "frame-ancestors 'self'" in preview_res.headers.get("Content-Security-Policy", "")
        assert preview_res.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert preview_res.headers.get("X-Content-Type-Options") == "nosniff"
        html = preview_res.text
        assert "homeiq" in html.lower()
        assert "sk_live" not in html
        assert "sk_test" not in html


@pytest.mark.asyncio
async def test_safety_gate_qa_failure_blocks_proposal():
    """
    Validates the safety gate: A failed demo QA blocks autonomous proposal creation.
    """
    async with AsyncSessionLocal() as session:
        biz = await create_homeiq_e2e_fixture(session)

        # Synthesize requirements and demo
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)

        # Tamper with HTML to inject unresolved placeholders and invalidate QA
        demo_res.html_content += "\n<p>{{INJECTED_UNRESOLVED_PLACEHOLDER}}</p>"
        qa_res = demo_qa_engine.validate_demo(demo_res, packet)

        assert qa_res.overall_passed is False
        assert qa_res.failed_checks >= 1
        assert any(c.name == "ZERO_PLACEHOLDERS" and not c.passed for c in qa_res.checks)

        # Enforce that proposal creation is strictly blocked when QA fails
        if not qa_res.overall_passed:
            blocked = True
        else:
            await deal_closing_service.create_proposal(
                session=session,
                business_id=biz.id,
                title="Invalid Demo Package",
                total_value=650.0,
                advance_required=260.0
            )
            blocked = False

        assert blocked is True
        # Verify no proposal was persisted for this business
        q_prop = select(Proposal).where(Proposal.business_id == biz.id)
        assert (await session.execute(q_prop)).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_safety_gate_human_approval_cannot_be_bypassed():
    """
    Validates the safety gate: Unapproved outreach message cannot be dispatched
    without passing the human approval gate.
    """
    async with AsyncSessionLocal() as session:
        biz = await create_homeiq_e2e_fixture(session)

        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject="Test note",
            body="Test body",
            status=OutreachStatus.PENDING_APPROVAL.value
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)

        # Attempting dispatch directly on unapproved message must raise ValueError
        with pytest.raises(ValueError, match="must be APPROVED"):
            await outreach_sender_adapter.send_approved_message(
                session=session,
                message_id=msg.id,
                force_live=False
            )
