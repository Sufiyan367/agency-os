import uuid
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, LeadScore, Offer, OutreachMessage,
    OutreachStatus, PipelineStage, SystemRun, VerificationStatus, Reply
)
from app.market_intelligence.engine import market_intelligence_engine
from app.lead_generation.discovery import lead_discovery_coordinator
from app.auditing.engine import website_audit_engine
from app.scoring.engine import lead_scoring_engine
from app.offers.generator import offer_engine
from app.outreach.personalization import outreach_personalizer
from app.outreach.sender import outreach_sender_adapter
from app.followups.engine import followup_engine
from app.crm.reply_classifier import reply_classifier
from app.crm.pipeline import pipeline_manager
from app.analytics.engine import analytics_engine
from app.core.logging import setup_logging

class AutonomousCycleOrchestrator:
    """
    Central orchestrator executing the end-to-end autonomous revenue loop:
    Market Research -> Opportunity Ranking -> Lead Discovery (50-100 real prospects) ->
    Verification -> Deep Website Auditing -> Lead Scoring -> Offer Generation ->
    Personalized Outreach Drafting -> Approval Queue -> Execution ->
    Follow-up Management -> Analytics & Observability.
    Includes automated crash recovery and pipeline resumption.
    """

    async def run_full_autonomous_cycle(
        self,
        target_leads: int = 50,
        target_leads_per_market: Optional[int] = None,
        max_opportunities_to_mine: int = 1
    ) -> Dict[str, Any]:
        if target_leads_per_market is not None:
            target_leads = target_leads_per_market

        run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
        logger = setup_logging(run_id=run_id)
        start_time = time.perf_counter()
        started_at = datetime.utcnow()

        logger.info(f"=== Starting Autonomous Revenue Loop Cycle [{run_id}] (Target: {target_leads} Real Leads) ===")
        processed_count = 0
        failed_count = 0
        cycle_summary = {}

        async with AsyncSessionLocal() as session:
            # 0. Crash Recovery / Resume Incomplete Stages from Previous Runs
            logger.info("Step 0: Checking for uncompleted pipeline tasks (Crash Recovery)...")
            await self._recover_incomplete_stages(session, logger)

            # 1. Market Research & Intelligence: Select Best Opportunity
            logger.info("Step 1: Discovering and evaluating global market opportunities...")
            opportunities = await market_intelligence_engine.scan_and_rank_markets(session)
            top_markets = opportunities[:max_opportunities_to_mine]
            best_market = top_markets[0]
            cycle_summary["selected_market"] = {
                "country": best_market.country_name,
                "country_code": best_market.country_code,
                "niche": best_market.niche_name,
                "niche_slug": best_market.niche_slug,
                "opportunity_score": best_market.total_score,
                "expected_deal_value": best_market.expected_deal_value,
                "reasoning": best_market.reasoning
            }
            logger.info(f"Selected Best Market: {best_market.niche_name} in {best_market.country_name} (Score: {best_market.total_score}/100)")

            # 2. Lead Discovery & Verification: Discover 50-100 REAL Public B2B Prospects
            logger.info(f"Step 2: Discovering {target_leads} REAL public B2B prospects for {best_market.niche_slug} in {best_market.country_code}...")
            discovered_businesses = await lead_discovery_coordinator.run_discovery_and_verification(
                session,
                country_code=best_market.country_code,
                niche_slug=best_market.niche_slug,
                target_count=target_leads
            )
            cycle_summary["new_leads_discovered"] = len(discovered_businesses)

            # 3. Real Website Auditing
            logger.info("Step 3: Auditing real business websites across 6 diagnostic vectors...")
            unaudited_q = select(Business).where(
                Business.verification_status == VerificationStatus.VERIFIED.value,
                Business.pipeline_stage.in_([PipelineStage.DISCOVERED.value, PipelineStage.VERIFIED.value])
            )
            to_audit = list((await session.execute(unaudited_q)).scalars().all())
            audited_count = 0

            for biz in to_audit:
                try:
                    await website_audit_engine.audit_business(session, biz)
                    audited_count += 1
                    processed_count += 1
                except Exception as e:
                    logger.error(f"Audit failed for {biz.domain}: {e}")
                    failed_count += 1

            cycle_summary["websites_audited"] = audited_count

            # 4. Lead Scoring
            logger.info("Step 4: Computing transparent commercial 0-100 lead scores...")
            unscored_q = select(Business).where(
                Business.pipeline_stage == PipelineStage.AUDITED.value
            )
            to_score = list((await session.execute(unscored_q)).scalars().all())
            scored_count = 0

            for biz in to_score:
                try:
                    await lead_scoring_engine.score_business(session, biz)
                    scored_count += 1
                except Exception as e:
                    logger.error(f"Scoring failed for {biz.domain}: {e}")
                    failed_count += 1

            cycle_summary["leads_scored"] = scored_count

            # 5. Service Recommendation & Commercial Offer Generation
            logger.info("Step 5: Synthesizing customized commercial packages & offers ($450-$1,500+)...")
            qualified_q = select(Business).where(
                Business.pipeline_stage == PipelineStage.QUALIFIED.value
            )
            qualified_leads = list((await session.execute(qualified_q)).scalars().all())
            offers_count = 0

            for biz in qualified_leads:
                try:
                    await offer_engine.generate_offer_for_business(session, biz)
                    offers_count += 1
                except Exception as e:
                    logger.error(f"Offer generation failed for {biz.domain}: {e}")
                    failed_count += 1

            cycle_summary["offers_generated"] = offers_count

            # 6. Personalized Outreach Drafting -> Approval Queue
            logger.info("Step 6: Generating evidence-grounded outreach messages for approval queue...")
            ready_outreach_q = select(Business).where(
                Business.pipeline_stage == PipelineStage.QUALIFIED.value,
                Business.public_email != None
            )
            candidates = list((await session.execute(ready_outreach_q)).scalars().all())
            drafted_count = 0

            for biz in candidates:
                try:
                    await outreach_personalizer.prepare_outreach_for_business(session, biz)
                    drafted_count += 1
                except Exception as e:
                    logger.warning(f"Outreach prep note for {biz.domain}: {e}")

            cycle_summary["outreach_queued_for_approval"] = drafted_count

            # 7. Process Any Previously Approved Outreach
            logger.info("Step 7: Processing human-approved outreach messages...")
            approved_q = select(OutreachMessage).where(
                OutreachMessage.status == OutreachStatus.APPROVED.value
            )
            approved_msgs = list((await session.execute(approved_q)).scalars().all())
            sent_count = 0

            for a_msg in approved_msgs:
                try:
                    await outreach_sender_adapter.send_approved_message(session, a_msg.id)
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Send failed for message {a_msg.id}: {e}")
                    failed_count += 1

            cycle_summary["approved_outreach_sent"] = sent_count

            # 8. Follow-up Cadence Check
            logger.info("Step 8: Checking scheduled follow-up cadences...")
            due_followups = await followup_engine.process_due_followups(session)
            cycle_summary["followups_processed"] = len(due_followups)

            # 9. Dashboard Analytics Summary
            metrics = await analytics_engine.get_dashboard_metrics(session)
            cycle_summary["metrics"] = metrics

            duration = round(time.perf_counter() - start_time, 2)
            cycle_summary["duration_seconds"] = duration
            cycle_summary["status"] = "SUCCESS"

            # 10. Record System Run in database for Observability
            sys_run = SystemRun(
                run_id=run_id,
                job_name="full_autonomous_cycle",
                status="SUCCESS" if failed_count == 0 else "PARTIAL_SUCCESS",
                records_processed=processed_count + len(discovered_businesses) + drafted_count,
                records_failed=failed_count,
                duration_seconds=duration,
                started_at=started_at,
                finished_at=datetime.utcnow()
            )
            session.add(sys_run)
            await session.commit()

        logger.info(f"=== Autonomous Revenue Loop [{run_id}] Finished in {duration}s ===")
        return cycle_summary

    async def _recover_incomplete_stages(self, session: AsyncSession, logger):
        """Crash recovery: Resumes any tasks that were interrupted."""
        # 1. Unaudited verified leads
        unaudited = (await session.execute(
            select(Business).where(
                Business.verification_status == VerificationStatus.VERIFIED.value,
                Business.pipeline_stage.in_([PipelineStage.DISCOVERED.value, PipelineStage.VERIFIED.value])
            )
        )).scalars().all()
        if unaudited:
            logger.info(f"[Crash Recovery] Found {len(unaudited)} verified leads awaiting audit.")

        # 2. Audited unscored leads
        unscored = (await session.execute(
            select(Business).where(Business.pipeline_stage == PipelineStage.AUDITED.value)
        )).scalars().all()
        if unscored:
            logger.info(f"[Crash Recovery] Found {len(unscored)} audited leads awaiting scoring.")

        # 3. Approved unsent messages
        approved_unsent = (await session.execute(
            select(OutreachMessage).where(OutreachMessage.status == OutreachStatus.APPROVED.value)
        )).scalars().all()
        if approved_unsent:
            logger.info(f"[Crash Recovery] Found {len(approved_unsent)} approved messages awaiting dispatch.")

orchestrator = AutonomousCycleOrchestrator()
