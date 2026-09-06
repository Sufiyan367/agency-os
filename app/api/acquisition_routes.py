from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database.connection import get_db
from app.acquisition.config import country_config_manager
from app.acquisition.pool import global_prospect_pool
from app.acquisition.ranking import global_ranker
from app.acquisition.controller import active_prospect_controller
from app.acquisition.models import ActiveSlotStatus, GlobalQueueItem, CountryConfigDTO
from app.core.logging import logger

router = APIRouter(prefix="/api/acquisition", tags=["Global Acquisition & Outreach"])

class RunDiscoveryRequest(BaseModel):
    countries: Optional[List[str]] = None
    target_per_country: int = 3
    niche: Optional[str] = None

class SelectNextRequest(BaseModel):
    business_id: Optional[int] = None

class PrepareOutreachRequest(BaseModel):
    business_id: Optional[int] = None

class ApproveOutreachRequest(BaseModel):
    message_id: Optional[int] = None
    force_live: bool = False

class SimulateReplyRequest(BaseModel):
    reply_text: str
    sender_email: Optional[str] = None

class ReleaseActiveRequest(BaseModel):
    terminal_reason: str = "MANUAL_RELEASE"
    notes: Optional[str] = None

# 1. Multi-Country Configuration Endpoints
@router.get("/countries", response_model=List[CountryConfigDTO])
async def list_country_configurations(db: AsyncSession = Depends(get_db)):
    """Lists all configured countries and their regional parameters."""
    return await country_config_manager.list_countries(db)

@router.post("/countries/{country_code}/enable")
async def enable_country(country_code: str, db: AsyncSession = Depends(get_db)):
    """Enables multi-country acquisition for the given country."""
    cfg = await country_config_manager.set_enabled(db, country_code, True)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found.")
    return {"status": "ENABLED", "country_code": country_code.upper()}

@router.post("/countries/{country_code}/disable")
async def disable_country(country_code: str, db: AsyncSession = Depends(get_db)):
    """Disables multi-country acquisition for the given country."""
    cfg = await country_config_manager.set_enabled(db, country_code, False)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found.")
    return {"status": "DISABLED", "country_code": country_code.upper()}

# 2. Global Discovery Execution
@router.post("/run-discovery")
async def trigger_global_discovery(req: RunDiscoveryRequest, db: AsyncSession = Depends(get_db)):
    """
    Triggers parallel prospect discovery across all enabled target countries,
    deduplicates globally, audits websites, and computes client intelligence.
    """
    logger.info(f"[AcquisitionAPI] Triggering global discovery (countries={req.countries}, target_per_country={req.target_per_country})")
    discovered = await global_prospect_pool.discover_across_countries(
        session=db,
        countries=req.countries,
        target_per_country=req.target_per_country,
        niche=req.niche
    )
    if discovered:
        await global_prospect_pool.enrich_and_audit_prospects(session=db, businesses=discovered)

    return {
        "status": "COMPLETED",
        "discovered_count": len(discovered),
        "prospects": [
            {
                "id": b.id,
                "name": b.name,
                "domain": b.domain,
                "country": b.country,
                "city": b.city,
                "verification_status": b.verification_status,
                "pipeline_stage": b.pipeline_stage
            }
            for b in discovered
        ]
    }

# 3. Global Prospect Pool & Dynamic Ranking
@router.get("/pool-status")
async def get_pool_status(db: AsyncSession = Depends(get_db)):
    """Returns real-time aggregated metrics for the global prospect pool."""
    return await global_prospect_pool.get_pool_status(db)

@router.get("/global-queue", response_model=List[GlobalQueueItem])
async def get_global_queue(limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)):
    """
    Dynamically re-ranks the global uncontacted prospect pool using multi-criteria EV math.
    Returns complete transparent decision traces ('WHY THIS BUSINESS?').
    """
    return await global_ranker.rank_pool(db, limit=limit)

# 4. Singular Active Outreach Slot Management (MAX_ACTIVE_OUTREACH = 1)
@router.get("/active", response_model=ActiveSlotStatus)
async def get_active_outreach_slot(db: AsyncSession = Depends(get_db)):
    """Returns the current state of the active outreach slot."""
    return await active_prospect_controller.get_active_status(db)

@router.post("/select-next", response_model=ActiveSlotStatus)
async def select_next_active_prospect(req: SelectNextRequest, db: AsyncSession = Depends(get_db)):
    """
    Locks the singular active outreach slot onto the top-ranked candidate.
    Returns HTTP 409 Conflict if the slot is currently occupied.
    """
    try:
        return await active_prospect_controller.select_next_prospect(db, business_id=req.business_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.post("/{business_id}/prepare-outreach")
async def prepare_outreach_for_active(
    business_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Drafts evidence-grounded outreach for the active prospect and places it in PENDING_APPROVAL.
    Enforces the human operator approval gate.
    """
    try:
        return await active_prospect_controller.prepare_outreach(db, business_id=business_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{business_id}/approve-outreach")
async def approve_and_send_outreach(
    business_id: int,
    req: ApproveOutreachRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Approves draft outreach and dispatches email.
    Transitions slot to WAITING_FOR_REPLY.
    """
    try:
        return await active_prospect_controller.approve_and_send(
            session=db,
            business_id=business_id,
            message_id=req.message_id,
            force_live=req.force_live
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{business_id}/simulate-reply")
async def simulate_inbound_reply(
    business_id: int,
    req: SimulateReplyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Ingests and classifies inbound prospect reply.
    Automatically handles opt-outs, stops followups, or moves to negotiation.
    """
    try:
        return await active_prospect_controller.record_reply(
            session=db,
            business_id=business_id,
            reply_text=req.reply_text,
            sender_email=req.sender_email
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/release-active")
async def release_active_prospect(req: ReleaseActiveRequest, db: AsyncSession = Depends(get_db)):
    """
    Releases the active prospect slot, returning it to IDLE.
    Enables selection of the next top-ranked global candidate.
    """
    return await active_prospect_controller.release_active_slot(
        session=db,
        terminal_reason=req.terminal_reason,
        notes=req.notes
    )
