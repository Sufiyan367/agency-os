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
    PipelineStage,
    CustomerProject,
    ProductionProjectStatus
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


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal demo state transition is attempted."""
    pass


class PaymentAuthorizationRequiredError(PermissionError):
    """Raised when production build is attempted without advance payment confirmation."""
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
        spec_summary_update: Optional[Dict[str, Any]] = None,
        validate_transition: bool = True
    ) -> DemoBuildJob:
        """
        Updates the status of a DemoBuildJob through canonical lifecycle progression.
        """
        job = await session.get(DemoBuildJob, job_id)
        if not job:
            raise ValueError(f"DemoBuildJob #{job_id} not found.")

        old_status = job.status
        if validate_transition and old_status in DemoStateMachine.VALID_TRANSITIONS:
            DemoStateMachine.validate_transition(old_status, new_status)

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

        if new_status in (ProjectStatus.DEMO_READY.value, ProjectStatus.DEMO_DELIVERED.value, ProjectStatus.DEMO_SANDBOX_READY.value):
            job.completed_at = datetime.utcnow()
        elif "FAILED" in new_status:
            job.retry_count += 1

        await session.commit()
        await session.refresh(job)
        logger.info(f"[DemoJobManager] Job {job.demo_id} transitioned: {old_status} -> {new_status}")
        return job


class DemoStateMachine:
    """
    B16: Formal Demo Lifecycle State Machine.
    Enforces valid state progressions and rejects invalid transitions.
    """
    VALID_TRANSITIONS = {
        ProjectStatus.DEMO_REQUESTED.value: {
            ProjectStatus.DEMO_SPEC_CREATED.value,
            ProjectStatus.DEMO_BUILDING.value,
            ProjectStatus.DEMO_BUILD_FAILED.value,
        },
        ProjectStatus.DEMO_SPEC_CREATED.value: {
            ProjectStatus.DEMO_BUILDING.value,
            ProjectStatus.DEMO_BUILD_FAILED.value,
        },
        ProjectStatus.DEMO_BUILDING.value: {
            ProjectStatus.DEMO_QA.value,
            ProjectStatus.DEMO_BUILD_FAILED.value,
        },
        ProjectStatus.DEMO_QA.value: {
            ProjectStatus.DEMO_DEPLOYING.value,
            ProjectStatus.DEMO_QA_FAILED.value,
            ProjectStatus.DEMO_READY.value,
            ProjectStatus.DEMO_SANDBOX_READY.value,
        },
        ProjectStatus.DEMO_QA_FAILED.value: {
            ProjectStatus.DEMO_BUILDING.value,  # Auto-fix loop attempt
            ProjectStatus.DEMO_BUILD_FAILED.value,
        },
        ProjectStatus.DEMO_DEPLOYING.value: {
            ProjectStatus.DEMO_READY.value,
            ProjectStatus.DEMO_SANDBOX_READY.value,
            ProjectStatus.DEMO_DEPLOYMENT_BLOCKED.value,
            ProjectStatus.DEMO_BUILD_FAILED.value,
        },
        ProjectStatus.DEMO_DEPLOYMENT_BLOCKED.value: {
            ProjectStatus.DEMO_SANDBOX_READY.value,
            ProjectStatus.DEMO_DEPLOYING.value,
        },
        ProjectStatus.DEMO_SANDBOX_READY.value: {
            ProjectStatus.DEMO_READY.value,
            ProjectStatus.DEMO_DELIVERED.value,
        },
        ProjectStatus.DEMO_READY.value: {
            ProjectStatus.DEMO_DELIVERED.value,
        },
        ProjectStatus.DEMO_DELIVERED.value: set(),
        ProjectStatus.DEMO_BUILD_FAILED.value: {
            ProjectStatus.DEMO_REQUESTED.value,
            ProjectStatus.DEMO_BUILDING.value,
        },
    }

    @classmethod
    def validate_transition(cls, current_status: str, new_status: str) -> bool:
        if current_status == new_status:
            return True
        allowed = cls.VALID_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise InvalidStateTransitionError(
                f"Invalid demo state transition: cannot move from '{current_status}' to '{new_status}'. "
                f"Allowed transitions: {list(allowed)}"
            )
        return True


class ProductionPaymentGate:
    """
    B14: Production Implementation Payment Gate.
    Strictly enforces:
    DEMO_READY does NOT authorize production implementation.
    Production build CANNOT begin until advance payment is confirmed.
    """
    @classmethod
    def can_authorize_production_build(cls, project: CustomerProject) -> bool:
        status = str(getattr(project, "payment_status", "PENDING")).upper()
        return status in ("CONFIRMED", "PAID", "VERIFIED_PAYMENT", "ADVANCE_PAYMENT_CONFIRMED")

    @classmethod
    async def authorize_production_build(
        cls,
        session: AsyncSession,
        project_id: str,
        advance_payment_confirmed: bool = False
    ) -> CustomerProject:
        stmt = select(CustomerProject).where(CustomerProject.project_id == project_id)
        project = (await session.execute(stmt)).scalars().first()
        if not project:
            raise ValueError(f"CustomerProject '{project_id}' not found.")

        if not advance_payment_confirmed and not cls.can_authorize_production_build(project):
            raise PaymentAuthorizationRequiredError(
                f"Production build authorization rejected for project '{project_id}': "
                f"Advance payment is required before production implementation can begin. "
                f"Current payment status: '{getattr(project, 'payment_status', 'PENDING')}'. "
                f"Demo completion does NOT authorize production implementation."
            )

        project.payment_required = True
        project.payment_status = "CONFIRMED"
        project.production_build_authorized = True
        project.production_status = ProductionProjectStatus.PRODUCTION_BUILD_AUTHORIZED.value
        project.status = ProductionProjectStatus.PRODUCTION_BUILD_AUTHORIZED.value
        await session.commit()
        await session.refresh(project)
        logger.info(f"[ProductionPaymentGate] Production build authorized for project '{project_id}' after advance payment confirmation.")
        return project


def prepare_demo_delivery_package(
    job: DemoBuildJob,
    project: Optional[CustomerProject] = None
) -> Dict[str, Any]:
    """
    B13: Clean customer-facing delivery package.
    Sanitized: Zero internal tooling references (no mention of Stitch, Antigravity, Google AI Studio, Firebase).
    """
    biz_name = (job.spec_summary or {}).get("title") or job.customer_slug
    deployment_url = job.deployment_url or f"/demo/{job.customer_slug}"

    features = []
    if project and getattr(project, "builds", None):
        latest = project.builds[-1]
        manifest = latest.artifacts_manifest or {}
        if "n8n_automation.json" in manifest:
            features.append("Integrated Inbound Lead Automation & CRM Routing")
        if "app.js" in manifest:
            features.append("Interactive Client Experience Portal")
    if not features:
        features = [
            "Tailored Interactive Brand Prototype",
            "High-Conversion Lead Qualification Workflow",
            "Real-Time Response Integration"
        ]

    is_sandbox = "demo/" in deployment_url or "localhost" in deployment_url or "automatedagencyos.tech/demo" in deployment_url
    limitations = (
        "Interactive demonstration sandbox. Live production deployment requires custom domain DNS cutover and dedicated client credentials."
        if is_sandbox else
        "Live staging prototype. Production cutover ready upon contract execution."
    )

    customer_message = (
        f"Hi there! Your bespoke Agency OS interactive demo for {biz_name} is ready for review.\n\n"
        f"Live Demo URL: {deployment_url}\n\n"
        f"Key Implemented Features:\n"
        + "".join(f"- {f}\n" for f in features)
        + f"\nNext Steps: If this matches your requirements, our team will deliver the official commercial proposal and production rollout plan."
    )

    return {
        "customer_slug": job.customer_slug,
        "demo_url": deployment_url,
        "implemented_functionality": features,
        "qa_result": {
            "status": "PASSED" if job.status in (ProjectStatus.DEMO_READY.value, ProjectStatus.DEMO_SANDBOX_READY.value) else job.status,
            "certified": job.status in (ProjectStatus.DEMO_READY.value, ProjectStatus.DEMO_SANDBOX_READY.value, ProjectStatus.DEMO_DELIVERED.value)
        },
        "limitations": limitations,
        "customer_message": customer_message
    }
