from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.database.connection import get_db

from app.database.models import Business, ProspectEvidence, DiscoveryRun, PipelineStage, VerificationStatus
from app.acquisition.prospect_discovery import real_prospect_discovery_engine
from app.acquisition.evidence_gate import prospect_evidence_gate
from app.acquisition.ranking import global_ranker
from app.acquisition.controller import active_prospect_controller
from app.core.logging import logger

router = APIRouter(prefix="/api/prospects", tags=["Real Prospect Acquisition & Evidence"])


class ProspectDiscoveryRequest(BaseModel):
    country_code: str = Field(default="US", description="Target country code (e.g. US, UK, CA, AU, SG)")
    niche_slug: str = Field(default="roofing-contractors", description="Target niche slug")
    target_count: int = Field(default=5, ge=1, le=50, description="Target prospects count")
    cities: Optional[List[str]] = Field(default=None, description="Optional target cities for multi-city spread")


@router.post("/discover", response_model=Dict[str, Any])
async def trigger_prospect_discovery(
    req: ProspectDiscoveryRequest,
    session: AsyncSession = Depends(get_db)
):
    """
    Triggers an end-to-end real web prospect acquisition run with multi-city geographic spread,
    multi-source empirical evidence extraction, and hard evidence gate enforcement.
    """
    try:
        result = await real_prospect_discovery_engine.discover_prospects_for_market(
            session=session,
            country_code=req.country_code,
            niche_slug=req.niche_slug,
            target_count=req.target_count,
            cities=req.cities
        )
        return result
    except Exception as e:
        logger.error(f"[ProspectRoutes] Discovery failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prospect discovery failed: {str(e)}"
        )


@router.get("/pipeline-status", response_model=Dict[str, Any])
async def get_prospect_pipeline_status(
    session: AsyncSession = Depends(get_db)
):
    """
    Returns aggregated metrics across the acquisition pipeline, evidence gate pass/fail counts,
    and active outreach slot status.
    """
    total_biz = (await session.execute(select(func.count(Business.id)))).scalar() or 0
    total_evidence = (await session.execute(select(func.count(ProspectEvidence.id)))).scalar() or 0

    # Counts by stage
    by_stage_stmt = select(Business.pipeline_stage, func.count(Business.id)).group_by(Business.pipeline_stage)
    stage_counts = dict((await session.execute(by_stage_stmt)).all())

    # Counts by verification status
    by_verif_stmt = select(Business.verification_status, func.count(Business.id)).group_by(Business.verification_status)
    verif_counts = dict((await session.execute(by_verif_stmt)).all())

    # Counts by research status
    by_res_stmt = select(Business.research_status, func.count(Business.id)).group_by(Business.research_status)
    res_counts = dict((await session.execute(by_res_stmt)).all())

    # Active outreach slot
    slot_status = await active_prospect_controller.get_active_status(session)

    return {
        "total_prospects": total_biz,
        "total_verified_evidence_items": total_evidence,
        "by_stage": stage_counts,
        "by_verification_status": verif_counts,
        "by_research_status": res_counts,
        "evidence_gate_passed": verif_counts.get("VERIFIED", 0),
        "insufficient_evidence_blocked": verif_counts.get("INSUFFICIENT_EVIDENCE", 0),
        "active_slot": slot_status.model_dump()
    }



@router.get("/evidence/{business_id}", response_model=Dict[str, Any])
async def get_prospect_evidence(
    business_id: int,
    session: AsyncSession = Depends(get_db)
):
    """
    Retrieves all empirical multi-source evidence items and gate evaluation result for a prospect.
    """
    biz = await session.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found.")

    ev_stmt = select(ProspectEvidence).where(
        ProspectEvidence.business_id == business_id
    ).order_by(ProspectEvidence.source_tier.asc(), ProspectEvidence.confidence_score.desc())
    evidence_items = list((await session.execute(ev_stmt)).scalars().all())

    gate_result = prospect_evidence_gate.evaluate_evidence(evidence_items)

    return {
        "business": {
            "id": biz.id,
            "name": biz.name,
            "domain": biz.domain,
            "country": biz.country,
            "city": biz.city,
            "niche": biz.niche,
            "verification_status": biz.verification_status,
            "research_status": biz.research_status,
            "pipeline_stage": biz.pipeline_stage,
            "evidence_count": biz.evidence_count,
            "effective_evidence_score": biz.effective_evidence_score,
            "evidence_confidence": biz.evidence_confidence,
            "prospect_score": biz.prospect_score
        },
        "evidence_items": [
            {
                "id": ev.id,
                "evidence_id": ev.evidence_id,
                "claim": ev.claim,
                "source_url": ev.source_url,
                "source_domain": ev.source_domain,
                "source_type": ev.source_type,
                "source_tier": ev.source_tier,
                "publisher": ev.publisher,
                "raw_excerpt": ev.raw_excerpt,
                "evidence_category": ev.evidence_category,
                "confidence_score": ev.confidence_score,
                "source_quality_score": ev.source_quality_score,
                "freshness_score": ev.freshness_score,
                "is_verified": ev.is_verified,
                "http_status": getattr(ev, "http_status", 200),
                "content_hash": getattr(ev, "content_hash", None),
                "verification_status": getattr(ev, "verification_status", "VERIFIED" if ev.is_verified else "UNVERIFIED"),
                "verification_reason": getattr(ev, "verification_reason", None),
                "business_identity_match": getattr(ev, "business_identity_match", False),
                "source_independence_group": getattr(ev, "source_independence_group", ev.source_domain),
                "retrieved_at": ev.retrieved_at.isoformat() if ev.retrieved_at else None
            }
            for ev in evidence_items
        ],
        "gate_evaluation": gate_result.model_dump()
    }



@router.post("/evidence-gate/evaluate/{business_id}", response_model=Dict[str, Any])
async def evaluate_prospect_evidence_gate(
    business_id: int,
    session: AsyncSession = Depends(get_db)
):
    """
    On-demand re-evaluation of the ProspectEvidenceGate on a specific business.
    Applies gate status and commits state.
    """
    biz = await session.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found.")

    gate_result = await prospect_evidence_gate.evaluate_and_apply(session, biz)
    await session.commit()

    return {
        "business_id": biz.id,
        "verification_status": biz.verification_status,
        "research_status": biz.research_status,
        "pipeline_stage": biz.pipeline_stage,
        "evidence_count": biz.evidence_count,
        "effective_evidence_score": biz.effective_evidence_score,
        "gate_evaluation": gate_result.model_dump()
    }


@router.get("/runs", response_model=List[Dict[str, Any]])
async def list_discovery_runs(
    limit: int = 20,
    session: AsyncSession = Depends(get_db)
):
    """
    Lists recent discovery telemetry runs.
    """
    stmt = select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(limit)
    runs = list((await session.execute(stmt)).scalars().all())

    return [
        {
            "run_id": r.run_id,
            "country_code": r.country_code,
            "niche_slug": r.niche_slug,
            "status": r.status,
            "prospects_discovered": r.prospects_discovered,
            "prospects_verified": r.prospects_verified,
            "prospects_rejected": r.prospects_rejected,
            "evidence_items_extracted": r.evidence_items_extracted,
            "duration_seconds": r.duration_seconds,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None
        }
        for r in runs
    ]


@router.get("/top-candidate", response_model=Dict[str, Any])
async def get_top_prospect_candidate(
    session: AsyncSession = Depends(get_db)
):
    """
    Returns the current #1 ranked candidate from the global pool with full decision trace.
    """
    top = await global_ranker.get_top_candidate(session)
    if not top:
        return {"candidate": None, "message": "No uncontacted verified prospects in pool."}

    return {
        "candidate": top.model_dump()
    }

