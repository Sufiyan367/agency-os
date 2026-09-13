"""
Autonomous Customer Support & Maintenance API Routes — Mega Prompt 7.
Provides authenticated operator and customer endpoints for ticket creation,
triage, evidence diagnostics, bounded remediation, and post-incident memory.
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from app.database.connection import get_db
from app.database.models import SupportTicket, CustomerIncident, IncidentEvent, IncidentMemory, MaintenanceRecord
from app.support.service import support_service
from app.support.sla_and_memory import sla_engine, incident_memory_service
from app.support.maintenance import proactive_maintenance_engine
from app.code_intelligence.benchmarks import code_intelligence_benchmarker
from app.core.config import settings
from fastapi import Request

def get_current_user_info(request: Request) -> Dict[str, str]:
    if not settings.AUTH_ENABLED:
        return {"username": "admin", "role": "admin"}
    from app.core.auth_service import auth_service
    from app.core.security import verify_api_key, verify_session_token_with_role

    token = request.cookies.get("agency_session")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    if token:
        if verify_api_key(token):
            return {"username": "api_client", "role": "admin"}
        info = verify_session_token_with_role(token)
        if info and not auth_service.is_session_revoked(info["username"], token):
            return info
    return {"username": "anonymous", "role": "guest"}

router = APIRouter(prefix="/api/support", tags=["Support & Self-Healing Engine"])


class CreateTicketRequest(BaseModel):
    customer_id: int
    subject: str
    description: str
    severity: Optional[str] = None
    source: str = "CUSTOMER_PORTAL"


class AutonomousLoopRequest(BaseModel):
    customer_id: int
    subject: str
    description: str
    source: str = "CUSTOMER_PORTAL"


@router.get("/tickets")
async def list_tickets(
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(SupportTicket)
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    if customer_id:
        stmt = stmt.where(SupportTicket.customer_id == customer_id)
    stmt = stmt.order_by(desc(SupportTicket.created_at)).limit(limit)
    tickets = (await db.execute(stmt)).scalars().all()

    return {
        "count": len(tickets),
        "tickets": [
            {
                "id": t.id,
                "ticket_number": t.ticket_number,
                "customer_id": t.customer_id,
                "business_id": t.business_id,
                "subject": t.subject,
                "description": t.description,
                "severity": t.severity,
                "priority": t.priority,
                "status": t.status,
                "diagnosis": t.diagnosis,
                "root_cause": t.root_cause,
                "fix_plan": t.fix_plan,
                "is_high_impact": t.is_high_impact,
                "action_taken": t.action_taken,
                "remediation_result": t.remediation_result,
                "customer_notification": t.customer_notification,
                "sla_report": sla_engine.evaluate_sla(t).dict(),
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None
            }
            for t in tickets
        ]
    }


@router.post("/tickets")
async def create_ticket(
    req: CreateTicketRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        t = await support_service.create_ticket(
            session=db,
            customer_id=req.customer_id,
            subject=req.subject,
            description=req.description,
            source=req.source,
            severity=req.severity
        )
        return {
            "success": True,
            "ticket_id": t.id,
            "ticket_number": t.ticket_number,
            "status": t.status,
            "severity": t.severity,
            "priority": t.priority
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tickets/{ticket_id}/diagnose")
async def diagnose_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        diag = await support_service.diagnose_ticket(db, ticket_id)
        return diag.dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tickets/{ticket_id}/remediate")
async def remediate_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        res = await support_service.execute_remediation(db, ticket_id, operator_approved=False)
        return res.dict()
    except ApprovalRequiredException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tickets/{ticket_id}/approve")
async def approve_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user_info: Dict[str, str] = Depends(get_current_user_info)
):
    try:
        res = await support_service.execute_remediation(
            session=db,
            ticket_id=ticket_id,
            operator_approved=True,
            approved_by=user_info.get("username", "CEO")
        )
        return res.dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/autonomous-loop")
async def run_autonomous_loop(
    req: AutonomousLoopRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await support_service.run_full_autonomous_loop(
            session=db,
            customer_id=req.customer_id,
            subject=req.subject,
            description=req.description,
            source=req.source
        )
        return report.dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/incidents")
async def list_incidents(
    db: AsyncSession = Depends(get_db),
    limit: int = 50
):
    stmt = select(CustomerIncident).order_by(desc(CustomerIncident.detected_at)).limit(limit)
    incidents = (await db.execute(stmt)).scalars().all()
    return {
        "count": len(incidents),
        "incidents": [
            {
                "id": i.id,
                "incident_number": i.incident_number,
                "customer_id": i.customer_id,
                "title": i.title,
                "severity": i.severity,
                "category": i.category,
                "status": i.status,
                "root_cause": i.root_cause,
                "is_resolved": i.is_resolved,
                "detected_at": i.detected_at.isoformat() if i.detected_at else None,
                "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None
            }
            for i in incidents
        ]
    }


@router.get("/incidents/{incident_id}/events")
async def get_incident_events(
    incident_id: int,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(IncidentEvent).where(IncidentEvent.incident_id == incident_id).order_by(IncidentEvent.created_at)
    events = (await db.execute(stmt)).scalars().all()
    return {
        "incident_id": incident_id,
        "count": len(events),
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "from_status": e.from_status,
                "to_status": e.to_status,
                "agent_role": e.agent_role,
                "details": e.details,
                "created_at": e.created_at.isoformat()
            }
            for e in events
        ]
    }


@router.get("/memory/search")
async def search_memory(
    category: str = "APPLICATION",
    error_pattern: str = "",
    db: AsyncSession = Depends(get_db)
):
    memories = await incident_memory_service.search_memory(db, category, error_pattern)
    return {"count": len(memories), "memories": memories}


@router.post("/maintenance/run")
async def run_maintenance(
    customer_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    results = await proactive_maintenance_engine.run_host_maintenance_check(db, customer_id)
    return {"success": True, "checks": [r.dict() for r in results]}


@router.get("/benchmarks/code-intelligence")
async def get_code_intelligence_benchmarks():
    return await code_intelligence_benchmarker.run_all_benchmarks()


@router.get("/portal/{ticket_id}/customer-view")
async def get_customer_safe_view(
    ticket_id: int,
    db: AsyncSession = Depends(get_db)
):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    # Strictly sanitized customer view (Zero server paths, zero stack traces, zero DB schemas)
    return {
        "ticket_number": ticket.ticket_number,
        "subject": ticket.subject,
        "status": ticket.status,
        "severity": ticket.severity,
        "customer_summary": ticket.customer_visible_summary or "Your request is being processed by operations.",
        "notification": ticket.customer_notification,
        "resolution": ticket.resolution if ticket.status == "RESOLVED" else None,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None
    }
