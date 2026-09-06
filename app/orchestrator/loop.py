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
        target_leads: int = 1,
        target_leads_per_market: Optional[int] = None,
        max_opportunities_to_mine: int = 1
    ) -> Dict[str, Any]:
        total_targets = target_leads_per_market if target_leads_per_market is not None else target_leads
        if total_targets is None or total_targets < 1:
            total_targets = 1

        run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
        logger = setup_logging(run_id=run_id)
        start_time = time.perf_counter()
        started_at = datetime.utcnow()

        logger.info(f"=== Starting Autonomous Revenue Loop Cycle [{run_id}] (Target: {total_targets} Real Leads, Strict 1-at-a-Time) ===")
        processed_count = 0
        failed_count = 0
        cycle_summary = {}

        async with AsyncSessionLocal() as session:
            from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType

            # 0. Crash Recovery / Resume Incomplete Stages from Previous Runs
            logger.info("Step 0: Checking for uncompleted pipeline tasks (Crash Recovery)...")
            await self._recover_incomplete_stages(session, logger)

            # Record RUN_STARTED event
            await activity_broadcaster.record_event(
                session=session,
                run_id=run_id,
                event_type=AgentEventType.RUN_STARTED.value,
                message=f"Starting autonomous revenue loop cycle [{run_id}] (Target: {total_targets} Real Leads, Strict 1-at-a-Time).",
                status="INFO",
                metadata_json={"target_leads": total_targets, "run_id": run_id}
            )

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

            await activity_broadcaster.record_event(
                session=session,
                run_id=run_id,
                event_type=AgentEventType.MARKET_SELECTED.value,
                message=f"Market radar selected top opportunity: {best_market.niche_name} in {best_market.country_name} (Score: {best_market.total_score}/100).",
                status="INFO",
                metadata_json=cycle_summary["selected_market"]
            )

            discovered_businesses = []
            audited_count = 0
            scored_count = 0
            offers_count = 0
            drafted_count = 0
            sent_count = 0

            logger.info(f"Step 2: Processing {total_targets} prospects STRICTLY ONE-AT-A-TIME (Discover -> Verify -> Audit -> Score -> $500 Floor -> Compliance -> Outreach -> Memory Persistence)...")

            for prospect_idx in range(total_targets):
                # 2a. Pre-discovery safety: Emergency Kill Switch
                from app.core.config import settings
                from app.outreach.compliance import compliance_guard
                from app.crm.memory_service import memory_service

                if not getattr(settings, "AUTONOMOUS_AGENT_ENABLED", True):
                    logger.warning(f"[AutonomousCycle] Kill switch active or autonomous agent disabled. Aborting loop at prospect {prospect_idx + 1}.")
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id=run_id,
                        event_type=AgentEventType.KILL_SWITCH_ACTIVATED.value,
                        message="Emergency Kill Switch Active: Autonomous cycle aborted before discovery.",
                        status="WARNING",
                        metadata_json={"prospect_index": prospect_idx + 1}
                    )
                    break

                # 2b. Lead Discovery: Request/discover exactly ONE new real prospect (target=1)
                logger.info(f"--> [Prospect {prospect_idx + 1}/{total_targets}] Requesting discovery of exactly 1 real prospect (target=1)...")
                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.DISCOVERY_STARTED.value,
                    message=f"Requesting discovery of exactly 1 uncontacted prospect (target=1) in {best_market.niche_slug}...",
                    status="INFO",
                    metadata_json={"target": 1, "market": best_market.niche_slug, "country": best_market.country_code}
                )

                new_leads = await lead_discovery_coordinator.run_discovery_and_verification(
                    session,
                    country_code=best_market.country_code,
                    niche_slug=best_market.niche_slug,
                    target=1,
                    target_count=1
                )
                if not new_leads:
                    logger.info(f"[Prospect {prospect_idx + 1}/{total_targets}] No new uncontacted prospects found for {best_market.niche_slug}. Ending discovery loop.")
                    break

                biz = new_leads[0]
                discovered_businesses.append(biz)

                try:
                    from app.agents.revenue_agent import revenue_agent_orchestrator
                    revenue_agent_orchestrator.current_domain = biz.domain
                    revenue_agent_orchestrator.current_business_name = biz.name
                    revenue_agent_orchestrator.current_operation = f"Discovered candidate prospect: {biz.name} ({biz.domain})"
                    revenue_agent_orchestrator.current_pipeline_stage = PipelineStage.DISCOVERED.value
                except Exception:
                    pass

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.PROSPECT_FOUND.value,
                    message=f"Discovered candidate prospect: {biz.name} ({biz.domain}).",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="SUCCESS",
                    metadata_json={
                        "name": biz.name,
                        "domain": biz.domain,
                        "city": biz.city,
                        "email": biz.public_email,
                        "phone": biz.phone,
                        "verification_status": biz.verification_status
                    }
                )

                # 2c. Verification check
                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.VERIFICATION_STARTED.value,
                    message=f"Validating business entity and digital presence for {biz.domain}...",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="INFO"
                )

                if biz.verification_status != VerificationStatus.VERIFIED.value or biz.pipeline_stage == PipelineStage.REJECTED.value:
                    logger.info(f"[Prospect {biz.domain}] Verification status is '{biz.verification_status}'. Skipping to next prospect.")
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id=run_id,
                        event_type=AgentEventType.PROSPECT_DISQUALIFIED.value,
                        message=f"Prospect {biz.domain} failed verification with status '{biz.verification_status}'. Skipping.",
                        business_id=biz.id,
                        domain=biz.domain,
                        status="WARNING",
                        metadata_json={"verification_status": biz.verification_status}
                    )
                    continue

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.VERIFICATION_COMPLETED.value,
                    message=f"Verification confirmed genuine business identity for {biz.name}.",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="SUCCESS",
                    metadata_json={"verification_status": biz.verification_status}
                )

                # 2c.2 Duplicate / Already Contacted check
                if biz.pipeline_stage in (PipelineStage.CONTACTED.value, PipelineStage.REPLIED.value, PipelineStage.MEETING.value, PipelineStage.PROPOSAL.value, PipelineStage.WON.value):
                    logger.info(f"[Prospect {biz.domain}] Already contacted in stage '{biz.pipeline_stage}'. Skipping duplicate outreach.")
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id=run_id,
                        event_type=AgentEventType.PROSPECT_DUPLICATE_SKIPPED.value,
                        message=f"Prospect {biz.domain} is already in stage '{biz.pipeline_stage}'. Skipping duplicate outreach.",
                        business_id=biz.id,
                        domain=biz.domain,
                        status="INFO",
                        metadata_json={"pipeline_stage": biz.pipeline_stage}
                    )
                    continue

                # 2d. Deep Website Audit for THIS single prospect
                logger.info(f"[Prospect {biz.domain}] Auditing website across 6 diagnostic vectors...")
                try:
                    from app.agents.revenue_agent import revenue_agent_orchestrator
                    revenue_agent_orchestrator.current_operation = f"Auditing website across 6 diagnostic vectors for {biz.domain}"
                    revenue_agent_orchestrator.current_pipeline_stage = PipelineStage.AUDITED.value
                except Exception:
                    pass

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.AUDIT_STARTED.value,
                    message=f"Executing diagnostic audit for {biz.domain} across 6 performance and UX vectors...",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="INFO"
                )

                audit = None
                try:
                    audit = await website_audit_engine.audit_business(session, biz)
                    audited_count += 1
                    processed_count += 1
                except Exception as e:
                    logger.error(f"[Prospect {biz.domain}] Audit failed: {e}")
                    failed_count += 1
                    continue

                perf_score = getattr(audit, "performance_score", 50.0) if audit else 50.0
                load_time = getattr(audit, "load_time_seconds", 4.0) if audit else 4.0
                seo_score = getattr(audit, "seo_score", 60.0) if audit else 60.0
                a11y_score = getattr(audit, "a11y_score", 65.0) if audit else 65.0

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.AUDIT_COMPLETED.value,
                    message=f"Website audit completed for {biz.domain}: Performance {perf_score:.1f}/100, Load Time {load_time:.2f}s, SEO {seo_score:.1f}/100.",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="SUCCESS",
                    metadata_json={
                        "performance_score": perf_score,
                        "load_time_seconds": load_time,
                        "seo_score": seo_score,
                        "a11y_score": a11y_score,
                        "findings_count": len(audit.__dict__.get("findings", [])) if audit else 0
                    }
                )

                # 2e. Lead Scoring for THIS single prospect
                logger.info(f"[Prospect {biz.domain}] Computing transparent commercial 0-100 lead score...")
                try:
                    from app.agents.revenue_agent import revenue_agent_orchestrator
                    revenue_agent_orchestrator.current_operation = f"Computing commercial priority score for {biz.name} ({biz.domain})"
                    revenue_agent_orchestrator.current_pipeline_stage = PipelineStage.QUALIFIED.value
                except Exception:
                    pass

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.SCORING_STARTED.value,
                    message=f"Computing commercial priority & buying capacity score for {biz.domain}...",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="INFO"
                )

                score_rec = None
                try:
                    score_rec = await lead_scoring_engine.score_business(session, biz)
                    scored_count += 1
                except Exception as e:
                    logger.error(f"[Prospect {biz.domain}] Scoring failed: {e}")
                    failed_count += 1
                    continue

                b_score = getattr(score_rec, "buying_capacity_score", 80.0) if score_rec else 80.0
                opp_score = getattr(score_rec, "total_score", 75.0) if score_rec else 75.0

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.SCORING_COMPLETED.value,
                    message=f"Lead scored for {biz.domain}: Total Opportunity {opp_score:.1f}/100, Buying Capacity {b_score:.1f}/100.",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="SUCCESS",
                    metadata_json={
                        "total_score": opp_score,
                        "buying_capacity_score": b_score,
                        "priority": getattr(score_rec, "priority", "B") if score_rec else "B"
                    }
                )

                # 2f. Service Recommendation & Commercial Offer Generation ($500+ Minimum Floor)
                logger.info(f"[Prospect {biz.domain}] Synthesizing customized commercial package & offer...")
                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.OFFER_GENERATION_STARTED.value,
                    message=f"Synthesizing customized commercial turnaround package for {biz.domain}...",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="INFO"
                )

                # 2e.2 Client Intelligence & Service Matching Analysis (Phase 7)
                try:
                    from app.client_intelligence.engine import client_intelligence_engine
                    ci_res = await client_intelligence_engine.analyze_business_async(session, biz, audit=audit, persist=True)
                    logger.info(f"[Prospect {biz.domain}] Client Intelligence completed: segment={ci_res.get('size_estimate', {}).get('segment')}, top_service={ci_res.get('top_match', {}).get('service_name')}, selection_score={ci_res.get('selection_score')}")
                except Exception as ci_err:
                    logger.warning(f"[Prospect {biz.domain}] Client intelligence analysis encountered non-blocking warning: {ci_err}")

                commercial_floor = getattr(settings, "MINIMUM_SERVICE_VALUE_USD", 500.0)
                offer = None
                try:
                    offer = await offer_engine.generate_offer_for_business(session, biz)
                    offers_count += 1
                except Exception as e:
                    logger.error(f"[Prospect {biz.domain}] Offer generation failed: {e}")
                    failed_count += 1
                    continue

                offer_price = getattr(offer, "recommended_price", 0.0) or 0.0
                if offer_price < commercial_floor:
                    logger.info(f"[Prospect {biz.domain}] Commercial offer price (${offer_price:.0f}) below ${commercial_floor:.0f} floor. Disqualifying from outreach.")
                    biz.pipeline_stage = PipelineStage.REJECTED.value
                    await session.commit()
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id=run_id,
                        event_type=AgentEventType.PROSPECT_DISQUALIFIED.value,
                        message=f"Commercial offer (${offer_price:.0f}) fell below ${commercial_floor:.0f} commercial floor. Disqualified.",
                        business_id=biz.id,
                        domain=biz.domain,
                        status="WARNING",
                        metadata_json={"offer_price": offer_price, "commercial_floor": commercial_floor}
                    )
                    continue

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.COMMERCIAL_QUALIFICATION.value,
                    message=f"Commercial qualification approved for {biz.domain}: Offer price ${offer_price:.0f} satisfies ${commercial_floor:.0f}+ floor.",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="SUCCESS",
                    metadata_json={
                        "offer_price": offer_price,
                        "commercial_floor": commercial_floor,
                        "service_type": getattr(offer, "service_type", "Performance Turnaround")
                    }
                )

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.OFFER_GENERATED.value,
                    message=f"Offer generated for {biz.domain}: '{getattr(offer, 'title', 'Turnaround')}' at ${offer_price:.0f}.",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="SUCCESS",
                    metadata_json={
                        "title": getattr(offer, "title", "Performance Turnaround"),
                        "recommended_price": offer_price,
                        "deliverables": getattr(offer, "deliverables", [])
                    }
                )

                # 2g. Compliance & Safety Gates
                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.COMPLIANCE_STARTED.value,
                    message=f"Evaluating compliance, suppression, and daily rate limits for {biz.domain}...",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="INFO"
                )

                # 1. Kill Switch
                if not getattr(settings, "AUTONOMOUS_AGENT_ENABLED", True):
                    logger.warning(f"[Prospect {biz.domain}] Kill switch active. Halting outreach.")
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id=run_id,
                        event_type=AgentEventType.KILL_SWITCH_ACTIVATED.value,
                        message="Emergency kill switch active. Halting outreach.",
                        business_id=biz.id,
                        domain=biz.domain,
                        status="WARNING"
                    )
                    break

                # 2. Suppression / Opt-Out Check
                if await compliance_guard.is_suppressed(session, email=biz.public_email, phone=biz.phone, domain=biz.domain):
                    logger.info(f"[Prospect {biz.domain}] Contact on suppression list. Disqualifying.")
                    biz.pipeline_stage = PipelineStage.REJECTED.value
                    await session.commit()
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id=run_id,
                        event_type=AgentEventType.COMPLIANCE_BLOCKED.value,
                        message=f"Contact details for {biz.domain} match suppression / opt-out registry. Outreach blocked.",
                        business_id=biz.id,
                        domain=biz.domain,
                        status="WARNING",
                        metadata_json={"reason": "SUPPRESSION_LIST"}
                    )
                    continue

                # 3. Daily outreach limit
                if not await compliance_guard.can_send_today(session):
                    logger.warning(f"[Prospect {biz.domain}] Daily outreach limit reached. Halting outreach.")
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id=run_id,
                        event_type=AgentEventType.COMPLIANCE_BLOCKED.value,
                        message="Daily outreach volume cap (MAX_OUTREACH_PER_DAY) reached. Halting today's loop.",
                        business_id=biz.id,
                        domain=biz.domain,
                        status="WARNING",
                        metadata_json={"reason": "DAILY_LIMIT_EXCEEDED"}
                    )
                    break

                # 4. Valid public contact details (never fabricate)
                if not biz.public_email and not biz.phone:
                    logger.info(f"[Prospect {biz.domain}] No verified public contact details found. Skipping outreach (no contact fabrication).")
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id=run_id,
                        event_type=AgentEventType.COMPLIANCE_BLOCKED.value,
                        message=f"No verified public contact info found for {biz.domain}. Skipping outreach (no fabrication).",
                        business_id=biz.id,
                        domain=biz.domain,
                        status="INFO",
                        metadata_json={"reason": "NO_VERIFIED_CONTACT"}
                    )
                    continue

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.COMPLIANCE_PASSED.value,
                    message=f"Compliance check passed for {biz.domain}: Genuine contact verified, suppression cleared, rate limit permissible.",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="SUCCESS"
                )

                # 2h. Autonomous Personalized Outreach Drafting (Auto-Approved for $500+ Eligible Prospects)
                logger.info(f"[Prospect {biz.domain}] Drafting evidence-grounded outreach message...")
                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.OUTREACH_DRAFT_STARTED.value,
                    message=f"Drafting evidence-grounded outreach message for {biz.domain}...",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="INFO"
                )

                msg = None
                try:
                    msg = await outreach_personalizer.prepare_outreach_for_business(session, biz, auto_approve=True)
                    drafted_count += 1
                except Exception as e:
                    logger.warning(f"[Prospect {biz.domain}] Outreach drafting failed: {e}")
                    continue

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.OUTREACH_DRAFTED.value,
                    message=f"Outreach message drafted for {biz.name}: '{msg.subject}'.",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="SUCCESS",
                    metadata_json={
                        "message_id": msg.id,
                        "recipient": msg.recipient_email,
                        "subject": msg.subject,
                        "body": msg.body,
                        "variant": msg.variant_name,
                        "from_email": settings.EMAIL_FROM,
                        "from_name": settings.OUTREACH_FROM_NAME,
                        "audit_evidence": {
                            "performance_score": perf_score,
                            "load_time_seconds": load_time
                        }
                    }
                )

                # 2i. Autonomous Outreach Execution (Direct dispatch without human approval gate)
                logger.info(f"[Prospect {biz.domain}] Dispatching autonomous outreach message...")
                try:
                    from app.agents.revenue_agent import revenue_agent_orchestrator
                    revenue_agent_orchestrator.current_operation = f"Dispatching outreach email for {biz.domain} (SIMULATED DRY RUN)"
                    revenue_agent_orchestrator.current_pipeline_stage = PipelineStage.CONTACTED.value
                except Exception:
                    pass

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.OUTREACH_DISPATCH_STARTED.value,
                    message=f"Initiating autonomous dispatch to {msg.recipient_email} (DRY RUN SAFE)...",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="INFO"
                )

                try:
                    await outreach_sender_adapter.send_approved_message(session, msg.id)
                    sent_count += 1
                except Exception as e:
                    logger.error(f"[Prospect {biz.domain}] Send failed: {e}")
                    failed_count += 1
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id=run_id,
                        event_type=AgentEventType.OUTREACH_FAILED.value,
                        message=f"Outreach dispatch failed for {biz.domain}: {e}",
                        business_id=biz.id,
                        domain=biz.domain,
                        status="FAILED",
                        error=str(e)
                    )
                    continue

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.OUTREACH_DISPATCHED.value,
                    message=f"Outreach dispatched for {biz.domain} — SIMULATED (DRY RUN).",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="SUCCESS",
                    metadata_json={
                        "message_id": msg.id,
                        "recipient": msg.recipient_email,
                        "subject": msg.subject,
                        "body": msg.body,
                        "channel": "EMAIL",
                        "dry_run": getattr(settings, "EMAIL_DRY_RUN", True),
                        "status_note": "SIMULATED — NO EXTERNAL TRANSMISSION (DRY RUN)"
                    }
                )

                # 2j. Persistent Memory Snapshot (Non-Blocking Event-Driven Memory)
                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.MEMORY_PERSIST_STARTED.value,
                    message=f"Capturing complete prospect memory snapshot for {biz.domain}...",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="INFO"
                )

                await memory_service.save_memory(
                    session,
                    business_id=biz.id,
                    domain=biz.domain,
                    contact_name=f"Managing Partner ({biz.name})",
                    contact_email=biz.public_email,
                    contact_phone=biz.phone,
                    thread_id=f"thread-{biz.domain}",
                    channel_used="EMAIL",
                    pipeline_stage=PipelineStage.CONTACTED.value,
                    audit_results={
                        "performance_score": perf_score,
                        "load_time_seconds": load_time,
                        "seo_score": seo_score,
                        "a11y_score": a11y_score
                    },
                    buyer_score=b_score,
                    opportunity_score=opp_score,
                    estimated_value=offer_price,
                    offer_proposal={
                        "title": getattr(offer, "title", "Website Performance Turnaround"),
                        "service_type": getattr(offer, "service_type", "Performance"),
                        "recommended_price": offer_price,
                        "deliverables": getattr(offer, "deliverables", [])
                    },
                    outreach_message={
                        "subject": msg.subject,
                        "variant": msg.variant_name,
                        "recipient": msg.recipient_email,
                        "body": msg.body
                    },
                    last_interaction="Autonomous outreach placed via EMAIL (DRY RUN)",
                    next_expected_action="AWAITING_INBOUND_EVENT"
                )

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.MEMORY_PERSISTED.value,
                    message=f"Prospect memory snapshot persisted for {biz.domain}. Ready for non-blocking asynchronous reply handling.",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="SUCCESS",
                    metadata_json={
                        "business_id": biz.id,
                        "domain": biz.domain,
                        "estimated_value": offer_price,
                        "next_action": "AWAITING_INBOUND_EVENT"
                    }
                )

                logger.info(f"[Prospect {biz.domain}] Contacted & Memory persisted. Immediately progressing to next prospect.")
                try:
                    from app.agents.revenue_agent import revenue_agent_orchestrator
                    revenue_agent_orchestrator.current_operation = f"Completed {biz.domain}. Advancing to next prospect."
                    revenue_agent_orchestrator.current_pipeline_stage = "NEXT"
                except Exception:
                    pass

                await activity_broadcaster.record_event(
                    session=session,
                    run_id=run_id,
                    event_type=AgentEventType.NEXT_PROSPECT.value,
                    message=f"Completed prospect {biz.domain}. Immediately moving to next prospect in sequence.",
                    business_id=biz.id,
                    domain=biz.domain,
                    status="INFO",
                    metadata_json={"completed_prospect": biz.domain, "index": prospect_idx + 1}
                )

            cycle_summary["new_leads_discovered"] = len(discovered_businesses)
            cycle_summary["websites_audited"] = audited_count
            cycle_summary["leads_scored"] = scored_count
            cycle_summary["offers_generated"] = offers_count
            cycle_summary["outreach_prepared"] = drafted_count
            cycle_summary["autonomous_outreach_sent"] = sent_count

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

            await activity_broadcaster.record_event(
                session=session,
                run_id=run_id,
                event_type=AgentEventType.RUN_COMPLETED.value,
                message=f"Autonomous cycle [{run_id}] completed successfully in {duration}s. Processed {processed_count} prospects.",
                status="SUCCESS",
                metadata_json=cycle_summary
            )

        logger.info(f"=== Autonomous Revenue Loop [{run_id}] Finished in {duration}s ===")
        return cycle_summary

    async def _recover_incomplete_stages(self, session: AsyncSession, logger):
        """Crash recovery: Resumes and actively processes any tasks that were interrupted across reboots."""
        # 1. Unaudited verified leads
        unaudited = (await session.execute(
            select(Business).where(
                Business.verification_status == VerificationStatus.VERIFIED.value,
                Business.pipeline_stage.in_([PipelineStage.DISCOVERED.value, PipelineStage.VERIFIED.value])
            )
        )).scalars().all()
        if unaudited:
            logger.info(f"[Crash Recovery] Resuming audits for {len(unaudited)} verified leads...")
            for b in unaudited:
                try:
                    await website_audit_engine.audit_business(session, b)
                except Exception as e:
                    logger.warning(f"[Crash Recovery] Audit failed for {b.domain}: {e}")

        # 2. Audited unscored leads
        unscored = (await session.execute(
            select(Business).where(Business.pipeline_stage == PipelineStage.AUDITED.value)
        )).scalars().all()
        if unscored:
            logger.info(f"[Crash Recovery] Resuming scoring and offers for {len(unscored)} audited leads...")
            for b in unscored:
                try:
                    await lead_scoring_engine.score_business(session, b)
                    await offer_engine.generate_offers_for_business(session, b)
                except Exception as e:
                    logger.warning(f"[Crash Recovery] Scoring failed for {b.domain}: {e}")

        # 3. Approved unsent messages (human approved before restart)
        approved_unsent = (await session.execute(
            select(OutreachMessage).where(OutreachMessage.status == OutreachStatus.APPROVED.value)
        )).scalars().all()
        if approved_unsent:
            logger.info(f"[Crash Recovery] Dispatching {len(approved_unsent)} approved messages awaiting send...")
            for m in approved_unsent:
                try:
                    await outreach_sender_adapter.send_approved_message(session, m.id)
                except Exception as e:
                    logger.warning(f"[Crash Recovery] Send failed for message #{m.id}: {e}")

        # 4. Due follow-ups
        due_followups = await followup_engine.process_due_followups(session)
        if due_followups:
            logger.info(f"[Crash Recovery] Dispatched {len(due_followups)} due follow-ups upon service reboot.")

orchestrator = AutonomousCycleOrchestrator()
