import asyncio
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from uuid import uuid4
from app.acquisition.models import StandardizedProspect
from app.acquisition.config import country_config_manager
from app.acquisition.pipeline import CountryPipeline
from app.acquisition.evidence_gate import prospect_evidence_gate
from app.acquisition.evidence_harvester import evidence_harvester
from app.database.models import (
    Business, Contact, PipelineStage, VerificationStatus, PipelineEvent, AuditRun, ClientIntelligenceRecord, ProspectEvidence
)
from app.auditing.engine import website_audit_engine
from app.client_intelligence.engine import client_intelligence_engine
from app.crm.memory_service import memory_service
from app.core.security import normalize_domain
from app.core.logging import logger


class GlobalProspectPool:
    """
    Coordinates global multi-country prospect acquisition, parallel auditing,
    and client intelligence enrichment with global domain deduplication.
    """

    async def discover_across_countries(
        self,
        session: AsyncSession,
        countries: Optional[List[str]] = None,
        target_per_country: int = 3,
        niche: Optional[str] = None
    ) -> List[Business]:
        """
        Executes parallel prospect discovery across all specified (or enabled) countries.
        Deduplicates globally across countries and database records, persisting new businesses.
        """
        # 1. Resolve enabled countries
        all_configs = await country_config_manager.list_countries(session)
        target_countries = [c.upper() for c in (countries or [])]
        
        active_configs = [
            cfg for cfg in all_configs
            if cfg.enabled and (not target_countries or cfg.country_code.upper() in target_countries)
        ]

        if not active_configs:
            logger.warning("[GlobalProspectPool] No active countries configured for discovery.")
            return []

        # 2. Query all existing domains from DB for global deduplication
        existing_domains_stmt = select(Business.domain)
        existing_res = await session.execute(existing_domains_stmt)
        known_domains: Set[str] = set(existing_res.scalars().all())

        # 3. Launch parallel country discovery pipelines
        tasks = []
        for cfg in active_configs:
            pipeline = CountryPipeline(cfg)
            tasks.append(
                pipeline.run_discovery(
                    target_count=target_per_country,
                    niche=niche,
                    exclude_domains=set(known_domains)
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_discovered: List[StandardizedProspect] = []
        for idx, res in enumerate(results):
            cfg = active_configs[idx]
            if isinstance(res, Exception):
                logger.error(f"[GlobalProspectPool] Country {cfg.country_code} discovery failed: {res}")
            elif isinstance(res, list):
                all_discovered.extend(res)

        logger.info(f"[GlobalProspectPool] Collected {len(all_discovered)} candidates from {len(active_configs)} countries.")

        # 4. Global deduplication across all country outputs
        created_businesses: List[Business] = []
        for p in all_discovered:
            norm_dom = normalize_domain(p.domain)
            if not norm_dom or norm_dom in known_domains:
                continue
            known_domains.add(norm_dom)

            biz = Business(
                name=p.business_name,
                domain=norm_dom,
                website_url=p.website,
                country=p.country.upper(),
                city=p.city,
                niche=p.niche,
                public_email=p.public_email,
                email_status="verified" if p.public_email and p.confidence > 0.8 else "unknown",
                phone=p.public_phone,
                source=p.discovery_source,
                verification_status="INSUFFICIENT_EVIDENCE",
                research_status="RESEARCH_REQUIRED",
                pipeline_stage=PipelineStage.DISCOVERED.value,
                evidence_count=0,
                effective_evidence_score=0.0
            )
            session.add(biz)
            await session.flush()

            # Harvest Multi-Source Empirical Evidence via safe fetcher and identity matching
            ev_items, gate_res = await evidence_harvester.harvest_and_verify(session, biz, p)

            # Multi-vector verification status assignment
            if gate_res.is_passed:
                biz.verification_status = VerificationStatus.VERIFIED.value
                biz.research_status = "VERIFIED"
                biz.pipeline_stage = PipelineStage.VERIFIED.value
            elif p.verification_status == "VERIFIED":
                biz.verification_status = VerificationStatus.VERIFIED.value
                biz.research_status = "RESEARCH_REQUIRED"
                biz.pipeline_stage = PipelineStage.VERIFIED.value
            else:
                biz.verification_status = "INSUFFICIENT_EVIDENCE"
                biz.research_status = "RESEARCH_REQUIRED"
                biz.pipeline_stage = PipelineStage.DISCOVERED.value


            # Create Contact if public email available
            if p.public_email:
                contact = Contact(
                    business_id=biz.id,
                    name=f"Managing Partner ({p.business_name})",
                    title="General Manager / Owner",
                    email=p.public_email,
                    phone=p.public_phone,
                    email_status="verified" if p.confidence > 0.8 else "unknown",
                    source=p.discovery_source,
                    whatsapp_eligible=False,
                    whatsapp_consent_status="INELIGIBLE_NO_CONSENT",
                    whatsapp_status_reason="Public phone without opt-in consent"
                )
                session.add(contact)

            # Record Pipeline Event
            event = PipelineEvent(
                business_id=biz.id,
                from_stage=PipelineStage.DISCOVERED.value,
                to_stage=biz.pipeline_stage,
                deal_value=0.0,
                note=f"Discovered via global pipeline ({p.country}). Verification status: {biz.verification_status}."
            )
            session.add(event)

            # Create Memory
            try:
                await memory_service.get_or_create_memory(
                    session,
                    business_id=biz.id,
                    domain=biz.domain,
                    business_name=biz.name
                )
            except Exception as e:
                logger.debug(f"[GlobalProspectPool] Memory creation warning for {biz.domain}: {e}")

            created_businesses.append(biz)

        await session.commit()
        logger.info(f"[GlobalProspectPool] Successfully saved {len(created_businesses)} new global businesses.")
        return created_businesses

    async def enrich_and_audit_prospects(
        self,
        session: AsyncSession,
        businesses: Optional[List[Business]] = None,
        max_concurrency: int = 4
    ) -> List[Business]:
        """
        Conducts website audit and client intelligence analysis on un-audited or supplied businesses.
        Runs with bounded concurrency to protect network and database resources.
        """
        targets = businesses
        if targets is None:
            # Query businesses that need auditing (verified but not yet fully audited or qualified)
            stmt = select(Business).where(
                Business.verification_status == VerificationStatus.VERIFIED.value,
                Business.pipeline_stage.in_([PipelineStage.DISCOVERED.value, PipelineStage.VERIFIED.value])
            ).limit(20)
            res = await session.execute(stmt)
            targets = list(res.scalars().all())

        if not targets:
            logger.info("[GlobalProspectPool] No businesses require auditing.")
            return []

        logger.info(f"[GlobalProspectPool] Enriching and auditing {len(targets)} businesses (concurrency={max_concurrency})...")
        sem = asyncio.Semaphore(max_concurrency)

        async def _process_single(biz: Business):
            async with sem:
                try:
                    # 1. Audit website if not already present
                    audit_stmt = select(AuditRun).where(AuditRun.business_id == biz.id).options(selectinload(AuditRun.findings))
                    audit_res = await session.execute(audit_stmt)
                    audit = audit_res.scalar_one_or_none()

                    if not audit:
                        audit = await website_audit_engine.audit_business(session, biz)
                        audit_stmt = select(AuditRun).where(AuditRun.id == audit.id).options(selectinload(AuditRun.findings))
                        audit = (await session.execute(audit_stmt)).scalar_one()

                    biz = await session.get(Business, biz.id)

                    # 2. Run client intelligence profiling and service matching
                    await client_intelligence_engine.analyze_business_async(
                        session=session,
                        business=biz,
                        audit=audit,
                        persist=True
                    )

                    # Advance stage to AUDITED or QUALIFIED
                    if biz.pipeline_stage in [PipelineStage.DISCOVERED.value, PipelineStage.VERIFIED.value]:
                        biz.pipeline_stage = PipelineStage.AUDITED.value
                        session.add(biz)
                        event = PipelineEvent(
                            business_id=biz.id,
                            from_stage=PipelineStage.VERIFIED.value,
                            to_stage=PipelineStage.AUDITED.value,
                            deal_value=0.0,
                            note="Completed automated 6-vector audit and client intelligence profiling."
                        )
                        session.add(event)
                except Exception as e:
                    logger.warning(f"[GlobalProspectPool] Audit/Enrichment failed for {biz.domain}: {e}")

        for b in targets:
            await _process_single(b)

        await session.commit()
        return targets

    async def get_pool_status(self, session: AsyncSession) -> Dict[str, Any]:
        """Returns aggregated summary metrics of the global prospect pool."""
        total_stmt = select(func.count(Business.id))
        total = (await session.execute(total_stmt)).scalar() or 0

        by_country_stmt = select(Business.country, func.count(Business.id)).group_by(Business.country)
        country_counts = dict((await session.execute(by_country_stmt)).all())

        by_stage_stmt = select(Business.pipeline_stage, func.count(Business.id)).group_by(Business.pipeline_stage)
        stage_counts = dict((await session.execute(by_stage_stmt)).all())

        return {
            "total_prospects": total,
            "by_country": country_counts,
            "by_stage": stage_counts,
            "uncontacted_ready": stage_counts.get(PipelineStage.AUDITED.value, 0) + stage_counts.get(PipelineStage.VERIFIED.value, 0)
        }

    async def get_uncontacted_candidates(
        self,
        session: AsyncSession,
        limit: int = 50
    ) -> List[Business]:
        """
        Retrieves verified businesses that are eligible for ranking and outreach,
        excluding prospects that are already contacted, won, lost, opted-out, or rejected.
        """
        excluded_stages = [
            PipelineStage.CONTACTED.value,
            PipelineStage.REPLIED.value,
            PipelineStage.MEETING.value,
            PipelineStage.PROPOSAL.value,
            PipelineStage.WON.value,
            PipelineStage.LOST.value,
            PipelineStage.REJECTED.value,
        ]

        stmt = select(Business).where(
            Business.verification_status == VerificationStatus.VERIFIED.value,
            Business.verification_status != "INSUFFICIENT_EVIDENCE",
            Business.research_status != "INSUFFICIENT_EVIDENCE",
            ~Business.pipeline_stage.in_(excluded_stages)
        ).order_by(Business.created_at.desc()).limit(limit)



        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def discover_from_top_market_opportunities(
        self,
        session: AsyncSession,
        top_n: int = 3,
        target_per_country: int = 2
    ) -> List[Business]:
        """
        Feeds top-ranked Country x Niche opportunities from Phase 11 Market Intelligence
        directly into Phase 10 prospect discovery with global deduplication.
        """
        from app.market_intelligence.opportunity_queue import global_opportunity_queue
        return await global_opportunity_queue.feed_phase10_pool(
            session=session,
            top_n=top_n,
            target_per_country=target_per_country
        )

global_prospect_pool = GlobalProspectPool()
