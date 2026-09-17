import asyncio
from datetime import datetime
import uuid
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.connection import AsyncSessionLocal
from app.database.models import (
    SystemRun, Business, PipelineStage, PipelineEvent, OutreachMessage, OutreachStatus,
    Reply, ReplyClassification, FollowupStatus, CustomerProject, ProjectStatus
)
from app.crm.inbox_poller import inbox_poller
from app.crm.attention_engine import attention_engine
from app.campaigns.sender_registry import sender_registry
from app.outreach.sender import outreach_sender_adapter
from app.outreach.personalization import outreach_personalizer
from app.auditing.engine import website_audit_engine
from app.scoring.engine import lead_scoring_engine
from app.offers.generator import offer_engine
from app.followups.engine import followup_engine
from app.payments.provider import stripe_payment_provider, get_active_payment_provider
from app.payments.service import payment_service
from app.orchestrator.loop import orchestrator
from app.core.config import settings
from app.core.logging import logger

class PersistentAgencyWorker:
    """
    Persistent background autonomous worker and scheduler.
    Runs unattended cycles, polls prospect replies, executes scheduled follow-up cadences,
    enforces rate limits, and logs operational heartbeats.
    """

    def __init__(self, interval_seconds: Optional[int] = None):
        if interval_seconds is not None:
            self.interval_seconds = interval_seconds
        else:
            self.interval_seconds = getattr(settings, "WORKER_TICK_INTERVAL_SECONDS", None) or getattr(settings, "INBOX_POLL_INTERVAL_SECONDS", 60)
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.last_tick_at: Optional[datetime] = None
        self.last_cycle_at: Optional[datetime] = None
        self.ticks_executed = 0

    async def start(self):
        """Starts the persistent background loop."""
        if self.is_running:
            return
        self.is_running = True
        logger.info(f"[PersistentWorker] Starting autonomous background worker (Tick interval: {self.interval_seconds}s)...")
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Signals the worker to shut down gracefully."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[PersistentWorker] Autonomous background worker stopped gracefully.")

    async def _run_loop(self):
        while self.is_running:
            try:
                await self.execute_tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PersistentWorker] Unhandled tick error: {e}", exc_info=True)

            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    async def execute_tick(self) -> Dict[str, Any]:
        """Executes one single worker pass across all routine jobs."""
        tick_id = f"TICK-{uuid.uuid4().hex[:8].upper()}"
        start_time = datetime.utcnow()
        summary = {
            "tick_id": tick_id,
            "started_at": start_time.isoformat(),
            "inbox_replies_processed": 0,
            "followups_dispatched": 0,
            "autonomous_cycle_run": False,
            "status": "SUCCESS"
        }

        async with AsyncSessionLocal() as session:
            run_record = SystemRun(
                run_id=tick_id,
                job_name="worker_tick",
                status="RUNNING",
                started_at=start_time
            )
            session.add(run_record)
            await session.commit()

            try:
                # Job 1: Inbound Reply Polling (CONTINUOUS) & Response Loop Processing
                replies = await inbox_poller.poll_inbox(session)
                summary["inbox_replies_processed"] = len(replies)

                # Process all unhandled replies in the database
                unhandled_stmt = select(Reply).where(Reply.is_handled == False).order_by(Reply.received_at.asc())
                unhandled_replies = (await session.execute(unhandled_stmt)).scalars().all()
                for reply in unhandled_replies:
                    try:
                        cat = getattr(reply, "classification", "") or "UNCLEAR"
                        cat_upper = cat.upper()

                        if cat_upper in ("INTERESTED", "POSITIVE", "MEETING_REQUEST", "PRICE_REQUEST", "DEMO_REQUEST"):
                            from app.builder.pipeline import pipeline_orchestrator
                            from app.core.event_bus import event_bus, AgencyEvent
                            from app.database.models import PipelineEvent

                            biz = await session.get(Business, reply.business_id)
                            if biz:
                                old_stage = biz.pipeline_stage
                                new_stage = (
                                    PipelineStage.DEMO_REQUESTED.value
                                    if cat_upper == "DEMO_REQUEST"
                                    else PipelineStage.QUALIFIED_REPLY.value
                                )
                                biz.pipeline_stage = new_stage
                                pipe_event = PipelineEvent(
                                    business_id=biz.id,
                                    from_stage=old_stage,
                                    to_stage=new_stage,
                                    deal_value=0.0,
                                    note=f"Worker processed {cat_upper} reply from {reply.sender_email}"
                                )
                                session.add(pipe_event)
                                await session.commit()

                                # Stop pending follow-ups immediately upon receiving positive/interested reply
                                await followup_engine.cancel_pending_followups(session, reply.business_id, FollowupStatus.CANCELLED_REPLY)

                                # Requirement #6 Invariant: Demos are NOT generated automatically upon reply.
                                # Require client conversation and requirements gathering first.
                                if cat_upper == "DEMO_REQUEST":
                                    reply.suggested_response = (
                                        f"Hi there,\n\nThanks for reaching out! We would be happy to prepare a tailored demonstration "
                                        f"for {biz.name or biz.domain}. To ensure the preview addresses your exact workflow requirements, "
                                        f"could you share what key processes you are looking to automate, or are you open to a quick 10-minute discovery call?"
                                    )
                                else:
                                    reply.suggested_response = (
                                        f"Hi there,\n\nGreat to hear from you! We would love to discuss how Agency OS can streamline operations "
                                        f"for {biz.name or biz.domain}. Would you have 10 minutes this week for a brief conversation to explore your requirements?"
                                    )

                                # Publish high-priority POSITIVE_REPLY event to event bus for CEO notification
                                try:
                                    await event_bus.publish(AgencyEvent(
                                        event_type="POSITIVE_REPLY",
                                        entity_type="business",
                                        entity_id=biz.id,
                                        payload={
                                            "business_name": biz.name or biz.domain,
                                            "prospect_name": biz.name or biz.domain,
                                            "intent": cat_upper,
                                            "next_action": "Requirements Gathering Required (Collect Requirements Before Building Demo)",
                                            "reply_body": reply.raw_body
                                        }
                                    ))
                                except Exception as eb_err:
                                    logger.error(f"[PersistentWorker] Failed to publish POSITIVE_REPLY event: {eb_err}")

                            logger.info(
                                f"[PersistentWorker] Advanced pipeline to {new_stage} for {cat_upper} reply from biz #{reply.business_id}. "
                                f"Demo generation held until explicit client requirements and CEO trigger."
                            )
                        elif cat_upper in ("NOT_INTERESTED", "NEGATIVE", "UNSUBSCRIBE"):
                            await followup_engine.cancel_pending_followups(session, reply.business_id, FollowupStatus.CANCELLED_UNSUB)
                            biz = await session.get(Business, reply.business_id)
                            if biz:
                                biz.pipeline_stage = PipelineStage.LOST.value
                            logger.info(f"[PersistentWorker] Marked biz #{reply.business_id} as LOST for {cat_upper} reply.")
                        elif cat_upper == "BOUNCE":
                            await followup_engine.cancel_pending_followups(session, reply.business_id, FollowupStatus.CANCELLED_UNSUB)
                            biz = await session.get(Business, reply.business_id)
                            if biz:
                                biz.pipeline_stage = PipelineStage.DEAD.value
                            logger.info(f"[PersistentWorker] Marked biz #{reply.business_id} as DEAD for BOUNCE.")
                        elif cat_upper == "QUESTION":
                            await followup_engine.cancel_pending_followups(session, reply.business_id, FollowupStatus.CANCELLED_REPLY)
                            biz = await session.get(Business, reply.business_id)
                            if biz:
                                biz.pipeline_stage = PipelineStage.REPLIED.value
                            logger.info(f"[PersistentWorker] Marked biz #{reply.business_id} as REPLIED for QUESTION (awaiting human response).")

                        reply.is_handled = True
                        await session.commit()
                    except Exception as rep_err:
                        logger.error(
                            f"[PersistentWorker] Failed to process reply #{getattr(reply, 'id', None)}: {rep_err}"
                        )
                        await session.rollback()

                # Job 1a: Capacity-Governed Auto-Approval Gate (Deterministic Quality & Compliance Verification)
                summary["auto_approved_count"] = 0
                if getattr(settings, "AUTONOMOUS_OUTREACH", False) and getattr(settings, "AUTO_APPROVAL_ENABLED", True) and not getattr(settings, "EMERGENCY_STOP", False):
                    from app.outreach.auto_approval import auto_approval_engine
                    try:
                        auto_appr_summary = await auto_approval_engine.scan_and_auto_approve_pending(session)
                        summary["auto_approved_count"] = auto_appr_summary.get("auto_approved_count", 0)
                        if summary["auto_approved_count"] > 0:
                            logger.info(f"[PersistentWorker] Auto-approved {summary['auto_approved_count']} qualified messages passing all 14 safety gates.")
                    except Exception as appr_err:
                        logger.error(f"[PersistentWorker] Auto-approval evaluation error: {appr_err}")

                # Job 1b: Capacity-Governed Approved & Queued Processing (DISPATCH)
                summary["approved_queue_processed"] = 0
                summary["approved_queue_deferred"] = 0
                if getattr(settings, "AUTONOMOUS_OUTREACH", True) and not getattr(settings, "EMERGENCY_STOP", False):
                    cap_summary = await sender_registry.get_sender_capacity_summary(session)
                    available_cap = cap_summary.get("available_capacity", 0)
                    approved_stmt = (
                        select(OutreachMessage)
                        .where(
                            OutreachMessage.status.in_([
                                OutreachStatus.OUTREACH_QUEUED.value,
                                OutreachStatus.APPROVED.value,
                                OutreachStatus.SEND_ATTEMPTED.value
                            ])
                        )
                        .order_by(OutreachMessage.created_at.asc())
                    )
                    approved_msgs = (await session.execute(approved_stmt)).scalars().all()

                    if available_cap > 0 and approved_msgs:
                        to_send = approved_msgs[:available_cap]
                        for msg in to_send:
                            try:
                                sent_ok = await outreach_sender_adapter.send_approved_message(session, msg.id)
                                if sent_ok:
                                    summary["approved_queue_processed"] += 1
                                    available_cap -= 1
                            except Exception as send_err:
                                logger.error(f"[PersistentWorker] Failed to dispatch queued/approved message #{msg.id}: {send_err}")
                                # Guarantee message does not remain indefinitely in in-flight transition state
                                if msg.status not in (OutreachStatus.OUTREACH_BLOCKED.value, OutreachStatus.SEND_FAILED.value, OutreachStatus.SENT.value):
                                    msg.status = OutreachStatus.SEND_FAILED.value
                                    await session.commit()
                        summary["approved_queue_deferred"] = len(approved_msgs) - summary["approved_queue_processed"]
                    else:
                        summary["approved_queue_deferred"] = len(approved_msgs)
                        if approved_msgs and available_cap <= 0:
                            logger.info(
                                f"[PersistentWorker] {len(approved_msgs)} approved/queued messages deferred: "
                                f"sender capacity exhausted for today ({cap_summary.get('rollout_stage_name')} cap: {cap_summary.get('rollout_daily_cap')}/day)."
                            )
                else:
                    logger.debug("[PersistentWorker] Autonomous outreach dispatch is paused by policy or emergency stop.")

                # Job 2: Process Due Follow-up Cadences (AUTOMATIC)
                followups = await followup_engine.process_due_followups(session)
                summary["followups_dispatched"] = len(followups)

                # Job 3: Payment Detection (AUTOMATIC) & Delivery (AUTOMATIC)
                completed_payments = []
                try:
                    active_pmt_provider = get_active_payment_provider()
                    if hasattr(active_pmt_provider, "fetch_completed_payments"):
                        completed_payments = await active_pmt_provider.fetch_completed_payments()
                except Exception as p_err:
                    logger.debug(f"[PersistentWorker] Payment detection skipped: {p_err}")
                summary["payments_detected"] = len(completed_payments)
                for pmt in completed_payments:
                    try:
                        await payment_service.confirm_payment_and_onboard(
                            session=session,
                            business_id=pmt["business_id"],
                            amount_usd=pmt["amount_usd"],
                            reference_id=pmt["reference_id"],
                            payer_email=pmt.get("customer_email")
                        )
                        logger.info(f"[PersistentWorker] Automatic payment detected and client onboarded: Ref {pmt.get('reference_id')}")
                    except Exception as pe:
                        logger.error(f"[PersistentWorker] Automatic delivery failed for payment {pmt.get('reference_id')}: {pe}")

                # Job 3b: Modular Pipeline Backlog Drainage (Per-Item Isolated Execution)
                audited_n = await self.drain_audit_backlog(session, limit=10)
                scored_n = await self.drain_scoring_backlog(session, limit=10)
                drafted_n = await self.drain_drafting_backlog(session, limit=10)
                summary["audited_backlog"] = audited_n
                summary["scored_backlog"] = scored_n
                summary["drafted_backlog"] = drafted_n

                # Job 3c: Autonomous Demo Build Backlog Drainage (Persistent & Idempotent)
                demos_n = await self.drain_demo_backlog(session, limit=5)
                summary["demos_built"] = demos_n

                # Job 3d: Autonomous Portfolio Maintenance & Rebalancing (Periodic or on tick intervals)
                if self.ticks_executed % 60 == 0:
                    try:
                        from app.market_intelligence.autonomous_market_engine import autonomous_market_engine
                        rebal_res = await autonomous_market_engine.rebalance_portfolio(session)
                        summary["portfolio_rebalanced"] = True
                        logger.info(f"[PersistentWorker] Autonomous portfolio maintenance rebalanced {len(rebal_res.get('active_portfolio', []))} markets.")
                    except Exception as rebal_err:
                        logger.debug(f"[PersistentWorker] Autonomous rebalance skipped: {rebal_err}")

                # Job 4: Lead Discovery (CONTINUOUS WORKER) & Audit/Scoring (AUTOMATIC) & Outreach (QUEUE + APPROVAL)
                cycle_interval_mins = settings.WORKER_CYCLE_INTERVAL_MINUTES
                should_run_cycle = False
                if getattr(settings, "AUTONOMOUS_AUTO_DISCOVERY", True):
                    if not self.last_cycle_at:
                        # Run on startup if uncontacted / actionable prospect volume is low (< 5 leads)
                        uncontacted_stmt = select(func.count(Business.id)).where(
                            Business.pipeline_stage.in_([
                                PipelineStage.DISCOVERED.value,
                                PipelineStage.VERIFIED.value,
                                PipelineStage.AUDITED.value,
                                PipelineStage.QUALIFIED.value,
                                PipelineStage.OUTREACH_READY.value,
                                PipelineStage.APPROVAL.value
                            ])
                        )
                        actionable_count = (await session.execute(uncontacted_stmt)).scalar() or 0
                        if actionable_count < 5:
                            should_run_cycle = True
                        else:
                            # Initialize last_cycle_at so timer runs cleanly
                            self.last_cycle_at = datetime.utcnow()
                    else:
                        elapsed_mins = (datetime.utcnow() - self.last_cycle_at).total_seconds() / 60.0
                        if elapsed_mins >= cycle_interval_mins:
                            should_run_cycle = True
                else:
                    logger.debug("[PersistentWorker] Unsolicited autonomous auto-discovery is disabled by policy (AUTONOMOUS_AUTO_DISCOVERY=False).")

                if should_run_cycle:
                    target_leads_n = min(getattr(settings, "CANARY_DAILY_LIMIT", 5), 5)
                    logger.info(f"[PersistentWorker] Triggering scheduled autonomous lead cycle (Target: {target_leads_n} leads)...")
                    cycle_res = await orchestrator.run_full_autonomous_cycle(
                        target_leads_per_market=target_leads_n, max_opportunities_to_mine=1
                    )
                    self.last_cycle_at = datetime.utcnow()
                    summary["autonomous_cycle_run"] = True
                    summary["cycle_summary"] = cycle_res

                # Job 5: Attention Engine Scan & Exception Escalation (AUTOMATIC)
                try:
                    attention_summary = await attention_engine.get_attention_feed(session)
                    summary["attention_status"] = attention_summary.get("overall_status", "ALL_CLEAR")
                    summary["high_priority_events"] = attention_summary.get("counts", {}).get("high_priority", 0)
                    summary["medium_priority_events"] = attention_summary.get("counts", {}).get("medium_priority", 0)
                    if attention_summary.get("overall_status") == "ATTENTION_REQUIRED":
                        logger.warning(
                            f"[PersistentWorker] ATTENTION REQUIRED: {summary['high_priority_events']} high-priority commercial events need CEO visibility."
                        )
                except Exception as att_err:
                    logger.error(f"[PersistentWorker] Failed to execute attention engine scan: {att_err}")

                run_record.status = "SUCCESS"
                run_record.records_processed = (
                    summary["inbox_replies_processed"]
                    + summary["followups_dispatched"]
                    + summary.get("approved_queue_processed", 0)
                    + summary.get("demos_built", 0)
                )
            except Exception as e:
                run_record.status = "FAILED"
                run_record.error_log = str(e)
                summary["status"] = "ERROR"
                summary["error"] = str(e)
                logger.error(f"[PersistentWorker] Tick {tick_id} failed: {e}")
            finally:
                finished_time = datetime.utcnow()
                run_record.finished_at = finished_time
                run_record.duration_seconds = (finished_time - start_time).total_seconds()
                await session.commit()

        self.last_tick_at = datetime.utcnow()
        self.ticks_executed += 1
        return summary

    async def drain_audit_backlog(self, session: AsyncSession, limit: int = 10) -> int:
        """Audits discovered/verified businesses with per-item isolation."""
        stmt = (
            select(Business.id)
            .where(
                Business.pipeline_stage.in_([PipelineStage.DISCOVERED.value, PipelineStage.VERIFIED.value]),
                ~Business.audits.any()
            )
            .order_by(Business.created_at.asc())
            .limit(limit)
        )
        prospect_ids = (await session.execute(stmt)).scalars().all()
        audited_count = 0
        for biz_id in prospect_ids:
            biz = await session.get(Business, biz_id)
            if not biz:
                continue
            domain_name = biz.domain
            try:
                await website_audit_engine.audit_business(session, biz)
                biz.pipeline_stage = PipelineStage.AUDITED.value
                await session.commit()
                audited_count += 1
                logger.info(f"[PersistentWorker:Audit] Successfully audited {biz.name} ({domain_name})")
            except Exception as e:
                logger.error(f"[PersistentWorker:Audit] Failed to audit {domain_name}: {e}")
                await session.rollback()
                try:
                    failed_biz = await session.get(Business, biz_id)
                    if failed_biz:
                        failed_biz.pipeline_stage = PipelineStage.REJECTED.value
                        session.add(PipelineEvent(
                            business_id=failed_biz.id,
                            from_stage=failed_biz.pipeline_stage,
                            to_stage=PipelineStage.REJECTED.value,
                            note=f"Audit failed: {str(e)[:200]}"
                        ))
                        await session.commit()
                except Exception as rec_err:
                    logger.error(f"[PersistentWorker:Audit] Could not record rejection for #{biz_id}: {rec_err}")
                    await session.rollback()
        return audited_count

    async def drain_scoring_backlog(self, session: AsyncSession, limit: int = 10) -> int:
        """Scores audited businesses and generates commercial packages with per-item isolation."""
        stmt = (
            select(Business.id)
            .where(
                Business.pipeline_stage == PipelineStage.AUDITED.value,
                ~Business.lead_score.has()
            )
            .order_by(Business.created_at.asc())
            .limit(limit)
        )
        prospect_ids = (await session.execute(stmt)).scalars().all()
        scored_count = 0
        commercial_floor = getattr(settings, "MINIMUM_SERVICE_VALUE_USD", 500.0)
        for biz_id in prospect_ids:
            biz = await session.get(Business, biz_id)
            if not biz:
                continue
            domain_name = biz.domain
            try:
                score = await lead_scoring_engine.score_business(session, biz)
                offer = await offer_engine.generate_offer_for_business(session, biz)
                price = getattr(offer, "recommended_price", 0.0) or 0.0
                # Enforce dual gate: score_business must qualify (score >= 55.0) AND price must meet commercial floor
                if biz.pipeline_stage == PipelineStage.QUALIFIED.value:
                    if price < commercial_floor:
                        biz.pipeline_stage = PipelineStage.REJECTED.value
                        session.add(PipelineEvent(
                            business_id=biz.id,
                            from_stage=PipelineStage.QUALIFIED.value,
                            to_stage=PipelineStage.REJECTED.value,
                            deal_value=0.0,
                            note=f"Disqualified: Offer price ${price:.2f} below commercial floor ${commercial_floor:.2f}."
                        ))
                await session.commit()
                scored_count += 1
                logger.info(f"[PersistentWorker:Score] Scored {domain_name} -> {biz.pipeline_stage} (${price:.0f})")
            except Exception as e:
                logger.error(f"[PersistentWorker:Score] Failed to score {domain_name}: {e}")
                await session.rollback()
                try:
                    failed_biz = await session.get(Business, biz_id)
                    if failed_biz:
                        failed_biz.pipeline_stage = PipelineStage.REJECTED.value
                        session.add(PipelineEvent(
                            business_id=failed_biz.id,
                            from_stage=failed_biz.pipeline_stage,
                            to_stage=PipelineStage.REJECTED.value,
                            note=f"Lead scoring failed: {str(e)[:200]}"
                        ))
                        await session.commit()
                except Exception as rec_err:
                    logger.error(f"[PersistentWorker:Score] Could not record rejection for #{biz_id}: {rec_err}")
                    await session.rollback()
        return scored_count

    async def drain_drafting_backlog(self, session: AsyncSession, limit: int = 10) -> int:
        """Drafts hyper-personalized outreach for qualified leads into PENDING_APPROVAL with per-item isolation."""
        stmt = (
            select(Business.id)
            .where(
                Business.pipeline_stage == PipelineStage.QUALIFIED.value,
                ~Business.outreach_messages.any()
            )
            .order_by(Business.created_at.asc())
            .limit(limit)
        )
        prospect_ids = (await session.execute(stmt)).scalars().all()
        drafted_count = 0
        for biz_id in prospect_ids:
            biz = await session.get(Business, biz_id)
            if not biz:
                continue
            domain_name = biz.domain
            try:
                # Cold outreach strictly requires human approval (auto_approve=False)
                msg = await outreach_personalizer.prepare_outreach_for_business(session, biz, auto_approve=False)
                biz.pipeline_stage = PipelineStage.APPROVAL.value
                await session.commit()
                drafted_count += 1
                logger.info(f"[PersistentWorker:Draft] Outreach draft #{msg.id} staged in PENDING_APPROVAL for {domain_name}")
            except Exception as e:
                logger.error(f"[PersistentWorker:Draft] Failed to draft outreach for {domain_name}: {e}")
                await session.rollback()
                try:
                    failed_biz = await session.get(Business, biz_id)
                    if failed_biz:
                        failed_biz.pipeline_stage = PipelineStage.REJECTED.value
                        session.add(PipelineEvent(
                            business_id=failed_biz.id,
                            from_stage=failed_biz.pipeline_stage,
                            to_stage=PipelineStage.REJECTED.value,
                            note=f"Outreach drafting failed: {str(e)[:200]}"
                        ))
                        await session.commit()
                except Exception as rec_err:
                    logger.error(f"[PersistentWorker:Draft] Could not record rejection for #{biz_id}: {rec_err}")
                    await session.rollback()
        return drafted_count

    async def drain_demo_backlog(self, session: AsyncSession, limit: int = 5) -> int:
        """
        Processes pending DEMO_REQUESTED build jobs autonomously.
        Ensures customer projects are loaded, specs generated, projects built, QA'd, repaired, and deployed.
        Survives worker restarts and executes idempotently.
        """
        from app.builder.pipeline import pipeline_orchestrator
        from app.delivery.demo_job_manager import DemoJobManager
        from app.database.models import DemoBuildJob

        # 1. First, check for businesses in DEMO_REQUESTED that need a CustomerProject and DemoBuildJob initialized
        biz_stmt = (
            select(Business.id)
            .where(
                Business.pipeline_stage == PipelineStage.DEMO_REQUESTED.value,
                ~Business.customer_projects.any()
            )
            .order_by(Business.created_at.asc())
            .limit(limit)
        )
        uninit_biz_ids = (await session.execute(biz_stmt)).scalars().all()
        for biz_id in uninit_biz_ids:
            try:
                await DemoJobManager.create_or_get_job(session, biz_id, force=True)
                await pipeline_orchestrator.get_or_create_project(session, biz_id)
                logger.info(f"[PersistentWorker:Demo] Created initial CustomerProject & DemoBuildJob for DEMO_REQUESTED biz #{biz_id}")
            except Exception as e:
                logger.error(f"[PersistentWorker:Demo] Failed to create project for biz #{biz_id}: {e}")
                await session.rollback()
                try:
                    failed_biz = await session.get(Business, biz_id)
                    if failed_biz:
                        failed_biz.pipeline_stage = PipelineStage.DEMO_BUILD_FAILED.value
                        session.add(PipelineEvent(
                            business_id=failed_biz.id,
                            from_stage=failed_biz.pipeline_stage,
                            to_stage=PipelineStage.DEMO_BUILD_FAILED.value,
                            note=f"Demo initialization failed: {str(e)[:200]}"
                        ))
                        await session.commit()
                except Exception as rec_err:
                    logger.error(f"[PersistentWorker:Demo] Could not record demo initialization failure for #{biz_id}: {rec_err}")
                    await session.rollback()

        # 2. Pick up pending customer projects in DEMO_REQUESTED or REQUESTED state
        proj_stmt = (
            select(CustomerProject)
            .where(
                CustomerProject.status.in_([
                    ProjectStatus.DEMO_REQUESTED.value,
                    ProjectStatus.REQUESTED.value
                ])
            )
            .order_by(CustomerProject.created_at.asc())
            .limit(limit)
        )
        pending_projects = (await session.execute(proj_stmt)).scalars().all()
        demos_completed = 0

        for project in pending_projects:
            pid = project.project_id
            try:
                logger.info(f"[PersistentWorker:Demo] Autonomously running demo build pipeline for {pid}...")
                res = await pipeline_orchestrator.run_pipeline(session, pid)
                if res.get("success"):
                    demos_completed += 1
                    logger.info(
                        f"[PersistentWorker:Demo] Successfully built demo {pid}: "
                        f"URL={res.get('demo_url')} QA={res.get('qa_score')}%"
                    )
                else:
                    logger.warning(
                        f"[PersistentWorker:Demo] Demo build for {pid} did not pass QA: {res.get('status')}"
                    )
            except Exception as pe:
                logger.error(f"[PersistentWorker:Demo] Error running pipeline for {pid}: {pe}", exc_info=True)
                await session.rollback()

        return demos_completed

    def get_status(self) -> Dict[str, Any]:
        """Returns the live worker operational status."""
        return {
            "is_running": self.is_running,
            "interval_seconds": self.interval_seconds,
            "ticks_executed": self.ticks_executed,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "last_cycle_at": self.last_cycle_at.isoformat() if self.last_cycle_at else None,
            "email_provider": settings.EMAIL_PROVIDER,
            "email_dry_run": settings.EMAIL_DRY_RUN or settings.DRY_RUN,
            "payment_provider": settings.PAYMENT_PROVIDER,
            "payments_enabled": settings.PAYMENTS_ENABLED,
            "autonomous_auto_discovery": bool(getattr(settings, "AUTONOMOUS_AUTO_DISCOVERY", True))
        }

agency_worker = PersistentAgencyWorker()
