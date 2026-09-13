"""
Bounded Autonomous Repair Loop Engine — Phase 11.
Provides targeted, automated self-healing when QA gates fail.
Strictly bounded by MAX_REPAIR_ATTEMPTS = 3 to prevent infinite loops.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    CustomerProject, ProjectBuild, BuildQA, RepairAttempt, ProjectSpecification
)
from app.builder.models import PipelineQAResult, RepairResult
from app.builder.providers.antigravity_coding_provider import AntigravityCodingProvider
from app.builder.qa_engine import BuildQAEngine
from app.core.logging import logger

MAX_REPAIR_ATTEMPTS = 3


class BuildRepairEngine:
    """
    Executes bounded repair feedback cycles on failing builds.
    """

    def __init__(self, coding_provider: Optional[AntigravityCodingProvider] = None):
        self.coding_provider = coding_provider or AntigravityCodingProvider()

    def classify_failure(self, failing_gates: List[str]) -> str:
        """Classifies QA gate failure into actionable engineering categories."""
        if any("PLACEHOLDER" in g for g in failing_gates):
            return "PLACEHOLDER_LEAK"
        if any("SYNTAX" in g for g in failing_gates):
            return "SYNTAX_ERROR"
        if any("ROUTE" in g for g in failing_gates):
            return "MISSING_ROUTE"
        if any("IDENTITY" in g for g in failing_gates) or any("LEAKAGE" in g for g in failing_gates):
            return "IDENTITY_ISOLATION_VIOLATION"
        if any("SECURITY" in g or "SECRET" in g for g in failing_gates):
            return "SECURITY_POLICY_VIOLATION"
        return "GENERAL_QA_DEFECT"

    async def execute_repair_loop(
        self,
        session: AsyncSession,
        customer_project: CustomerProject,
        spec: ProjectSpecification,
        build: ProjectBuild,
        initial_qa: PipelineQAResult,
        artifacts_dir: str
    ) -> PipelineQAResult:
        """
        Runs up to MAX_REPAIR_ATTEMPTS self-healing passes against the failing build.
        """
        current_qa = initial_qa

        for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
            if current_qa.overall_status in ("PASS", "WARN"):
                logger.info(
                    f"[BuildRepairEngine] Build {build.id} resolved successfully "
                    f"at attempt {attempt - 1}."
                )
                return current_qa

            failing_gate = current_qa.critical_violations[0] if current_qa.critical_violations else "UNKNOWN"
            classification = self.classify_failure(current_qa.critical_violations)

            logger.warning(
                f"[BuildRepairEngine] Executing repair pass {attempt}/{MAX_REPAIR_ATTEMPTS} "
                f"for project {customer_project.project_id} (failing gate: {failing_gate}, classification: {classification})"
            )

            # Invoke targeted repair logic in coding provider
            repair_res = await self.coding_provider.repair_build(
                spec=spec,
                build=build,
                failing_gate=failing_gate,
                failure_classification=classification,
                critical_violations=current_qa.critical_violations,
                attempt_number=attempt
            )

            # Persist repair attempt in database
            repair_record = RepairAttempt(
                build_id=build.id,
                attempt_number=attempt,
                failing_gate=failing_gate,
                failure_classification=classification,
                diff_applied=repair_res.diff_applied,
                resolved=repair_res.resolved
            )
            session.add(repair_record)
            customer_project.status = "REPAIRING"
            await session.commit()

            # Re-evaluate QA after repair patch
            current_qa = BuildQAEngine.evaluate_build(
                build=build,
                spec=spec,
                customer_project=customer_project,
                artifacts_dir=artifacts_dir
            )

            # Record updated QA run
            re_qa_record = BuildQA(
                build_id=build.id,
                overall_status=current_qa.overall_status,
                score=current_qa.score,
                gate_results=current_qa.gate_results,
                critical_violations=current_qa.critical_violations,
                non_critical_warnings=current_qa.non_critical_warnings
            )
            session.add(re_qa_record)
            await session.commit()

        # If loop exhausts all 3 attempts and still fails:
        if current_qa.overall_status == "FAIL":
            logger.error(
                f"[BuildRepairEngine] Maximum repair attempts ({MAX_REPAIR_ATTEMPTS}) reached "
                f"for project {customer_project.project_id}. Flagging as BLOCKED for human operator review."
            )
            customer_project.status = "BLOCKED"
            build.status = "BUILD_FAILED"
            await session.commit()

        return current_qa
