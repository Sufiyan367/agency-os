"""
Tests for Phase 19 Architectural Integration:
Wiring the existing 15-stage pipeline into app/acquisition/autonomous_controller.py.

Verifies:
1. INTERESTED reply triggers requirements.
2. Requirements trigger demo generation.
3. Demo is validated by the existing QA engine.
4. Proposal is created only after QA passes.
5. Payment handoff remains dry-run.
6. A failed QA prevents proposal creation.
7. advance_cycle_step correctly detects and processes inbound INTERESTED replies.
"""
import pytest
import os
import uuid
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, AuditFinding, Offer, PipelineStage,
    Proposal, ActiveOutreachLock, Reply
)
from app.delivery.requirements_engine import RequirementsPacket
from app.delivery.demo_factory import DemoGenerationResult
from app.delivery.demo_qa import DemoQAResult, QACheckItem, demo_qa_engine
from app.acquisition.autonomous_controller import autonomous_acquisition_controller
from app.acquisition.controller import active_prospect_controller
from app.core.config import settings


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()


async def create_pipeline_test_business(session: AsyncSession) -> Business:
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name=f"Auto Pipeline Co {uid}",
        domain=f"autopipeline-{uid}.ae",
        country="AE",
        city="Dubai",
        niche="hvac-services",
        public_email=f"info@autopipeline-{uid}.ae",
        email_status="verified",
        pipeline_stage=PipelineStage.CONTACTED.value
    )
    session.add(biz)
    await session.flush()

    audit = AuditRun(
        business_id=biz.id,
        url_audited=f"https://{biz.domain}/",
        performance_score=48.0,
        seo_score=92.0,
        a11y_score=75.0,
        ux_conversion_score=85.0,
        security_score=100.0,
        content_score=88.0,
        overall_health_score=78.0,
        summary="Audit summary: Excessive TTFB and uncompressed hero assets."
    )
    session.add(audit)
    await session.flush()

    f1 = AuditFinding(
        audit_id=audit.id,
        category="Performance",
        finding="High TTFB Latency",
        severity="HIGH",
        evidence="Observed TTFB of 1,450ms on mobile network profile.",
        url=f"https://{biz.domain}/",
        recommended_fix="Implement edge CDN caching.",
        estimated_business_impact="Bounce rate elevated."
    )
    session.add(f1)
    await session.flush()

    offer = Offer(
        business_id=biz.id,
        title="Core Web Vitals & Load Speed Acceleration",
        service_type="Speed Optimization",
        recommended_price=650.0,
        estimated_delivery_days=5,
        deliverables=["Edge CDN caching", "Asset compression"]
    )
    session.add(offer)
    await session.commit()
    await session.refresh(biz)
    return biz


@pytest.mark.asyncio
async def test_interested_reply_triggers_requirements_and_demo():
    """1 & 2: Proves INTERESTED reply triggers requirements and turnkey demo generation."""
    async with AsyncSessionLocal() as session:
        biz = await create_pipeline_test_business(session)

        res = await autonomous_acquisition_controller._step_process_reply(
            session=session,
            business_id=biz.id,
            reply_category="INTERESTED",
            reply_body="Yes, we would like to see the demo for our site."
        )

        assert res["status"] == "SUCCESS"
        assert res["requirements_generated"] is True
        assert isinstance(res["requirements_packet"], RequirementsPacket)
        assert len(res["requirements_packet"].requirements) >= 1
        assert res["requirements_packet"].catalog_price_usd == 650.0

        assert res["demo_generated"] is True
        assert isinstance(res["demo_result"], DemoGenerationResult)
        assert res["demo_result"].success is True
        assert os.path.exists(res["demo_result"].metadata.html_file_path)
        assert os.path.exists(res["demo_result"].metadata.json_spec_path)


@pytest.mark.asyncio
async def test_demo_qa_and_proposal_creation():
    """3 & 4: Proves demo is validated by QA engine and proposal is created only after QA passes."""
    async with AsyncSessionLocal() as session:
        biz = await create_pipeline_test_business(session)

        res = await autonomous_acquisition_controller._step_process_reply(
            session=session,
            business_id=biz.id,
            reply_category="INTERESTED"
        )

        assert res["qa_passed"] is True
        assert isinstance(res["qa_result"], DemoQAResult)
        assert res["qa_result"].overall_passed is True

        assert res["proposal_created"] is True
        assert res["proposal_id"] is not None

        prop = await session.get(Proposal, res["proposal_id"])
        assert prop is not None
        assert prop.business_id == biz.id
        assert prop.total_value == 650.0
        assert prop.advance_required == 260.0  # 40%

        await session.refresh(biz)
        assert biz.pipeline_stage == PipelineStage.PROPOSAL.value


@pytest.mark.asyncio
async def test_payment_handoff_remains_dry_run():
    """5: Proves payment handoff remains strictly in safe dry-run mode with payments disabled."""
    async with AsyncSessionLocal() as session:
        biz = await create_pipeline_test_business(session)

        res = await autonomous_acquisition_controller._step_process_reply(
            session=session,
            business_id=biz.id,
            reply_category="INTERESTED"
        )

        handoff = res["payment_handoff"]
        assert handoff is not None
        assert handoff.business_id == biz.id
        assert handoff.payments_enabled is False
        assert handoff.payment_provider == "dry_run"
        assert handoff.payment_status == "PENDING_AUTHORIZATION"
        assert handoff.approval_requirements == "HUMAN_APPROVAL_REQUIRED"
        assert handoff.catalog_price_usd == 650.0
        assert handoff.advance_required_usd == 260.0


@pytest.mark.asyncio
async def test_failed_qa_prevents_proposal_creation():
    """6: Proves a failed QA strictly prevents proposal creation and blocks pipeline advance."""
    async with AsyncSessionLocal() as session:
        biz = await create_pipeline_test_business(session)

        mock_failed_qa = DemoQAResult(
            demo_id="DEMO-MOCK-FAIL",
            overall_passed=False,
            total_checks=8,
            passed_checks=7,
            failed_checks=1,
            checks=[
                QACheckItem(name="ZERO_PLACEHOLDERS", passed=False, details="Detected template placeholder: {{TODO}}")
            ],
            qa_signature="QA-FAIL",
            error_summary="Detected template placeholder: {{TODO}}"
        )

        with patch.object(demo_qa_engine, "validate_demo", return_value=mock_failed_qa):
            res = await autonomous_acquisition_controller._step_process_reply(
                session=session,
                business_id=biz.id,
                reply_category="INTERESTED"
            )

        assert res["status"] == "QA_FAILED"
        assert res["qa_passed"] is False
        assert res["proposal_created"] is False
        assert res["proposal_id"] is None
        assert res["payment_handoff"] is None
        assert "Detected template placeholder" in res["error_summary"]

        # Ensure NO proposal was created in database
        prop_q = select(Proposal).where(Proposal.business_id == biz.id)
        props = (await session.execute(prop_q)).scalars().all()
        assert len(props) == 0

        # Ensure pipeline stage did NOT advance to PROPOSAL
        await session.refresh(biz)
        assert biz.pipeline_stage != PipelineStage.PROPOSAL.value
        assert biz.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value


@pytest.mark.asyncio
async def test_advance_cycle_step_inbound_reply_advancement():
    """7: Proves advance_cycle_step automatically detects an INTERESTED reply and advances pipeline."""
    async with AsyncSessionLocal() as session:
        await active_prospect_controller.release_active_slot(session, terminal_reason="MANUAL_RELEASE")

        biz = await create_pipeline_test_business(session)
        # Select business into active slot
        slot = await active_prospect_controller.select_next_prospect(session, business_id=biz.id)
        assert slot.is_occupied is True

        # Manually set slot stage to WAITING_FOR_REPLY
        lock = await active_prospect_controller.get_or_create_lock(session)
        lock.current_stage = "WAITING_FOR_REPLY"
        await session.commit()

        # Add an INTERESTED reply from prospect
        reply = Reply(
            business_id=biz.id,
            sender_email=biz.public_email,
            raw_body="We are interested in this speed optimization turnaround. Please send details.",
            classification="INTERESTED"
        )
        session.add(reply)
        await session.commit()

        # Execute one autonomous cycle step
        step_res = await autonomous_acquisition_controller.advance_cycle_step(session)

        assert step_res["status"] == "SUCCESS"
        assert step_res["proposal_created"] is True
        assert step_res["qa_passed"] is True

        # Lock stage advanced to PROPOSAL_READY
        await session.refresh(lock)
        assert lock.current_stage == "PROPOSAL_READY"
