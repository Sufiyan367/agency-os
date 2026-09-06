"""
Autonomous Agent Observability & Control Routes — Phase 15.

Exposes:
- GET /api/agent/autonomous-status (Full operator telemetry)
- POST /api/agent/pause (Operator pause control)
- POST /api/agent/resume (Operator resume control)
- POST /api/agent/emergency-stop (Operator kill switch)
- POST /api/agent/cycle-step (Atomic loop step execution)
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database.connection import get_db
from app.acquisition.autonomous_controller import autonomous_acquisition_controller
from app.core.logging import logger

router = APIRouter(prefix="/api/agent", tags=["Autonomous Operator Observability & Safety"])


class EmergencyStopRequest(BaseModel):
    reason: Optional[str] = "Operator initiated emergency kill switch"


@router.get("/autonomous-status")
async def get_autonomous_status(session: AsyncSession = Depends(get_db)):
    """Returns real-time operator observability telemetry across all 14 mandatory fields."""
    try:
        return await autonomous_acquisition_controller.get_live_status(session)
    except Exception as e:
        logger.error(f"[AutonomousAPI] Failed to fetch autonomous status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch autonomous status telemetry.")


@router.post("/pause")
async def pause_autonomous_controller():
    """Pauses autonomous agent operations."""
    autonomous_acquisition_controller.pause()
    return {"status": "PAUSED", "message": "Autonomous controller paused."}


@router.post("/resume")
async def resume_autonomous_controller():
    """Resumes autonomous agent operations."""
    autonomous_acquisition_controller.resume()
    return {"status": "RUNNING", "message": "Autonomous controller resumed."}


@router.post("/emergency-stop")
async def emergency_stop_autonomous_controller(req: EmergencyStopRequest = EmergencyStopRequest()):
    """
    Emergency kill switch: immediately halts all autonomous activities,
    cancels pending dispatches, and blocks commercial outreach.
    """
    res = autonomous_acquisition_controller.emergency_stop(reason=req.reason or "Operator Kill Switch Activated")
    return res


@router.post("/cycle-step")
async def execute_autonomous_cycle_step(session: AsyncSession = Depends(get_db)):
    """
    Executes one atomic step through the autonomous acquisition loop.
    Safe for testing, verification, and deterministic execution.
    """
    try:
        return await autonomous_acquisition_controller.advance_cycle_step(session)
    except Exception as e:
        logger.error(f"[AutonomousAPI] Cycle step error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))