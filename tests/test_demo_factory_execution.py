"""
Agency OS — Focused Tests for Workstream B: Demo Factory Execution.
Verifies Trigger Gate (B1), Persistent Job Deduplication (B2),
Canonical Spec Persistence (B3), Tool Orchestration (B4),
Code & n8n Artifact Generation (B5/B6), Sandbox Deployment (B7),
Build Capture (B8), 20-Gate QA (B9), Bounded Repair (B10),
Deployment URL (B11/B12), and Autonomous Worker Execution (B13/B14/B15).
"""
import pytest
from datetime import datetime
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business,
    CustomerProject,
    DemoBuildJob,
    PipelineStage,
    ProjectStatus
)
from app.delivery.demo_job_manager import DemoJobManager, TriggerGateRejectedError
from app.builder.pipeline import pipeline_orchestrator
from app.orchestrator.worker import PersistentAgencyWorker


@pytest.mark.asyncio
async def test_demo_trigger_gate_rejection():
    """B1: Verify trigger gate strictly rejects interested/qualified stages without explicit demo request."""
    async with AsyncSessionLocal() as session:
        # Create prospect in INTERESTED stage without demo_requested
        biz = Business(
            domain="interested-firm.com",
            name="Interested Firm",
            country="US",
            niche="Legal Services",
            public_email="contact@interested-firm.com",
            pipeline_stage="INTERESTED",
            demo_requested=False,
            created_at=datetime.utcnow()
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Attempt to create demo job -> Must raise TriggerGateRejectedError
        with pytest.raises(TriggerGateRejectedError):
            await DemoJobManager.create_or_get_job(session, biz.id)

        # Now test QUALIFIED_REPLY without demo_requested
        biz.pipeline_stage = "QUALIFIED_REPLY"
        await session.commit()
        with pytest.raises(TriggerGateRejectedError):
            await DemoJobManager.create_or_get_job(session, biz.id)

        # Now test DEMO_REQUIREMENTS_REQUIRED without demo_requested
        biz.pipeline_stage = "DEMO_REQUIREMENTS_REQUIRED"
        await session.commit()
        with pytest.raises(TriggerGateRejectedError):
            await DemoJobManager.create_or_get_job(session, biz.id)


@pytest.mark.asyncio
async def test_demo_trigger_gate_acceptance():
    """B1: Verify trigger gate accepts explicit demo request."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            domain="valid-demo-target.com",
            name="Valid Demo Target",
            country="US",
            niche="Healthcare Services",
            public_email="owner@valid-demo-target.com",
            pipeline_stage=PipelineStage.DEMO_REQUESTED.value,
            demo_requested=True,
            created_at=datetime.utcnow()
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        job, is_created = await DemoJobManager.create_or_get_job(session, biz.id)
        assert is_created is True
        assert job.business_id == biz.id
        assert job.status == ProjectStatus.DEMO_REQUESTED.value
        assert job.customer_slug == "valid-demo-target"


@pytest.mark.asyncio
async def test_persistent_job_deduplication():
    """B2: Verify multiple trigger calls return existing job without duplicating."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            domain="dedupe-target.com",
            name="Dedupe Target",
            country="US",
            niche="HVAC Services",
            public_email="info@dedupe-target.com",
            pipeline_stage=PipelineStage.DEMO_REQUESTED.value,
            demo_requested=True,
            created_at=datetime.utcnow()
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        req_id = "req_custom_dedupe_12345"
        job1, created1 = await DemoJobManager.create_or_get_job(session, biz.id, request_id=req_id)
        assert created1 is True

        # Second call with same request_id
        job2, created2 = await DemoJobManager.create_or_get_job(session, biz.id, request_id=req_id)
        assert created2 is False
        assert job2.id == job1.id
        assert job2.demo_id == job1.demo_id

        # Third call without request_id but for same business
        job3, created3 = await DemoJobManager.create_or_get_job(session, biz.id)
        assert created3 is False
        assert job3.id == job1.id


@pytest.mark.asyncio
async def test_full_autonomous_demo_build_pipeline():
    """B3-B12: Verify full autonomous pipeline execution, artifacts, n8n webhook, QA, and deployment."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            domain="crestview-logistics.com",
            name="Crestview Logistics",
            country="US",
            public_email="dispatch@crestview-logistics.com",
            niche="Supply Chain & Freight Dispatch",
            pipeline_stage=PipelineStage.DEMO_REQUESTED.value,
            demo_requested=True,
            created_at=datetime.utcnow()
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # 1. Initialize project and job
        job, _ = await DemoJobManager.create_or_get_job(session, biz.id)
        project = await pipeline_orchestrator.get_or_create_project(session, biz.id)
        assert project is not None
        assert project.customer_slug == "crestview-logistics"

        # 2. Run pipeline
        res = await pipeline_orchestrator.run_pipeline(session, project.project_id)
        assert res.get("success") is True
        assert res.get("status") == ProjectStatus.DEMO_READY.value
        assert res.get("qa_score") >= 90
        assert "/demo/crestview-logistics" in res.get("demo_url")

        # 3. Verify job and project state
        await session.refresh(job)
        assert job.status == ProjectStatus.DEMO_READY.value
        assert job.deployment_url is not None
        assert job.completed_at is not None

        # 4. Verify generated build artifacts including B6 (n8n_automation.json)
        await session.refresh(project)
        latest_build = project.builds[-1]
        manifest = latest_build.artifacts_manifest
        assert "index.html" in manifest
        assert "styles.css" in manifest
        assert "app.js" in manifest
        assert "spec.json" in manifest
        assert "ai_config.json" in manifest
        assert "n8n_automation.json" in manifest


@pytest.mark.asyncio
async def test_worker_drain_demo_backlog_idempotency():
    """B13-B15: Verify autonomous worker drains demo backlog idempotently across restarts."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            domain="apex-sol.com",
            name="Apex Solutions",
            country="US",
            niche="Information Technology",
            public_email="admin@apex-sol.com",
            pipeline_stage=PipelineStage.DEMO_REQUESTED.value,
            demo_requested=True,
            created_at=datetime.utcnow()
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        worker = PersistentAgencyWorker()

        # First run: picks up pending DEMO_REQUESTED businesses, initializes project/job, runs pipeline
        completed = await worker.drain_demo_backlog(session, limit=5)
        assert completed >= 1

        # Second run (simulating next worker cycle / restart): no pending jobs remain
        second_run = await worker.drain_demo_backlog(session, limit=5)
        assert second_run == 0
