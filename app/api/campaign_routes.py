"""International Outbound Campaigns API Routes."""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.campaigns.service import campaign_service
from app.campaigns.models import CampaignDTO, RolloutConfigDTO, ComplianceGateResult
from app.campaigns.compliance_gate import campaign_compliance_gate
from app.core.logging import logger

campaign_router = APIRouter(prefix="/api/campaigns", tags=["International Campaigns"])


class RolloutLevelUpdateRequest(BaseModel):
    level: int = Field(..., ge=0, le=7, description="Target rollout level (0-7)")
    confirm: bool = Field(True, description="Explicit confirmation required to change live volume")


class CampaignUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, description="Campaign status: ACTIVE, PAUSED, COMPLETED")
    daily_quota: Optional[int] = Field(None, ge=1, le=100, description="Daily outbound quota for this campaign")
    enabled: Optional[bool] = Field(None, description="Enable or disable campaign")


class PreflightCheckRequest(BaseModel):
    recipient_email: str
    subject: str = "Technical Diagnostic Suggestion"
    body: str = "Hi there, regarding your web infrastructure..."
    force_live: bool = False


@campaign_router.get("", response_model=Dict[str, Any])
async def list_campaigns(
    include_stats: bool = True,
    session: AsyncSession = Depends(get_db)
):
    """
    Returns all 18 international outbound campaigns with real-time stats,
    current sending window status, timezone, and daily quota consumption.
    """
    try:
        campaigns = await campaign_service.list_campaigns(session, include_stats=include_stats)
        rollout = campaign_service.get_rollout_status()
        
        total_daily_capacity = sum(c.daily_quota for c in campaigns)
        total_today_sent = sum(c.today_sent for c in campaigns)
        total_today_remaining = sum(c.today_remaining for c in campaigns)
        
        return {
            "status": "SUCCESS",
            "count": len(campaigns),
            "rollout_level": rollout.current_level,
            "rollout_level_name": rollout.current_level_name,
            "rollout_live_cap": rollout.daily_max_real_emails,
            "is_simulation": rollout.is_simulation,
            "total_daily_capacity": total_daily_capacity,
            "total_today_sent": total_today_sent,
            "total_today_remaining": total_today_remaining,
            "campaigns": [c.model_dump() for c in campaigns]
        }
    except Exception as e:
        logger.error(f"[CampaignsAPI] Failed listing campaigns: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve campaigns: {str(e)}"
        )


@campaign_router.get("/rollout", response_model=Dict[str, Any])
async def get_rollout_configuration():
    """
    Returns the current progressive rollout stage configuration and rules (Levels 0-7).
    """
    try:
        rollout = campaign_service.get_rollout_status()
        return {
            "status": "SUCCESS",
            "rollout": rollout.model_dump()
        }
    except Exception as e:
        logger.error(f"[CampaignsAPI] Failed fetching rollout config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve rollout configuration: {str(e)}"
        )


@campaign_router.post("/rollout/level", response_model=Dict[str, Any])
async def set_rollout_level(req: RolloutLevelUpdateRequest):
    """
    Updates the progressive rollout stage.
    INVARIANT: Advancement requires explicit CEO confirmation.
    """
    try:
        if not req.confirm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rollout level adjustment requires explicit confirmation (confirm=True)."
            )

        updated = campaign_service.set_rollout_level(req.level)
        return {
            "status": "SUCCESS",
            "message": f"Rollout level updated to Level {updated.current_level}: {updated.current_level_name}",
            "rollout": updated.model_dump()
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CampaignsAPI] Failed updating rollout level: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update rollout level: {str(e)}"
        )


@campaign_router.get("/{campaign_id}", response_model=Dict[str, Any])
async def get_campaign_detail(
    campaign_id: int,
    session: AsyncSession = Depends(get_db)
):
    """
    Retrieves detailed metadata, sending window, and stats for a single campaign.
    """
    from app.database.models import Campaign
    camp = await session.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found.")

    dto = await campaign_service.get_campaign_dto(session, camp)
    return {
        "status": "SUCCESS",
        "campaign": dto.model_dump()
    }


@campaign_router.patch("/{campaign_id}", response_model=Dict[str, Any])
async def update_campaign(
    campaign_id: int,
    req: CampaignUpdateRequest,
    session: AsyncSession = Depends(get_db)
):
    """
    Updates campaign status or daily quota limit.
    """
    from app.database.models import Campaign
    camp = await session.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found.")

    if req.status is not None:
        camp.status = req.status.strip().upper()
    if req.daily_quota is not None:
        camp.daily_quota = req.daily_quota
    if req.enabled is not None:
        camp.enabled = req.enabled

    await session.commit()
    await session.refresh(camp)

    dto = await campaign_service.get_campaign_dto(session, camp)
    return {
        "status": "SUCCESS",
        "message": f"Campaign '{camp.name}' updated.",
        "campaign": dto.model_dump()
    }


@campaign_router.post("/{campaign_id}/preflight", response_model=Dict[str, Any])
async def preflight_compliance_check(
    campaign_id: int,
    req: PreflightCheckRequest,
    session: AsyncSession = Depends(get_db)
):
    """
    Simulates the 10-point deterministic pre-send compliance gate for a given recipient.
    Does NOT send an email or alter message state.
    """
    from app.database.models import Campaign, OutreachMessage, OutreachStatus
    camp = await session.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found.")

    # Create dummy message for dry-run evaluation
    dummy_msg = OutreachMessage(
        campaign_id=camp.id,
        recipient_email=req.recipient_email,
        subject=req.subject,
        body=req.body,
        status=OutreachStatus.APPROVED.value
    )

    gate_result = await campaign_compliance_gate.evaluate_pre_send(
        session=session,
        message=dummy_msg,
        campaign=camp,
        force_live=req.force_live
    )

    return {
        "status": "SUCCESS",
        "campaign_id": camp.id,
        "country_code": camp.country_code,
        "is_eligible": gate_result.is_eligible,
        "failure_reasons": gate_result.failure_reasons,
        "checks": [c.model_dump() for c in gate_result.checks],
        "quota": gate_result.quota_result.model_dump() if gate_result.quota_result else None
    }
