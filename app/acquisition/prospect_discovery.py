import asyncio
import time
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Business, ProspectEvidence, DiscoveryRun, PipelineStage, VerificationStatus
from app.acquisition.models import StandardizedProspect
from app.acquisition.providers.registry import discovery_registry
from app.acquisition.evidence_gate import prospect_evidence_gate, GateEvaluationResult
from app.acquisition.evidence_harvester import evidence_harvester
from app.lead_generation.adapters.real_web_discovery import EXPANDED_CITIES
from app.core.security import normalize_domain, is_safe_url
from app.core.logging import logger

class RealProspectDiscoveryEngine:
    """
    Orchestrates real public web prospect acquisition with multi-city geographic spread,
    multi-source empirical evidence harvesting, and hard evidence gate enforcement.
    """

    async def discover_prospects_for_market(
        self,
        session: AsyncSession,
        country_code: str,
        niche_slug: str,
        target_count: int = 5,
        cities: Optional[List[str]] = None,
        exclude_domains: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        """
        Executes verified prospect discovery for a specific Country x Niche,
        harvests multi-source evidence, enforces the ProspectEvidenceGate,
        and logs execution telemetry.
        """
        start_time = time.time()
        c_code = country_code.upper()
        run_id = f"run_disc_{uuid4().hex[:10]}"
        
        # Target cities for multi-city geographic spread
        target_cities = cities or EXPANDED_CITIES.get(c_code, ["Metropolitan Area", "Commercial District"])
        excluded = set(exclude_domains or [])

        # Fetch existing domains in DB to prevent duplicates
        existing_stmt = select(Business.domain)
        res = await session.execute(existing_stmt)
        for dom in res.scalars().all():
            if dom:
                excluded.add(dom.lower().strip())

        # Initialize telemetry run
        disc_run = DiscoveryRun(
            run_id=run_id,
            country_code=c_code,
            niche_slug=niche_slug,
            status="RUNNING",
            started_at=datetime.utcnow()
        )
        session.add(disc_run)
        await session.flush()

        logger.info(f"[RealProspectDiscoveryEngine] Starting run {run_id} for {c_code} x {niche_slug} across {len(target_cities)} cities.")

        total_discovered = 0
        total_verified = 0
        total_insufficient = 0
        total_evidence_extracted = 0
        created_businesses: List[Business] = []

        try:
            # 1. Execute discovery via registry
            raw_prospects: List[StandardizedProspect] = await discovery_registry.execute_discovery_with_fallback(
                country_code=c_code,
                niche=niche_slug,
                limit=target_count,
                cities=target_cities,
                exclude_domains=set(excluded)
            )

            total_discovered = len(raw_prospects)

            # 2. Process each discovered prospect
            for p in raw_prospects:
                norm_dom = normalize_domain(p.domain)
                if not norm_dom or norm_dom in excluded:
                    continue

                # Verify domain URL health and safety
                is_safe, reason = is_safe_url(p.website)
                if not is_safe:
                    logger.warning(f"[RealProspectDiscoveryEngine] Domain {norm_dom} website {p.website} failed SSRF/safety check: {reason}")
                    total_insufficient += 1
                    continue

                excluded.add(norm_dom)

                # Create Business record (initially INSUFFICIENT_EVIDENCE / RESEARCH_REQUIRED)
                biz = Business(
                    name=p.business_name,
                    domain=norm_dom,
                    website_url=p.website,
                    country=c_code,
                    city=p.city or (target_cities[0] if target_cities else None),
                    niche=niche_slug,
                    public_email=p.public_email,
                    email_status="verified" if p.public_email and p.confidence > 0.8 else "unknown",
                    phone=p.public_phone,
                    source=p.discovery_source or "real_web",
                    verification_status="INSUFFICIENT_EVIDENCE",
                    research_status="RESEARCH_REQUIRED",
                    pipeline_stage=PipelineStage.DISCOVERED.value,
                    evidence_count=0,
                    effective_evidence_score=0.0
                )
                session.add(biz)
                await session.flush()

                # Harvest Multi-Source Empirical Evidence via safe fetcher and identity matching
                evidence_items, gate_result = await evidence_harvester.harvest_and_verify(session, biz, p)
                total_evidence_extracted += len(evidence_items)

                if gate_result.is_passed:
                    total_verified += 1
                    try:
                        from app.auditing.engine import website_audit_engine
                        await website_audit_engine.audit_business(session, biz)
                    except Exception as audit_err:
                        logger.warning(f"[RealProspectDiscoveryEngine] Website audit for {biz.domain} skipped or failed: {audit_err}")
                else:
                    total_insufficient += 1

                created_businesses.append(biz)

            # Update telemetry record
            elapsed = round(time.time() - start_time, 2)
            disc_run.status = "COMPLETED"
            disc_run.prospects_discovered = total_discovered
            disc_run.prospects_verified = total_verified
            disc_run.prospects_rejected = total_insufficient
            disc_run.evidence_items_extracted = total_evidence_extracted
            disc_run.duration_seconds = elapsed
            disc_run.completed_at = datetime.utcnow()
            disc_run.metadata_json = {
                "cities": target_cities,
                "created_business_ids": [b.id for b in created_businesses]
            }
            session.add(disc_run)
            await session.commit()

            logger.info(f"[RealProspectDiscoveryEngine] Completed run {run_id}: Discovered={total_discovered}, Verified={total_verified}, Insufficient={total_insufficient}, Evidence={total_evidence_extracted} in {elapsed}s.")

            return {
                "run_id": run_id,
                "status": "COMPLETED",
                "country_code": c_code,
                "niche_slug": niche_slug,
                "prospects_discovered": total_discovered,
                "prospects_verified": total_verified,
                "prospects_rejected": total_insufficient,
                "evidence_items_extracted": total_evidence_extracted,
                "duration_seconds": elapsed,
                "businesses": [
                    {
                        "id": b.id,
                        "name": b.name,
                        "domain": b.domain,
                        "country": b.country,
                        "city": b.city,
                        "status": b.verification_status,
                        "evidence_count": b.evidence_count,
                        "effective_evidence_score": b.effective_evidence_score
                    }
                    for b in created_businesses
                ]
            }

        except Exception as e:
            await session.rollback()
            elapsed = round(time.time() - start_time, 2)
            disc_run.status = "FAILED"
            disc_run.error_message = str(e)
            disc_run.duration_seconds = elapsed
            disc_run.completed_at = datetime.utcnow()
            session.add(disc_run)
            await session.commit()
            logger.error(f"[RealProspectDiscoveryEngine] Discovery run {run_id} failed: {e}")
            raise e

real_prospect_discovery_engine = RealProspectDiscoveryEngine()
