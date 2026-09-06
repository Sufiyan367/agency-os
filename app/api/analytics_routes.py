"""
Analytics API Routes for JARVIS // AG Decision Dashboard.
Phase 14 Production Implementation.

Read-only endpoints exposing live telemetry calculated strictly from persisted database state.
Protected by existing authentication & RBAC middleware.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.analytics.service import analytics_service
from app.core.logging import logger

router = APIRouter(prefix="/api/analytics", tags=["Decision Dashboard & Analytics"])


@router.get("/overview", response_model=Dict[str, Any])
async def get_overview(
    time_filter: Optional[str] = Query(default="all", description="today | 7d | 30d | 90d | all"),
    session: AsyncSession = Depends(get_db)
):
    """Returns Executive Overview KPI metrics."""
    try:
        return await analytics_service.get_executive_overview(session, time_filter=time_filter or "all")
    except Exception as e:
        logger.error(f"[AnalyticsAPI] get_overview failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate executive overview metrics.")


@router.get("/funnel", response_model=Dict[str, Any])
async def get_funnel(
    time_filter: Optional[str] = Query(default="all", description="today | 7d | 30d | 90d | all"),
    session: AsyncSession = Depends(get_db)
):
    """Returns Acquisition Funnel conversion and drop-off analysis."""
    try:
        return await analytics_service.get_acquisition_funnel(session, time_filter=time_filter or "all")
    except Exception as e:
        logger.error(f"[AnalyticsAPI] get_funnel failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate acquisition funnel.")


@router.get("/market-radar", response_model=Dict[str, Any])
async def get_market_radar(
    session: AsyncSession = Depends(get_db)
):
    """Returns Market Radar by Country and Niche with evidence/model separation."""
    try:
        return await analytics_service.get_market_radar(session)
    except Exception as e:
        logger.error(f"[AnalyticsAPI] get_market_radar failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate market radar.")


@router.get("/quality", response_model=Dict[str, Any])
@router.get("/prospect-quality", response_model=Dict[str, Any])
async def get_quality(
    time_filter: Optional[str] = Query(default="all", description="today | 7d | 30d | 90d | all"),
    session: AsyncSession = Depends(get_db)
):
    """Returns Prospect Quality, Evidence Score, and Website Health distributions."""
    try:
        return await analytics_service.get_prospect_quality_distribution(session, time_filter=time_filter or "all")
    except Exception as e:
        logger.error(f"[AnalyticsAPI] get_quality failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate quality distributions.")


@router.get("/services", response_model=Dict[str, Any])
@router.get("/service-demand", response_model=Dict[str, Any])
async def get_services(
    time_filter: Optional[str] = Query(default="all", description="today | 7d | 30d | 90d | all"),
    session: AsyncSession = Depends(get_db)
):
    """Returns demand distribution across the 10 catalog services."""
    try:
        return await analytics_service.get_service_demand_distribution(session, time_filter=time_filter or "all")
    except Exception as e:
        logger.error(f"[AnalyticsAPI] get_services failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate service demand distribution.")


@router.get("/sales", response_model=Dict[str, Any])
async def get_sales(
    time_filter: Optional[str] = Query(default="all", description="today | 7d | 30d | 90d | all"),
    session: AsyncSession = Depends(get_db)
):
    """Returns Sales Analytics with zero-denominator safety."""
    try:
        return await analytics_service.get_sales_analytics(session, time_filter=time_filter or "all")
    except Exception as e:
        logger.error(f"[AnalyticsAPI] get_sales failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate sales analytics.")


@router.get("/revenue", response_model=Dict[str, Any])
async def get_revenue(
    time_filter: Optional[str] = Query(default="all", description="today | 7d | 30d | 90d | all"),
    session: AsyncSession = Depends(get_db)
):
    """Returns Revenue Analytics with explicit pipeline vs revenue separation."""
    try:
        return await analytics_service.get_revenue_analytics(session, time_filter=time_filter or "all")
    except Exception as e:
        logger.error(f"[AnalyticsAPI] get_revenue failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate revenue analytics.")


@router.get("/estimated-value", response_model=Dict[str, Any])
async def get_estimated_value(
    time_filter: Optional[str] = Query(default="all", description="today | 7d | 30d | 90d | all"),
    session: AsyncSession = Depends(get_db)
):
    """Returns Estimated Recoverable Value with mandatory model disclosure."""
    try:
        return await analytics_service.get_estimated_value(session, time_filter=time_filter or "all")
    except Exception as e:
        logger.error(f"[AnalyticsAPI] get_estimated_value failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate estimated value.")


@router.get("/model-outputs", response_model=Dict[str, Any])
async def get_model_outputs(
    time_filter: Optional[str] = Query(default="all", description="today | 7d | 30d | 90d | all"),
    session: AsyncSession = Depends(get_db)
):
    """Returns Model Output statistics strictly tagged INTERNAL ONLY."""
    try:
        return await analytics_service.get_model_outputs_summary(session, time_filter=time_filter or "all")
    except Exception as e:
        logger.error(f"[AnalyticsAPI] get_model_outputs failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate model outputs summary.")


@router.get("/data-quality", response_model=Dict[str, Any])
async def get_data_quality(
    session: AsyncSession = Depends(get_db)
):
    """Returns Data Quality, evidence coverage, stale counts, and failure rates."""
    try:
        return await analytics_service.get_data_quality_metrics(session)
    except Exception as e:
        logger.error(f"[AnalyticsAPI] get_data_quality failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate data quality metrics.")
