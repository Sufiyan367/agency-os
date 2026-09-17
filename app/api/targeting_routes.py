"""
Global Acquisition Targeting API Endpoints
Autonomous B2B Lead-Gen & Revenue Operations Platform

Exposes:
- Global Country -> Region -> City -> Niche catalog query endpoints
- TargetDefinition CRUD (/api/targets)
- Aggregated real-time targeting metrics (/api/targeting/summary)
- Priority target queue execution
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database.connection import get_db
from app.acquisition.targeting_catalog import (
    list_countries,
    get_country,
    get_regions_for_country,
    get_cities_for_region,
    get_niches_for_country,
    NICHE_CATALOG
)
from app.acquisition.targeting_manager import targeting_manager
from app.acquisition.pool import global_prospect_pool
from app.core.logging import logger

router = APIRouter(tags=["Global Targeting & Acquisition"])

# DTOs
class TargetCreateRequest(BaseModel):
    country_code: str = Field(..., description="2-letter ISO country code, e.g. US, AE, SA, IN")
    region: str = Field(..., description="Administrative region name, e.g. Texas, Dubai, Maharashtra")
    city: str = Field(..., description="City name, e.g. Houston, Dubai, Pune")
    niche: str = Field(..., description="Canonical niche ID or recognized alias, e.g. HVAC, DENTAL, Real Estate")
    priority: str = Field(default="P1", description="Target priority: P1, P2, P3")
    status: str = Field(default="ACTIVE", description="Status: ACTIVE, PAUSED, DISABLED")

class TargetUpdateRequest(BaseModel):
    priority: Optional[str] = Field(None, description="P1, P2, P3")
    status: Optional[str] = Field(None, description="ACTIVE, PAUSED, DISABLED")
    enabled: Optional[bool] = None

class TargetResponseDTO(BaseModel):
    id: int
    country_code: str
    country_name: str
    region: str
    region_type: str
    city: str
    niche_id: str
    niche_name: str
    priority: str
    status: str
    enabled: bool
    created_at: str

    @classmethod
    def from_model(cls, model) -> "TargetResponseDTO":
        return cls(
            id=model.id,
            country_code=model.country_code,
            country_name=model.country_name,
            region=model.region,
            region_type=model.region_type,
            city=model.city,
            niche_id=model.niche_id,
            niche_name=model.niche_name,
            priority=model.priority,
            status=model.status,
            enabled=model.enabled,
            created_at=model.created_at.strftime("%Y-%m-%d %H:%M") if model.created_at else ""
        )

# ==============================================================================
# 1. CATALOG QUERY ENDPOINTS
# ==============================================================================

@router.get("/api/targeting/countries")
async def get_targeting_countries():
    """Lists all 41 supported countries with administrative region types and currency."""
    return list_countries()

@router.get("/api/targeting/regions")
async def get_targeting_regions(
    country: str = Query(..., description="2-letter ISO country code, e.g. US")
):
    """Returns administrative regions for a given country."""
    c_def = get_country(country)
    if not c_def:
        raise HTTPException(status_code=404, detail=f"Country '{country}' not found in global catalog.")
    return {
        "country_code": c_def.code,
        "country_name": c_def.name,
        "region_type": c_def.region_type,
        "regions": get_regions_for_country(country)
    }

@router.get("/api/targeting/cities")
async def get_targeting_cities(
    country: str = Query(..., description="2-letter ISO country code, e.g. US"),
    region: str = Query(..., description="Administrative region name, e.g. Texas")
):
    """Returns cities for an administrative region."""
    cities = get_cities_for_region(country, region)
    if not cities:
        c_def = get_country(country)
        if not c_def:
            raise HTTPException(status_code=404, detail=f"Country '{country}' not found.")
        raise HTTPException(
            status_code=404,
            detail=f"No cities found for region '{region}' in {c_def.name}."
        )
    return {
        "country_code": country.upper().strip(),
        "region": region,
        "cities": cities
    }

@router.get("/api/targeting/niches")
async def get_targeting_niches(
    country: Optional[str] = Query(None, description="Optional 2-letter country code to get country-specific niches")
):
    """Returns canonical niches, optionally filtered for a specific country."""
    if country:
        return get_niches_for_country(country)
    return [
        {
            "niche_id": n.id,
            "name": n.name,
            "category": n.category,
            "min_estimated_service_value": n.min_estimated_service_value
        }
        for n in NICHE_CATALOG.values()
    ]

@router.get("/api/targeting/summary")
async def get_targeting_summary(db: AsyncSession = Depends(get_db)):
    """Returns real-time aggregated metrics for global acquisition targeting."""
    return await targeting_manager.get_targeting_summary(db)

@router.get("/api/targeting/market-overview")
async def get_market_overview(db: AsyncSession = Depends(get_db)):
    """Returns overview of all countries, their market classifications, priority tiers, and active target counts."""
    return await targeting_manager.list_market_overview(db)

# ==============================================================================
# 2. TARGET DEFINITIONS CRUD (/api/targets)
# ==============================================================================

@router.get("/api/targets", response_model=List[TargetResponseDTO])
async def list_configured_targets(
    country: Optional[str] = None,
    region: Optional[str] = None,
    city: Optional[str] = None,
    niche: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Returns list of configured targets with optional cascading filters."""
    targets = await targeting_manager.list_targets(
        session=db,
        country_code=country,
        region=region,
        city=city,
        niche_id=niche,
        status=status,
        priority=priority
    )
    return [TargetResponseDTO.from_model(t) for t in targets]

@router.post("/api/targets", response_model=TargetResponseDTO)
async def create_target_definition(
    req: TargetCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Creates a new canonical target definition. Validates hierarchy and rejects duplicates."""
    try:
        target = await targeting_manager.create_target(
            session=db,
            country_code=req.country_code,
            region=req.region,
            city=req.city,
            niche=req.niche,
            priority=req.priority,
            status=req.status
        )
        return TargetResponseDTO.from_model(target)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/api/targets/{target_id}", response_model=TargetResponseDTO)
async def update_target_definition(
    target_id: int = Path(..., description="ID of target definition"),
    req: TargetUpdateRequest = None,
    db: AsyncSession = Depends(get_db)
):
    """Updates status (ACTIVE/PAUSED/DISABLED), priority (P1/P2/P3), or enabled flag."""
    priority = req.priority if req else None
    status = req.status if req else None
    enabled = req.enabled if req else None

    target = await targeting_manager.update_target(
        session=db,
        target_id=target_id,
        priority=priority,
        status=status,
        enabled=enabled
    )
    if not target:
        raise HTTPException(status_code=404, detail=f"Target #{target_id} not found.")
    return TargetResponseDTO.from_model(target)

@router.delete("/api/targets/{target_id}")
async def delete_target_definition(
    target_id: int = Path(..., description="ID of target definition to delete"),
    db: AsyncSession = Depends(get_db)
):
    """Removes a target definition."""
    deleted = await targeting_manager.delete_target(session=db, target_id=target_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Target #{target_id} not found.")
    return {"status": "DELETED", "target_id": target_id}

# Also support execution from active target queue
@router.post("/api/targeting/run-active-targets")
async def trigger_active_target_discovery(
    limit_targets: int = Query(default=3, ge=1, le=10),
    target_per_combination: int = Query(default=3, ge=1, le=10),
    db: AsyncSession = Depends(get_db)
):
    """
    Executes discovery for the top active targets in priority order (P1 > P2 > P3).
    Saves new verified businesses with full targeting provenance.
    """
    discovered = await global_prospect_pool.discover_from_active_targets(
        session=db,
        limit_targets=limit_targets,
        target_per_combination=target_per_combination
    )
    return {
        "status": "COMPLETED",
        "discovered_count": len(discovered),
        "prospects": [
            {
                "id": b.id,
                "name": b.name,
                "domain": b.domain,
                "country": b.country,
                "administrative_region": b.administrative_region,
                "city": b.city,
                "niche": b.niche,
                "verification_status": b.verification_status
            }
            for b in discovered
        ]
    }


# ==============================================================================
# 3. AUTONOMOUS MULTI-MARKET ACQUISITION & CEO OPS ENDPOINTS
# ==============================================================================

class CEOOverrideRequest(BaseModel):
    action: str = Field(..., description="Override action: pause, exclude, force, emergency_stop, clear")
    market_key: Optional[str] = Field(None, description="Canonical market key: COUNTRY:REGION:CITY:NICHE or ALL")
    reason: Optional[str] = Field(default="CEO manual intervention", description="Audit rationale")


@router.get("/api/targeting/autonomous-queue")
async def get_autonomous_targeting_queue(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the real-time autonomous acquisition state:
    - Active market portfolio (with reason codes, explore/exploit classification, freshness)
    - Next candidate targets prioritized by multi-factor score
    - Currently running operations counters (discovery, research, audit, demos, deploys)
    - CEO overrides in effect
    """
    from app.market_intelligence.autonomous_market_engine import autonomous_market_engine
    return await autonomous_market_engine.get_autonomous_target_queue(session=db, limit=limit)


@router.post("/api/targeting/rebalance")
async def rebalance_autonomous_portfolio(
    db: AsyncSession = Depends(get_db)
):
    """
    Triggers an immediate autonomous rebalance of the market acquisition portfolio.
    Evaluates evidence, rotates underperforming or stale markets, and emits MARKET_REBALANCED event.
    """
    from app.market_intelligence.autonomous_market_engine import autonomous_market_engine
    result = await autonomous_market_engine.rebalance_portfolio(session=db)
    return {
        "status": "COMPLETED",
        "result": result
    }


@router.post("/api/targeting/override")
async def set_ceo_targeting_override(
    req: CEOOverrideRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Executes a CEO manual override on autonomous acquisition:
    - pause: Suspend discovery in specified market
    - exclude: Add market to exclusion list
    - force: Force immediate active status and discovery priority
    - emergency_stop: Immediately pause all active discovery
    - clear: Reset override for specified market or all
    """
    from app.market_intelligence.autonomous_market_engine import autonomous_market_engine
    res = await autonomous_market_engine.set_ceo_override(
        action=req.action,
        market_key=req.market_key,
        reason=req.reason,
        session=db
    )
    return res
