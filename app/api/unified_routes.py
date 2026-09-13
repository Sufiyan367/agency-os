"""
Unified Agency Orchestration API Routes — Mega Prompt 9.
Exposes control, lifecycle transitions, capacity intelligence, and simulation gates.
"""
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database.connection import get_db
from app.api.routes import get_current_user_info
from app.orchestrator.unified_orchestrator import unified_orchestrator
from app.lifecycle.canonical_lifecycle import (
    canonical_lifecycle_manager, CanonicalLifecycleStage
)
from app.orchestration.scheduler import deterministic_scheduler, CapacityReport
from app.simulation.end_to_end_simulator import end_to_end_simulator

router = APIRouter(prefix="/api/orchestration", tags=["Orchestration"])
ceo_router = APIRouter(prefix="/api/ceo", tags=["CEO Control"])


class TransitionRequest(BaseModel):
    target_stage: CanonicalLifecycleStage
    actor: str = "operator"
    reason: str = "Manual API state progression"
    idempotency_key: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SimulationRequest(BaseModel):
    industry: str = "automotive"
    business_name: Optional[str] = None


@router.get("/status")
async def get_orchestrator_status(
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Returns top-level operational status across the entire integrated Agency OS."""
    status = await unified_orchestrator.get_system_status(session)
    return status


@router.get("/capacity")
async def get_system_capacity(
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Evaluates real-time outbound capacity, active locks, and host headroom."""
    capacity = await deterministic_scheduler.evaluate_capacity(session)
    return capacity.model_dump()


@router.get("/lifecycle/{business_id}")
async def get_prospect_lifecycle_stage(
    business_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Returns canonical lifecycle stage and allowed next stages for a business."""
    from app.database.models import Business, Customer, Project, CustomerIncident
    from sqlalchemy import select, desc

    biz = await session.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail=f"Business #{business_id} not found.")

    stmt_cust = select(Customer).where(Customer.business_id == business_id)
    customer = (await session.execute(stmt_cust)).scalar_one_or_none()

    project = None
    if customer:
        stmt_proj = select(Project).where(Project.customer_id == customer.id).order_by(desc(Project.id))
        project = (await session.execute(stmt_proj)).scalars().first()

    stmt_inc = select(CustomerIncident).where(
        CustomerIncident.business_id == business_id,
        CustomerIncident.is_resolved == False
    )
    active_inc = (await session.execute(stmt_inc)).scalars().first()

    canonical = canonical_lifecycle_manager.map_to_canonical(biz, customer, project, active_inc)
    allowed_next = [s.value for s in canonical_lifecycle_manager.VALID_TRANSITIONS.get(canonical, [])]

    return {
        "business_id": business_id,
        "business_name": biz.name,
        "current_canonical_stage": canonical.value,
        "allowed_next_stages": allowed_next,
        "is_customer": bool(customer),
        "active_project_id": project.id if project else None,
        "has_active_incident": bool(active_inc)
    }


@router.post("/lifecycle/{business_id}/transition")
async def transition_prospect_lifecycle(
    business_id: int,
    payload: TransitionRequest,
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Executes a policy-vetted canonical state transition."""
    try:
        audit = await canonical_lifecycle_manager.transition(
            session=session,
            business_id=business_id,
            target_stage=payload.target_stage,
            actor=payload.actor,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
            metadata=payload.metadata
        )
        await session.commit()
        return audit.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/simulation/run")
async def run_end_to_end_simulation(
    payload: SimulationRequest,
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Executes a deterministic simulated closed revenue, delivery & support loop."""
    result = await end_to_end_simulator.simulate_single_prospect_full_loop(
        session=session,
        industry=payload.industry,
        business_name=payload.business_name
    )
    await session.commit()
    return result.model_dump()


# --- CEO CONTROL CENTER ENDPOINTS ---

@ceo_router.get("/unified-control")
async def get_ceo_unified_control_center(
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Returns top-level CEO executive telemetry across all 10 operational domains."""
    status = await unified_orchestrator.get_system_status(session)
    return status
