"""
Build Pipeline Orchestrator — Phase 6 & Phase 18.
Coordinates the end-to-end execution:
SPEC -> DESIGN -> AI_PROTOTYPING -> BUILD -> QA -> REPAIR -> DEPLOY -> SALES_ALIGNMENT.
Enforces per-project concurrency isolation (Customer A never blocks Customer B).
"""

import asyncio
import uuid
import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    Business, CustomerProject, ProjectSpecification, DesignSpecification,
    AIFeatureSpecification, ProjectBuild, BuildQA, ProjectDeployment,
    ProjectEvent, PipelineStage, ProjectStatus, PipelineEvent, Offer, Proposal,
    DemoBuildJob
)
from app.builder.spec_engine import spec_engine
from app.builder.providers.stitch_provider import StitchDesignProvider
from app.builder.providers.ai_studio_provider import GoogleAIStudioProvider
from app.builder.providers.antigravity_coding_provider import AntigravityCodingProvider
from app.builder.qa_engine import BuildQAEngine
from app.builder.repair_engine import BuildRepairEngine
from app.builder.deployment import deployment_engine
from app.intelligence.tool_selector import demo_tool_selector
from app.intelligence.operator_learning import operator_learning_engine, CommercialGateViolation
from app.core.logging import logger

# Per-project independent concurrency locks
_PROJECT_LOCKS: Dict[str, asyncio.Lock] = {}
_REGISTRY_LOCK = asyncio.Lock()


async def get_project_lock(project_id: str) -> asyncio.Lock:
    """Returns an isolated asyncio.Lock for a specific customer project."""
    async with _REGISTRY_LOCK:
        if project_id not in _PROJECT_LOCKS:
            _PROJECT_LOCKS[project_id] = asyncio.Lock()
        return _PROJECT_LOCKS[project_id]


class BuildPipelineOrchestrator:
    """
    End-to-end autonomous coordinator for demo project builds.
    """

    def __init__(self):
        self.design_provider = StitchDesignProvider()
        self.ai_provider = GoogleAIStudioProvider()
        self.coding_provider = AntigravityCodingProvider()
        self.repair_engine = BuildRepairEngine(self.coding_provider)

    @classmethod
    def slugify(cls, text: str) -> str:
        s = (text or "").lower()
        s = re.sub(r'[^a-z0-9]+', '-', s)
        return s.strip('-') or "customer"

    async def get_or_create_project(
        self,
        session: AsyncSession,
        business_id: int,
        reply_text: Optional[str] = None
    ) -> CustomerProject:
        """Finds active customer project or initializes a new one."""
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business ID {business_id} not found.")

        # Check existing active project
        q = select(CustomerProject).where(
            CustomerProject.business_id == business_id
        ).order_by(CustomerProject.created_at.desc())
        existing = (await session.execute(q)).scalars().first()

        if existing and existing.status not in ("FAILED", "CANCELLED"):
            return existing

        biz_name = biz.name or biz.domain
        slug = self.slugify(biz_name) or self.slugify(biz.domain.split(".")[0])
        proj_id = f"proj_{slug}_{uuid.uuid4().hex[:6]}"

        project = CustomerProject(
            project_id=proj_id,
            business_id=biz.id,
            customer_slug=slug,
            title=biz_name,
            industry=biz.niche or "Commercial Services",
            status=ProjectStatus.DEMO_REQUESTED.value,
            current_stage="DEMO_REQUESTED",
            created_at=datetime.utcnow()
        )
        session.add(project)
        await session.flush()

        # Record project event
        event = ProjectEvent(
            project_id=project.id,
            event_type="PROJECT_INITIALIZED",
            stage="DEMO_REQUESTED",
            details={"reply_text": reply_text, "industry": project.industry}
        )
        session.add(event)

        # Update business pipeline stage to DEMO_REQUESTED
        old_stage = biz.pipeline_stage
        biz.pipeline_stage = PipelineStage.DEMO_REQUESTED.value
        pipe_event = PipelineEvent(
            business_id=biz.id,
            from_stage=old_stage,
            to_stage=PipelineStage.DEMO_REQUESTED.value,
            deal_value=0.0,
            note=f"Demo build pipeline requested for {biz_name}."
        )
        session.add(pipe_event)

        await session.commit()
        await session.refresh(project)

        logger.info(f"[BuildPipelineOrchestrator] Initialized project {project.project_id} for {biz.domain}")
        return project

    async def run_pipeline(
        self,
        session: AsyncSession,
        project_id: str,
        reply_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes full autonomous pipeline stages sequentially under per-project lock.
        """
        lock = await get_project_lock(project_id)
        async with lock:
            q = select(CustomerProject).where(CustomerProject.project_id == project_id)
            project = (await session.execute(q)).scalars().first()
            if not project:
                raise ValueError(f"Project {project_id} not found.")

            biz = await session.get(Business, project.business_id)

            # Query existing DemoBuildJob if present
            q_job = select(DemoBuildJob).where(
                DemoBuildJob.business_id == project.business_id
            ).order_by(DemoBuildJob.created_at.desc())
            demo_job = (await session.execute(q_job)).scalars().first()

            # Update status to DEMO_BUILDING
            if biz:
                biz.pipeline_stage = PipelineStage.DEMO_BUILDING.value
            project.status = ProjectStatus.DEMO_BUILDING.value
            project.current_stage = "DEMO_BUILDING"
            if demo_job:
                demo_job.status = ProjectStatus.DEMO_BUILDING.value
            await session.commit()

            try:
                # -------------------------------------------------------------
                # STAGE 1: SPECIFICATION
                # -------------------------------------------------------------
                project.current_stage = "SPEC"
                session.add(ProjectEvent(project_id=project.id, event_type="SPEC_GENERATION_STARTED", stage="SPEC"))
                await session.commit()

                spec = await spec_engine.build_canonical_spec(
                    session=session,
                    customer_project=project,
                    reply_text=reply_text
                )

                project.status = ProjectStatus.DEMO_SPEC_CREATED.value
                project.current_stage = "DEMO_SPEC_CREATED"

                # Synthesize intelligent tool allocation plan
                from app.builder.spec_engine import CanonicalSpecEngine
                canonical_spec = CanonicalSpecEngine.to_canonical_spec(spec, project, biz)
                demo_plan = demo_tool_selector.generate_demo_plan(canonical_spec)

                if demo_job:
                    demo_job.status = ProjectStatus.DEMO_SPEC_CREATED.value
                    demo_job.spec_summary = {
                        "screens": [getattr(s, "name", str(s)) for s in (spec.required_screens or [])],
                        "facts_count": len(spec.facts or []),
                        "checksum": spec.checksum,
                        "demo_plan": demo_plan.to_dict()
                    }
                session.add(ProjectEvent(
                    project_id=project.id,
                    event_type="DEMO_PLAN_TOOL_SELECTION",
                    stage="DEMO_SPEC_CREATED",
                    details=demo_plan.to_dict()
                ))
                await session.commit()

                # -------------------------------------------------------------
                # STAGE 2: DESIGN (Stitch Provider)
                # -------------------------------------------------------------
                project.current_stage = "DESIGN"
                project.status = "DESIGNING"
                session.add(ProjectEvent(project_id=project.id, event_type="DESIGN_GENERATION_STARTED", stage="DESIGN"))
                await session.commit()

                design_res = await self.design_provider.generate_design(spec=spec, customer_project=project)
                design_model = DesignSpecification(
                    project_id=project.id,
                    version=spec.version,
                    provider=design_res.provider,
                    screens=[s.model_dump() for s in design_res.screens],
                    color_system=design_res.color_system,
                    typography=design_res.typography,
                    responsive_variants=design_res.responsive_variants,
                    status=design_res.status
                )
                session.add(design_model)
                await session.commit()

                # -------------------------------------------------------------
                # STAGE 3: AI PROTOTYPING (Google AI Studio Provider)
                # -------------------------------------------------------------
                project.current_stage = "AI_PROTOTYPING"
                project.status = "AI_PROTOTYPING"
                session.add(ProjectEvent(project_id=project.id, event_type="AI_PROTOTYPE_STARTED", stage="AI_PROTOTYPING"))
                await session.commit()

                ai_res = await self.ai_provider.generate_prototype(spec=spec, customer_project=project)
                ai_model = AIFeatureSpecification(
                    project_id=project.id,
                    version=spec.version,
                    provider=ai_res.provider,
                    prototype_type=ai_res.prototype_type,
                    prompt_templates=ai_res.prompt_templates,
                    system_instructions=ai_res.system_instructions,
                    safety_settings=ai_res.safety_settings,
                    model_name=ai_res.model_name,
                    fallback_behavior=ai_res.fallback_behavior,
                    status=ai_res.status
                )
                session.add(ai_model)
                await session.commit()

                # -------------------------------------------------------------
                # STAGE 4: BUILD (Antigravity Multi-Language Code Generation)
                # -------------------------------------------------------------
                project.current_stage = "BUILD"
                project.status = "BUILDING"
                session.add(ProjectEvent(project_id=project.id, event_type="BUILD_STARTED", stage="BUILD"))
                await session.commit()

                build_res = await self.coding_provider.build_project(
                    spec=spec,
                    design=design_res,
                    ai_proto=ai_res,
                    customer_project=project
                )

                from sqlalchemy import func
                q_build_count = select(func.count(ProjectBuild.id)).where(ProjectBuild.project_id == project.id)
                build_cnt = (await session.execute(q_build_count)).scalar() or 0
                next_build_num = build_cnt + 1

                build_model = ProjectBuild(
                    project_id=project.id,
                    build_number=next_build_num,
                    status=build_res.status,
                    artifacts_manifest=build_res.artifacts_manifest,
                    routes_manifest=build_res.routes_manifest,
                    dependencies_manifest=build_res.dependencies_manifest,
                    build_duration_ms=build_res.build_duration_ms,
                    created_at=datetime.utcnow(),
                    completed_at=datetime.utcnow()
                )
                session.add(build_model)
                await session.commit()
                await session.refresh(build_model)

                # -------------------------------------------------------------
                # STAGE 5: DEPLOY TO SANDBOX (Write artifacts for QA inspection)
                # -------------------------------------------------------------
                project.current_stage = "DEMO_DEPLOYING"
                project.status = ProjectStatus.DEMO_DEPLOYING.value
                if biz:
                    biz.pipeline_stage = PipelineStage.DEMO_DEPLOYING.value
                if demo_job:
                    demo_job.status = ProjectStatus.DEMO_DEPLOYING.value
                session.add(ProjectEvent(project_id=project.id, event_type="DEPLOYMENT_STARTED", stage="DEMO_DEPLOYING"))
                await session.commit()

                deployment = await deployment_engine.deploy_demo(
                    session=session,
                    customer_project=project,
                    build=build_model,
                    build_result=build_res
                )

                # -------------------------------------------------------------
                # STAGE 6: 20-GATE QA ENGINE EVALUATION
                # -------------------------------------------------------------
                project.current_stage = "DEMO_QA"
                project.status = ProjectStatus.DEMO_QA.value
                if biz:
                    biz.pipeline_stage = PipelineStage.DEMO_QA.value
                if demo_job:
                    demo_job.status = ProjectStatus.DEMO_QA.value
                session.add(ProjectEvent(project_id=project.id, event_type="QA_STARTED", stage="DEMO_QA"))
                await session.commit()

                qa_res = BuildQAEngine.evaluate_build(
                    build=build_model,
                    spec=spec,
                    customer_project=project,
                    artifacts_dir=deployment.metadata_json.get("sandbox_path", "")
                )

                qa_record = BuildQA(
                    build_id=build_model.id,
                    overall_status=qa_res.overall_status,
                    score=qa_res.score,
                    gate_results=qa_res.gate_results,
                    critical_violations=qa_res.critical_violations,
                    non_critical_warnings=qa_res.non_critical_warnings
                )
                session.add(qa_record)
                await session.commit()

                # -------------------------------------------------------------
                # STAGE 7: BOUNDED REPAIR LOOP (If QA fails)
                # -------------------------------------------------------------
                if qa_res.overall_status == "FAIL":
                    project.current_stage = "REPAIR"
                    project.status = ProjectStatus.REPAIRING.value
                    session.add(ProjectEvent(project_id=project.id, event_type="REPAIR_LOOP_STARTED", stage="REPAIR"))
                    await session.commit()

                    qa_res = await self.repair_engine.execute_repair_loop(
                        session=session,
                        customer_project=project,
                        spec=spec,
                        build=build_model,
                        initial_qa=qa_res,
                        artifacts_dir=deployment.metadata_json.get("sandbox_path", "")
                    )

                # -------------------------------------------------------------
                # STAGE 8: SALES STATE MACHINE ALIGNMENT & PROPOSAL
                # -------------------------------------------------------------
                if qa_res.overall_status in ("PASS", "WARN"):
                    project.status = ProjectStatus.DEMO_READY.value
                    project.current_stage = "DEMO_READY"
                    if demo_job:
                        demo_job.status = ProjectStatus.DEMO_READY.value
                        demo_job.deployment_url = deployment.deployment_url
                        demo_job.completed_at = datetime.utcnow()
                    if biz:
                        old_st = biz.pipeline_stage
                        biz.pipeline_stage = PipelineStage.DEMO_READY.value
                        session.add(PipelineEvent(
                            business_id=biz.id,
                            from_stage=old_st,
                            to_stage=PipelineStage.DEMO_READY.value,
                            deal_value=650.0,
                            note=f"Demo ready at {deployment.deployment_url}. QA score: {qa_res.score}%"
                        ))

                        # Create or ensure commercial proposal
                        q_prop = select(Proposal).where(Proposal.business_id == biz.id).order_by(Proposal.created_at.desc())
                        prop = (await session.execute(q_prop)).scalars().first()
                        if not prop:
                            prop = Proposal(
                                business_id=biz.id,
                                title="Turnkey Commercial Implementation Package",
                                service_type=project.industry or "Website Turnaround",
                                total_value=650.0,
                                advance_required=260.0,
                                remaining_balance=390.0,
                                status="APPROVED"
                            )
                            session.add(prop)

                    session.add(ProjectEvent(
                        project_id=project.id,
                        event_type="DEMO_DELIVERY_COMPLETE",
                        stage="DEMO_READY",
                        details={"url": deployment.deployment_url, "qa_score": qa_res.score}
                    ))
                    await session.commit()

                    logger.info(
                        f"[BuildPipelineOrchestrator] Completed demo pipeline for {project_id} -> {deployment.deployment_url}"
                    )
                    return {
                        "success": True,
                        "project_id": project.project_id,
                        "customer_slug": project.customer_slug,
                        "demo_id": deployment.demo_id,
                        "demo_url": deployment.deployment_url,
                        "status": ProjectStatus.DEMO_READY.value,
                        "qa_score": qa_res.score,
                        "gate_results": qa_res.gate_results
                    }
                else:
                    project.status = ProjectStatus.DEMO_BUILD_FAILED.value
                    project.current_stage = "DEMO_BUILD_FAILED"
                    if demo_job:
                        demo_job.status = ProjectStatus.DEMO_BUILD_FAILED.value
                        demo_job.error_details = str(qa_res.critical_violations)
                        demo_job.retry_count += 1
                    if biz:
                        biz.pipeline_stage = PipelineStage.DEMO_BUILD_FAILED.value
                    session.add(ProjectEvent(
                        project_id=project.id,
                        event_type="DEMO_BUILD_FAILED",
                        stage="DEMO_BUILD_FAILED",
                        details={"critical_violations": qa_res.critical_violations, "alert": "CEO_REQUIRED"}
                    ))
                    await session.commit()
                    logger.error(
                        f"[BuildPipelineOrchestrator] Demo build failed for {project_id} with violations: "
                        f"{qa_res.critical_violations} - CEO_REQUIRED"
                    )
                    return {
                        "success": False,
                        "project_id": project.project_id,
                        "customer_slug": project.customer_slug,
                        "status": ProjectStatus.DEMO_BUILD_FAILED.value,
                        "qa_score": qa_res.score,
                        "critical_violations": qa_res.critical_violations,
                        "requires_action": "CEO_REQUIRED"
                    }

            except Exception as exc:
                logger.exception(
                    f"[BuildPipelineOrchestrator] Unhandled exception during demo build for {project_id}: {exc}"
                )
                try:
                    await session.rollback()
                    project.status = ProjectStatus.DEMO_BUILD_FAILED.value
                    project.current_stage = "DEMO_BUILD_FAILED"
                    if demo_job:
                        demo_job.status = ProjectStatus.DEMO_BUILD_FAILED.value
                        demo_job.error_details = str(exc)
                        demo_job.retry_count += 1
                    if biz:
                        biz.pipeline_stage = PipelineStage.DEMO_BUILD_FAILED.value
                    session.add(ProjectEvent(
                        project_id=project.id,
                        event_type="DEMO_BUILD_FAILED",
                        stage="DEMO_BUILD_FAILED",
                        details={"error": str(exc), "alert": "CEO_REQUIRED"}
                    ))
                    await session.commit()
                except Exception as inner_exc:
                    logger.error(
                        f"[BuildPipelineOrchestrator] Failed to persist demo failure state: {inner_exc}"
                    )
                    await session.rollback()
                return {
                    "success": False,
                    "project_id": project.project_id,
                    "customer_slug": project.customer_slug,
                    "status": ProjectStatus.DEMO_BUILD_FAILED.value,
                    "error": str(exc),
                    "requires_action": "CEO_REQUIRED"
                }

    async def trigger_demo_pipeline(
        self,
        session: AsyncSession,
        business_id: int,
        reply_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convenience entrypoint: gets or creates project, then runs pipeline."""
        proj = await self.get_or_create_project(session, business_id, reply_text=reply_text)
        return await self.run_pipeline(session, proj.project_id, reply_text=reply_text)

    @classmethod
    async def authorize_production_build(
        cls,
        session: AsyncSession,
        business_id: int,
        project_id: int
    ) -> bool:
        """
        Enforces commercial gate:
        DEMO READY -> CUSTOMER APPROVES -> PROPOSAL -> ADVANCE PAYMENT -> PRODUCTION BUILD
        Raises CommercialGateViolation if advance or full payment is not verified.
        """
        return await operator_learning_engine.enforce_commercial_gate(session, business_id)


pipeline_orchestrator = BuildPipelineOrchestrator()
