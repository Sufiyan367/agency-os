"""
Blast Radius Analysis Engine — Mega Prompt 8.
Determines downstream architectural impacts prior to automated remediation or deployment:
Affected functions, routes, database models, customer services, and test suites.
Classifies risk tiers (LOW, MEDIUM, HIGH, UNKNOWN) with deterministic policy gating.
"""
import uuid
from typing import Dict, Any, List, Set, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import BlastRadiusReport, RiskLevel
from app.code_intelligence.native_analyzer import NativeRepositoryAnalyzer
from app.database.models import BlastRadiusReportRecord

class BlastRadiusEngine:
    """
    Computes precise reverse-dependency blast radius using AST parsing.
    """

    CRITICAL_MODULES = {"database", "auth", "payment", "security", "connection.py", "models.py"}

    @classmethod
    async def analyze_change_impact(
        cls,
        candidate_files: List[str],
        repair_ticket_id: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> BlastRadiusReport:
        """
        Builds a comprehensive blast radius assessment.
        """
        analyzer = NativeRepositoryAnalyzer()
        raw_report = await analyzer.get_blast_radius(candidate_files)

        report_id = f"BLAST-{uuid.uuid4().hex[:10].upper()}"

        # Categorize impacted components
        affected_routes = list(getattr(raw_report, "indirectly_affected_routes", []) or getattr(raw_report, "affected_routes", []))
        affected_services = list(getattr(raw_report, "affected_services", []))
        modified_files = list(getattr(raw_report, "modified_files", candidate_files))

        # Detect model changes
        affected_models = [f for f in modified_files if "models.py" in f or "database" in f]

        directly_affected = list(getattr(raw_report, "directly_affected_files", []))
        total_impact = len(directly_affected) + len(modified_files)
        contains_critical = any(any(crit in f for crit in cls.CRITICAL_MODULES) for f in modified_files)

        if contains_critical or total_impact > 10:
            risk = RiskLevel.HIGH
            reasoning = f"Core subsystem modified ({', '.join(modified_files)}) with {total_impact} dependent files. Human approval strictly required."
            regression_score = 0.85
        elif total_impact > 3:
            risk = RiskLevel.MEDIUM
            reasoning = f"Moderate blast radius impacting {total_impact} files. Comprehensive automated test suite required."
            regression_score = 0.50
        else:
            risk = RiskLevel.LOW
            reasoning = "Isolated modification with minimal downstream dependencies. Qualifies for safe bounded automated repair."
            regression_score = 0.15

        report = BlastRadiusReport(
            report_id=report_id,
            repair_ticket_id=repair_ticket_id,
            modified_files=modified_files,
            affected_routes=affected_routes,
            affected_services=affected_services,
            affected_models=affected_models,
            affected_customers_count=0,
            regression_risk=risk,
            regression_score=regression_score,
            rollback_reference=f"git-stash-{report_id}",
            reasoning=reasoning,
            created_at=datetime.utcnow()
        )

        # Persist if DB session provided
        if session:
            record = BlastRadiusReportRecord(
                report_id=report.report_id,
                repair_ticket_id=report.repair_ticket_id,
                modified_files=report.modified_files,
                affected_routes=report.affected_routes,
                affected_services=report.affected_services,
                affected_models=report.affected_models,
                regression_risk=report.regression_risk.value,
                regression_score=report.regression_score,
                rollback_reference=report.rollback_reference,
                reasoning=report.reasoning,
                created_at=report.created_at
            )
            session.add(record)
            await session.commit()

        return report


blast_radius_engine = BlastRadiusEngine()
