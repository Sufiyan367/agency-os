from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.connection import get_db
from app.database.models import (
    CountryMarketProfile, NicheMarketProfile, CountryNicheOpportunity,
    MarketEvidence, MarketResearchRun
)
from app.market_intelligence.schemas import (
    CountryMarketProfileDTO, NicheMarketProfileDTO, CountryNicheOpportunityDTO,
    MarketEvidenceDTO, ResearchTriggerRequest
)
from app.market_intelligence.market_research_engine import market_research_engine
from app.market_intelligence.opportunity_queue import global_opportunity_queue
from app.market_intelligence.dynamic_discovery import dynamic_market_discovery
from app.core.logging import logger

router = APIRouter(prefix="/api/market-intelligence", tags=["Market Intelligence"])


@router.get("/countries", response_model=List[Dict[str, Any]])
async def list_country_profiles(session: AsyncSession = Depends(get_db)):
    """Lists all researched and candidate country market profiles."""
    await market_research_engine.ensure_seed_universe(session)
    stmt = select(CountryMarketProfile).order_by(CountryMarketProfile.country_name)
    profiles = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": p.id,
            "country_code": p.country_code,
            "country_name": p.country_name,
            "region": p.region,
            "currency": p.currency,
            "timezone": p.timezone,
            "primary_languages": p.primary_languages,
            "compliance_risk_signal": p.compliance_risk_signal,
            "research_status": p.research_status,
            "confidence": p.confidence,
            "research_timestamp": p.research_timestamp.isoformat() if p.research_timestamp else None
        }
        for p in profiles
    ]


@router.get("/countries/{country_code}")
async def get_country_profile(country_code: str, session: AsyncSession = Depends(get_db)):
    """Fetches complete intelligence profile for a specific country."""
    stmt = select(CountryMarketProfile).where(CountryMarketProfile.country_code == country_code.upper())
    profile = (await session.execute(stmt)).scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Country profile {country_code} not found.")
    return profile


@router.get("/niches", response_model=List[Dict[str, Any]])
async def list_niche_profiles(session: AsyncSession = Depends(get_db)):
    """Lists all researched industry niches and their economic parameters."""
    await market_research_engine.ensure_seed_universe(session)
    stmt = select(NicheMarketProfile).order_by(NicheMarketProfile.name)
    niches = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": n.id,
            "niche_slug": n.niche_slug,
            "name": n.name,
            "category": n.category,
            "typical_lead_value_usd": n.typical_lead_value_usd,
            "missed_lead_pain_severity": n.missed_lead_pain_severity,
            "automation_potential": n.automation_potential,
            "baseline_ability_to_pay": n.baseline_ability_to_pay,
            "suitable_services": n.suitable_services,
            "research_status": n.research_status
        }
        for n in niches
    ]


@router.get("/opportunities", response_model=List[Dict[str, Any]])
async def list_opportunities(
    country_code: Optional[str] = Query(None),
    niche_slug: Optional[str] = Query(None),
    service_id: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    limit: int = Query(50, le=200),
    session: AsyncSession = Depends(get_db)
):
    """Returns ranked Country x Niche x Service market opportunities."""
    opps = await global_opportunity_queue.get_ranked_queue(
        session=session,
        limit=limit,
        country_code=country_code,
        niche_slug=niche_slug,
        service_id=service_id,
        min_score=min_score
    )
    return [
        {
            "id": o.id,
            "country_code": o.country_code,
            "niche_slug": o.niche_slug,
            "service_id": o.service_id,
            "opportunity_key": o.opportunity_key,
            "market_score": o.market_score,
            "demand_score": o.demand_score,
            "ability_to_pay_score": o.ability_to_pay_score,
            "automation_score": o.automation_score,
            "expected_deal_value_usd": o.expected_deal_value_usd,
            "p_contact": o.p_contact,
            "p_fit": o.p_fit,
            "p_deal": o.p_deal,
            "expected_value_usd": o.expected_value_usd,
            "confidence": o.confidence,
            "research_status": o.research_status,
            "evidence_count": o.evidence_count,
            "freshest_evidence_at": o.freshest_evidence_at.isoformat() if o.freshest_evidence_at else None,
            "updated_at": o.updated_at.isoformat() if o.updated_at else None
        }
        for o in opps
    ]


@router.get("/top")
async def get_top_opportunities(limit: int = Query(5, le=20), session: AsyncSession = Depends(get_db)):
    """Returns the top highest-EV market opportunities feeding commercial prospecting."""
    opps = await global_opportunity_queue.get_ranked_queue(session=session, limit=limit)
    return opps


@router.get("/opportunities/{opp_id}")
async def get_opportunity_detail(opp_id: int, session: AsyncSession = Depends(get_db)):
    """Fetches full details including decision trace for an opportunity."""
    stmt = select(CountryNicheOpportunity).where(CountryNicheOpportunity.id == opp_id)
    opp = (await session.execute(stmt)).scalars().first()
    if not opp:
        raise HTTPException(status_code=404, detail=f"Opportunity #{opp_id} not found.")
    return opp


@router.get("/evidence/{opp_id}", response_model=List[Dict[str, Any]])
async def get_opportunity_evidence(opp_id: int, session: AsyncSession = Depends(get_db)):
    """Retrieves all stored empirical evidence items supporting an opportunity."""
    stmt = select(CountryNicheOpportunity).where(CountryNicheOpportunity.id == opp_id)
    opp = (await session.execute(stmt)).scalars().first()
    if not opp:
        raise HTTPException(status_code=404, detail=f"Opportunity #{opp_id} not found.")

    ev_stmt = select(MarketEvidence).where(
        MarketEvidence.country_code == opp.country_code,
        MarketEvidence.niche_slug.in_([opp.niche_slug, None])
    ).order_by(MarketEvidence.confidence_score.desc())

    evidence_list = (await session.execute(ev_stmt)).scalars().all()
    return [
        {
            "id": e.id,
            "evidence_id": e.evidence_id,
            "claim": e.claim,
            "source_url": e.source_url,
            "source_domain": e.source_domain,
            "source_type": e.source_type,
            "source_tier": e.source_tier,
            "publisher": e.publisher,
            "publication_date": e.publication_date.isoformat() if e.publication_date else None,
            "retrieved_at": e.retrieved_at.isoformat(),
            "raw_excerpt": e.raw_excerpt,
            "signal_type": e.signal_type,
            "source_quality_score": e.source_quality_score,
            "freshness_score": e.freshness_score,
            "confidence_score": e.confidence_score,
            "supports_claim": e.supports_claim
        }
        for e in evidence_list
    ]


@router.get("/decision-trace/{opp_id}")
async def get_opportunity_decision_trace(opp_id: int, session: AsyncSession = Depends(get_db)):
    """Fetches explainable 5-point decision trace for an opportunity."""
    stmt = select(CountryNicheOpportunity).where(CountryNicheOpportunity.id == opp_id)
    opp = (await session.execute(stmt)).scalars().first()
    if not opp:
        raise HTTPException(status_code=404, detail=f"Opportunity #{opp_id} not found.")
    return {
        "opportunity_id": opp.id,
        "opportunity_key": opp.opportunity_key,
        "decision_trace": opp.decision_trace,
        "scoring_weights": opp.scoring_weights
    }


@router.post("/research/opportunity/{opp_id}")
async def trigger_opportunity_research(opp_id: int, session: AsyncSession = Depends(get_db)):
    """Triggers a fresh real research cycle for a specific opportunity."""
    stmt = select(CountryNicheOpportunity).where(CountryNicheOpportunity.id == opp_id)
    opp = (await session.execute(stmt)).scalars().first()
    if not opp:
        raise HTTPException(status_code=404, detail=f"Opportunity #{opp_id} not found.")

    refreshed = await market_research_engine.research_opportunity(
        session=session,
        country_code=opp.country_code,
        niche_slug=opp.niche_slug,
        service_id=opp.service_id,
        force_refresh=True
    )
    return refreshed


@router.post("/research/country/{country_code}")
async def trigger_country_research(country_code: str, session: AsyncSession = Depends(get_db)):
    """Researches key niches and services for a given country."""
    c = country_code.upper()
    opps = []
    for niche in ["roofing", "hvac", "dental", "real-estate"]:
        for s in ["SERVICE_001", "SERVICE_003"]:
            opp = await market_research_engine.research_opportunity(session, c, niche, s, force_refresh=True)
            opps.append(opp)
    return {"country_code": c, "opportunities_scored": len(opps), "status": "COMPLETED"}


@router.post("/research/refresh")
async def trigger_batch_research_refresh(
    req: ResearchTriggerRequest = None,
    session: AsyncSession = Depends(get_db)
):
    """Triggers comprehensive multi-country market intelligence batch run."""
    force = req.force_refresh if req else False
    res = await market_research_engine.run_full_refresh(session=session, force=force)
    return res


@router.post("/discover/candidates")
async def discover_new_candidates(session: AsyncSession = Depends(get_db)):
    """Discovers and registers new high-potential candidate countries and niches."""
    new_countries = await dynamic_market_discovery.discover_new_candidate_markets(session)
    new_niches = await dynamic_market_discovery.discover_new_candidate_niches(session)
    await session.commit()
    return {
        "new_countries": [c["code"] for c in new_countries],
        "new_niches": [n["slug"] for n in new_niches],
        "total_new_candidates": len(new_countries) + len(new_niches)
    }


@router.post("/feed-phase10")
async def feed_phase10_acquisition(
    top_n: int = Query(3, le=10),
    target_per_country: int = Query(2, le=5),
    session: AsyncSession = Depends(get_db)
):
    """Feeds top ranked market intelligence opportunities into Phase 10 real prospect discovery."""
    discovered_prospects = await global_opportunity_queue.feed_phase10_pool(
        session=session,
        top_n=top_n,
        target_per_country=target_per_country
    )
    return {
        "top_opportunities_targeted": top_n,
        "new_prospects_discovered": len(discovered_prospects),
        "prospect_domains": [b.domain for b in discovered_prospects],
        "commercial_outreach_concurrency_lock": 1
    }

