"""
Intelligence & Optimization API Routes — Mega Prompt 8.
Exposes endpoints for lead prioritization, next best action, conversation intelligence,
sales funnel analytics, predictive maintenance, and optimization recommendations.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.database.connection import get_db
from app.api.routes import get_current_user_info
from app.intelligence import (
    lead_intelligence_engine,
    prospect_priority_engine,
    next_best_action_engine,
    conversation_intelligence_engine,
    sales_intelligence_engine,
    funnel_analytics_engine,
    proposal_optimization_engine,
    payment_intelligence_engine,
    customer_intelligence_engine,
    predictive_maintenance_engine,
    code_benchmark_harness,
    data_quality_engine,
    optimization_engine,
    revenue_optimization_engine,
    cost_engine,
    signal_registry,
    specialized_orchestrator,
    AnalystTask
)

router = APIRouter(prefix="/api/intelligence", tags=["Intelligence & Optimization"])


class ClassifyMessageRequest(BaseModel):
    message: str
    business_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None


class RecommendationActionRequest(BaseModel):
    action: str  # ACCEPT, REJECT, EXECUTE


@router.get("/overview")
async def get_intelligence_overview(
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Returns top-level executive intelligence summary across revenue, funnel, and system health."""
    revenue = await revenue_optimization_engine.get_revenue_summary(session)
    funnel = await funnel_analytics_engine.get_funnel_metrics(session)
    maintenance = await predictive_maintenance_engine.analyze_host_trends(session)
    costs = await cost_engine.get_cost_summary(session)
    recommendations = await optimization_engine.generate_system_recommendations(session)

    return {
        "status": "HEALTHY",
        "revenue_intelligence": revenue,
        "funnel_analytics": funnel,
        "predictive_maintenance": maintenance,
        "cost_efficiency": costs,
        "active_recommendations_count": len(recommendations),
        "recommendations": [r.model_dump() for r in recommendations[:5]]
    }


@router.get("/signals/{entity_type}/{entity_id}")
async def get_entity_signals(
    entity_type: str,
    entity_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Retrieves all active unexpired canonical intelligence signals for a specific entity."""
    signals = await signal_registry.get_active_signals_for_entity(session, entity_type, entity_id)
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "signals_count": len(signals),
        "signals": [s.model_dump() for s in signals]
    }


@router.get("/prioritization")
async def get_prioritized_prospects(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Returns ranked prospect opportunities ordered by deterministic Expected Commercial Value."""
    ranked = await prospect_priority_engine.rank_prospects(session, limit=limit)
    return {
        "count": len(ranked),
        "prospects": ranked
    }


@router.get("/next-best-action/{business_id}")
async def get_next_best_action(
    business_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Computes the policy-vetted next best action for a given business."""
    decision = await next_best_action_engine.determine_next_action(session, business_id)
    return decision.model_dump()


@router.post("/conversation/classify")
async def classify_conversation_message(
    payload: ClassifyMessageRequest,
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Analyzes an incoming message for buyer intent and objection categorization."""
    result = await conversation_intelligence_engine.analyze_message(
        raw_message=payload.message,
        business_context=payload.context
    )
    return result


@router.get("/funnel")
async def get_funnel_analytics(
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Returns 12-stage sales funnel telemetry and bottleneck radar."""
    metrics = await funnel_analytics_engine.get_funnel_metrics(session)
    return metrics


@router.get("/recommendations")
async def get_optimization_recommendations(
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Returns prioritized system optimization recommendations."""
    recs = await optimization_engine.generate_system_recommendations(session)
    return {
        "count": len(recs),
        "recommendations": [r.model_dump() for r in recs]
    }


@router.get("/benchmarks/code")
async def get_code_intelligence_benchmarks(
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Executes empirical benchmarking across code intelligence providers."""
    results = await code_benchmark_harness.run_comprehensive_benchmark()
    return results


@router.get("/data-quality")
async def audit_data_quality(
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Audits database records and returns DATA_QUALITY_SCORE and anomaly logs."""
    report = await data_quality_engine.audit_lead_database(session)
    return report.model_dump()


@router.get("/revenue")
async def get_revenue_intelligence(
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Returns Actual, Expected, Projected, and Hypothetical commercial revenue breakdown."""
    summary = await revenue_optimization_engine.get_revenue_summary(session)
    return summary


@router.get("/maintenance")
async def get_maintenance_intelligence(
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Returns predictive host headroom and maintenance forecasts."""
    maint = await predictive_maintenance_engine.analyze_host_trends(session)
    return maint


@router.get("/customer-health/{customer_id}")
async def get_customer_health(
    customer_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: Dict[str, str] = Depends(get_current_user_info)
) -> Dict[str, Any]:
    """Returns multi-signal customer health and churn risk predictions."""
    health = await customer_intelligence_engine.evaluate_customer_health(session, customer_id)
    return health
