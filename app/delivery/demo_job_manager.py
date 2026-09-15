"""
Agency OS — Demo Job Manager (Phase Execution: Demo Factory B1/B2)
Handles Trigger Gate Verification (B1), Persistent Job Deduplication (B2),
and Lifecycle State Transitions for Demo Build Jobs.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Business,
    DemoBuildJob,
    ProjectStatus,
    PipelineStage
)

logger = logging.getLogger("agency.demo_job_manager")

ALLOWED_DEMO_STAGES = {
    PipelineStage.DEMO_REQUESTED.value,
    ProjectStatus.DEMO_REQUESTED.value,
}

REJECTED_TRIGGER_STAGES = {
    "INTERESTED",
    "QUALIFIED_REPLY",
    "DEMO_REQUIREMENTS_REQUIRED",
    PipelineStage.DISCOVERED.value,
    PipelineStage.QUALIFIED.value,
    PipelineStage.CONTACTED.value,
    PipelineStage.REPLIED.value,
}


class TriggerGateRejectedError(ValueError):
    """Raised when demo build trigger is invoked without explicit demo request."""
    pass


class DemoJobManager:
    """
    Manages DemoBuildJob lifecycle:
    - B1: Trigger gate verification (strictly require demo_requested=True or DEMO_REQUESTED stage)
    - B2: Persistent deduplication (return existing job if matching request_id or active business job exists)
    - B14: State transition progression across canonical demo lifecycle states
    """

    @staticmethod
    def slugify(text: str) -> str:
        import re
        s = text.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_-]+", "-", s)
        return s.strip("-")

    @classmethod
    async def create_or_get_job(
        cls,
        session: AsyncSession,
        business_id: int,
        request_id: Optional[str] = None,
        force: bool = False
    ) -> Tuple[DemoBuildJob, bool]:
        """
        Enforces B1 trigger gate and B2 deduplication.
        Returns (DemoBuildJob, is_created: bool).
        """
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business #{business_id} not found.")

        # B1: TRIGGER GATE VALIDATION
        # Must have demo_requested=True or be in DEMO_REQUESTED stage
        has_demo_requested_flag = getattr(biz, "demo_requested", False) is True
        stage = str(biz.pipeline_stage or "")

        if not force:
            if stage in REJECTED_TRIGGER_STAGES and not has_demo_requested_flag:
                raise TriggerGateRejectedError(
                    f"Trigger gate rejected for biz #{business_id}: "
                    f"stage='{stage}' requires explicit requirements or confirmation first. "
                    f"demo_requested flag is False."
                )

            if not has_demo_requested_flag and stage not in ALLOWED_DEMO_STAGES:
                raise TriggerGateRejectedError(
                    f"Trigger gate rejected for biz #{business_id}: "
                    f"stage='{stage}' is not an authorized demo trigger stage and demo_requested is False."
                )

        # B2: DEDUPLICATION CHECK
        # 1. By request_id if provided
        if request_id:
            q_req = select(DemoBuildJob).where(DemoBuildJob.request_id == request_id)
            existing_req = (await session.execute(q_req)).scalars().first()
            if existing_req:
                logger.info(f"[DemoJobManager] Deduplication hit: returning existing job {existing_req.demo_id} for request_id={request_id}")
                return existing_req, False

        # 2. By business_id and active or completed status
        q_biz = (
            select(DemoBuildJob)
            .where(
                DemoBuildJob.business_id == business_id,
                DemoBuildJob.status.notin_([
                    ProjectStatus.DEMO_BUILD_FAILED.value,
                    ProjectStatus.DEMO_QA_FAILED.value,
                    "FAILED"
                ])
            )
            .order_by(DemoBuildJob.created_at.desc())
        )
        existing_job = (await session.execute(q_biz)).scalars().first()
        if existing_job:
            logger.info(f"[DemoJobManager] Deduplication hit: active job {existing_job.demo_id} already exists for biz #{business_id}")
            return existing_job, False

        # Create new DemoBuildJob
        biz_name = biz.name or biz.domain or f"biz-{business_id}"
        slug = cls.slugify(biz_name) or cls.slugify(biz.domain.split(".")[0] if biz.domain else f"biz-{business_id}")
        generated_req_id = request_id or f"req_{slug}_{uuid.uuid4().hex[:8]}"
        demo_id = f"demo_{slug}_{uuid.uuid4().hex[:6]}"

        job = DemoBuildJob(
            demo_id=demo_id,
            business_id=biz.id,
            request_id=generated_req_id,
            customer_slug=slug,
            status=ProjectStatus.DEMO_REQUESTED.value,
            retry_count=0,
            max_retries=3,
            spec_summary={"title": biz_name, "domain": biz.domain, "niche": biz.niche},
            created_at=datetime.utcnow()
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)

        logger.info(f"[DemoJobManager] Created new DemoBuildJob {job.demo_id} for biz #{biz.id} ({slug})")
        return job, True

    @classmethod
    async def update_job_status(
        cls,
        session: AsyncSession,
        job_id: int,
        new_status: str,
        deployment_url: Optional[str] = None,
        error_details: Optional[str] = None,
        spec_summary_update: Optional[Dict[str, Any]] = None
    ) -> DemoBuildJob:
        """
        Updates the status of a DemoBuildJob through canonical lifecycle progression.
        """
        job = await session.get(DemoBuildJob, job_id)
        if not job:
            raise ValueError(f"DemoBuildJob #{job_id} not found.")

        old_status = job.status
        job.status = new_status
        job.updated_at = datetime.utcnow()

        if deployment_url:
            job.deployment_url = deployment_url
        if error_details:
            job.error_details = error_details
        if spec_summary_update:
            current = dict(job.spec_summary or {})
            current.update(spec_summary_update)
            job.spec_summary = current

        if new_status in (ProjectStatus.DEMO_READY.value, ProjectStatus.DEMO_DELIVERED.value):
            job.completed_at = datetime.utcnow()
        elif "FAILED" in new_status:
            job.retry_count += 1

        await session.commit()
        await session.refresh(job)
        logger.info(f"[DemoJobManager] Job {job.demo_id} transitioned: {old_status} -> {new_status}")
        return job
