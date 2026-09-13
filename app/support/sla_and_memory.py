"""
SLA Engine & Incident Memory Layer — Mega Prompt 7.
Manages SLA targets, response/resolution compliance tracking, and maintains
searchable post-incident memory to inform future root-cause and remediation planning.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from app.database.models import IncidentMemory, SupportTicket

logger = logging.getLogger("agency.support.sla_and_memory")


class SLATarget(BaseModel):
    severity: str
    response_target_minutes: int
    resolution_target_hours: int


class SLAComplianceReport(BaseModel):
    ticket_number: str
    severity: str
    response_time_minutes: Optional[float]
    resolution_time_hours: Optional[float]
    response_breached: bool
    resolution_breached: bool
    overall_sla_status: str  # COMPLIANT, AT_RISK, BREACHED


class SLAEngine:
    """Calculates and monitors SLA targets across severity tiers."""

    TARGETS: Dict[str, SLATarget] = {
        "SEV-1": SLATarget(severity="SEV-1", response_target_minutes=15, resolution_target_hours=2),
        "SEV-2": SLATarget(severity="SEV-2", response_target_minutes=60, resolution_target_hours=8),
        "SEV-3": SLATarget(severity="SEV-3", response_target_minutes=240, resolution_target_hours=24),
        "SEV-4": SLATarget(severity="SEV-4", response_target_minutes=1440, resolution_target_hours=72)
    }

    @classmethod
    def evaluate_sla(cls, ticket: SupportTicket) -> SLAComplianceReport:
        target = cls.TARGETS.get(ticket.severity, cls.TARGETS["SEV-3"])
        now = datetime.utcnow()

        # Response SLA
        resp_time_min = None
        resp_breached = False
        if ticket.response_at and ticket.created_at:
            delta = ticket.response_at - ticket.created_at
            resp_time_min = delta.total_seconds() / 60.0
            resp_breached = resp_time_min > target.response_target_minutes
        elif ticket.created_at and not ticket.response_at:
            elapsed = (now - ticket.created_at).total_seconds() / 60.0
            resp_breached = elapsed > target.response_target_minutes

        # Resolution SLA
        res_time_hours = None
        res_breached = False
        if ticket.resolved_at and ticket.created_at:
            delta = ticket.resolved_at - ticket.created_at
            res_time_hours = delta.total_seconds() / 3600.0
            res_breached = res_time_hours > target.resolution_target_hours
        elif ticket.created_at and not ticket.resolved_at:
            elapsed = (now - ticket.created_at).total_seconds() / 3600.0
            res_breached = elapsed > target.resolution_target_hours

        status = "BREACHED" if (resp_breached or res_breached) else "COMPLIANT"

        return SLAComplianceReport(
            ticket_number=ticket.ticket_number,
            severity=ticket.severity,
            response_time_minutes=round(resp_time_min, 1) if resp_time_min is not None else None,
            resolution_time_hours=round(res_time_hours, 2) if res_time_hours is not None else None,
            response_breached=resp_breached,
            resolution_breached=res_breached,
            overall_sla_status=status
        )


class IncidentMemoryService:
    """Manages reusable operational memory from previous incident resolutions."""

    async def search_memory(
        self,
        session: AsyncSession,
        category: str,
        error_pattern: str
    ) -> List[Dict[str, Any]]:
        """Finds prior matching resolutions based on error pattern or category."""
        stmt = (
            select(IncidentMemory)
            .where(IncidentMemory.category == category)
            .order_by(desc(IncidentMemory.occurrence_count))
            .limit(5)
        )
        memories = (await session.execute(stmt)).scalars().all()
        results = []
        for m in memories:
            if error_pattern.lower() in m.error_pattern.lower() or m.category == category:
                results.append({
                    "id": m.id,
                    "signature": m.signature,
                    "component": m.component,
                    "root_cause": m.root_cause,
                    "remediation_pattern": m.remediation_pattern,
                    "prevention_guidance": m.prevention_guidance,
                    "occurrence_count": m.occurrence_count
                })
        return results

    async def record_incident_memory(
        self,
        session: AsyncSession,
        category: str,
        component: str,
        error_pattern: str,
        root_cause: str,
        remediation_pattern: str,
        verified_fix: Dict[str, Any],
        prevention_guidance: str = ""
    ) -> IncidentMemory:
        """Stores or updates operational memory following verified resolution."""
        sig = f"{category.upper()}:{component.lower()}"
        stmt = select(IncidentMemory).where(IncidentMemory.signature == sig)
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.occurrence_count += 1
            existing.last_applied_at = datetime.utcnow()
            existing.verified_fix = verified_fix
            await session.commit()
            return existing

        new_mem = IncidentMemory(
            signature=sig,
            category=category,
            component=component,
            error_pattern=error_pattern[:200],
            root_cause=root_cause,
            remediation_pattern=remediation_pattern,
            verified_fix=verified_fix,
            prevention_guidance=prevention_guidance,
            last_applied_at=datetime.utcnow()
        )
        session.add(new_mem)
        await session.commit()
        return new_mem


sla_engine = SLAEngine()
incident_memory_service = IncidentMemoryService()
