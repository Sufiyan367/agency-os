import asyncio
from datetime import datetime
import uuid
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.connection import AsyncSessionLocal
from app.database.models import SystemRun, Business, PipelineStage, OutreachMessage, OutreachStatus
from app.crm.inbox_poller import inbox_poller
from app.crm.attention_engine import attention_engine
from app.campaigns.sender_registry import sender_registry
from app.outreach.sender import outreach_sender_adapter
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
                # Job 1: Inbound Reply Polling (CONTINUOUS) & CRM (AUTOMATIC)
                replies = await inbox_poller.poll_inbox(session)
                summary["inbox_replies_processed"] = len(replies)

                # Route newly received INTERESTED replies to AutonomousController pipeline
                for reply in replies:
                    if reply and getattr(reply, "classification", "") == "INTERESTED":
                        try:
                            from app.acquisition.autonomous_controller import autonomous_acquisition_controller
                            await autonomous_acquisition_controller._step_process_reply(
                                session=session,
                                business_id=reply.business_id,
                                reply_category=reply.classification,
                                reply_body=reply.raw_body
                            )
                            logger.info(
                                f"[PersistentWorker] Advanced AutonomousController for INTERESTED reply from biz {reply.business_id}"
                            )
                        except Exception as ac_err:
                            logger.error(
                                f"[PersistentWorker] Failed to advance AutonomousController for reply #{getattr(reply, 'id', None)}: {ac_err}"
                            )

                # Job 1b: Capacity-Governed Approved Queue Processing (DISPATCH)
                summary["approved_queue_processed"] = 0
                summary["approved_queue_deferred"] = 0
                if getattr(settings, "AUTONOMOUS_OUTREACH", True) and not getattr(settings, "EMERGENCY_STOP", False):
                    cap_summary = await sender_registry.get_sender_capacity_summary(session)
                    available_cap = cap_summary.get("available_capacity", 0)
                    approved_stmt = (
                        select(OutreachMessage)
                        .where(OutreachMessage.status == OutreachStatus.APPROVED)
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
                                logger.error(f"[PersistentWorker] Failed to dispatch approved message #{msg.id}: {send_err}")
                        summary["approved_queue_deferred"] = len(approved_msgs) - summary["approved_queue_processed"]
                    else:
                        summary["approved_queue_deferred"] = len(approved_msgs)
                        if approved_msgs and available_cap <= 0:
                            logger.info(
                                f"[PersistentWorker] {len(approved_msgs)} approved messages deferred: "
                                f"sender capacity exhausted for today ({cap_summary.get('rollout_stage_name')} cap: {cap_summary.get('rollout_daily_cap')}/day)."
                            )
                else:
                    logger.debug("[PersistentWorker] Autonomous outreach dispatch is paused by policy or emergency stop.")

                # Job 2: Process Due Follow-up Cadences (AUTOMATIC)
                followups = await followup_engine.process_due_followups(session)
                summary["followups_dispatched"] = len(followups)

                # Job 3: Payment Detection (AUTOMATIC) & Delivery (AUTOMATIC)
                active_pmt_provider = get_active_payment_provider()
                completed_payments = await active_pmt_provider.fetch_completed_payments()
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

                # Job 4: Lead Discovery (CONTINUOUS WORKER) & Audit/Scoring (AUTOMATIC) & Outreach (QUEUE + APPROVAL)
                cycle_interval_mins = settings.WORKER_CYCLE_INTERVAL_MINUTES
                should_run_cycle = False
                if getattr(settings, "AUTONOMOUS_AUTO_DISCOVERY", False):
                    if not self.last_cycle_at:
                        # Run on startup if pipeline has low volume (< 10 leads)
                        lead_count = (await session.execute(select(func.count(Business.id)))).scalar() or 0
                        if lead_count < 10:
                            should_run_cycle = True
                    else:
                        elapsed_mins = (datetime.utcnow() - self.last_cycle_at).total_seconds() / 60.0
                        if elapsed_mins >= cycle_interval_mins:
                            should_run_cycle = True
                else:
                    logger.debug("[PersistentWorker] Unsolicited autonomous auto-discovery is disabled by policy (AUTONOMOUS_AUTO_DISCOVERY=False).")

                if should_run_cycle:
                    logger.info("[PersistentWorker] Triggering scheduled autonomous lead cycle...")
                    cycle_res = await orchestrator.run_full_autonomous_cycle(
                        target_leads_per_market=10, max_opportunities_to_mine=1
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
            "autonomous_auto_discovery": bool(getattr(settings, "AUTONOMOUS_AUTO_DISCOVERY", False))
        }

agency_worker = PersistentAgencyWorker()
