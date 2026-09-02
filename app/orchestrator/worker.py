import asyncio
from datetime import datetime
import uuid
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.connection import AsyncSessionLocal
from app.database.models import SystemRun, Business, PipelineStage
from app.crm.inbox_poller import inbox_poller
from app.followups.engine import followup_engine
from app.orchestrator.loop import orchestrator
from app.core.config import settings
from app.core.logging import logger

class PersistentAgencyWorker:
    """
    Persistent background autonomous worker and scheduler.
    Runs unattended cycles, polls prospect replies, executes scheduled follow-up cadences,
    enforces rate limits, and logs operational heartbeats.
    """

    def __init__(self, interval_seconds: int = 60):
        self.interval_seconds = interval_seconds
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
                # Job 1: Inbound Reply Polling & Classification
                replies = await inbox_poller.poll_inbox(session)
                summary["inbox_replies_processed"] = len(replies)

                # Job 2: Process Due Follow-up Cadences
                followups = await followup_engine.process_due_followups(session)
                summary["followups_dispatched"] = len(followups)

                # Job 3: Check if an autonomous discovery cycle should run
                cycle_interval_mins = settings.WORKER_CYCLE_INTERVAL_MINUTES
                should_run_cycle = False
                if not self.last_cycle_at:
                    # Run on startup if pipeline has low volume (< 10 leads)
                    lead_count = (await session.execute(select(func.count(Business.id)))).scalar() or 0
                    if lead_count < 10:
                        should_run_cycle = True
                else:
                    elapsed_mins = (datetime.utcnow() - self.last_cycle_at).total_seconds() / 60.0
                    if elapsed_mins >= cycle_interval_mins:
                        should_run_cycle = True

                if should_run_cycle:
                    logger.info("[PersistentWorker] Triggering scheduled autonomous lead cycle...")
                    cycle_res = await orchestrator.run_full_autonomous_cycle(
                        target_leads_per_market=10, max_opportunities_to_mine=1
                    )
                    self.last_cycle_at = datetime.utcnow()
                    summary["autonomous_cycle_run"] = True
                    summary["cycle_summary"] = cycle_res

                run_record.status = "SUCCESS"
                run_record.records_processed = summary["inbox_replies_processed"] + summary["followups_dispatched"]
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
            "payments_enabled": settings.PAYMENTS_ENABLED
        }

agency_worker = PersistentAgencyWorker(interval_seconds=60)
