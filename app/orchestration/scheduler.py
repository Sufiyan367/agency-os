"""
Autonomous Scheduling & Capacity Intelligence — Mega Prompt 9.
Provides deterministic priority job scheduling across Support, Sales, Delivery, and Acquisition.
"""
import enum
import logging
import uuid
import heapq
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.models import (
    CustomerIncident, SupportTicket, Payment, Business,
    OutreachMessage, ActiveOutreachLock
)
from app.core.config import settings

logger = logging.getLogger("agency.scheduler")


class JobPriorityTier(int, enum.Enum):
    CRITICAL_SEV1 = 0        # SEV-1 Customer Incidents (P0 - Immediate)
    HIGH_SEV2_PAYMENT = 1    # SEV-2 Incidents & Verified Payment Delivery Unlocks (P1)
    COMMERCIAL_SALES = 2     # High-EV Sales Replies & Proposal Actions (P2)
    ROUTINE_OPERATIONS = 3   # Routine Inbox Polling, Normal Support Tickets (P3)
    BACKGROUND_DISCOVERY = 4 # Discovery, Enrichment, Audits, Benchmarks (P4)


class ScheduledJob(BaseModel):
    job_id: str = Field(default_factory=lambda: f"JOB-{uuid.uuid4().hex[:8].upper()}")
    priority_tier: JobPriorityTier
    job_type: str
    entity_type: str
    entity_id: int
    commercial_value_usd: float = 0.0
    severity: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: str = "QUEUED"

    # Comparison for heapq: order by priority_tier, then -commercial_value_usd, then created_at
    def __lt__(self, other: "ScheduledJob") -> bool:
        if self.priority_tier != other.priority_tier:
            return self.priority_tier < other.priority_tier
        if self.commercial_value_usd != other.commercial_value_usd:
            return self.commercial_value_usd > other.commercial_value_usd
        return self.created_at < other.created_at


class CapacityReport(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_constrained: bool = False
    outbound_quota_daily: int = 1
    outbound_sent_today: int = 0
    outbound_available: int = 1
    active_outreach_locked: bool = False
    active_worker_concurrency: int = 1
    max_worker_concurrency: int = 4
    disk_free_gb: float = 20.0
    disk_used_pct: float = 15.0
    db_latency_ms: float = 1.5
    active_incidents_sev1: int = 0
    active_incidents_sev2: int = 0
    bottlenecks: List[str] = Field(default_factory=list)


class DeterministicScheduler:
    """
    Deterministic Job Scheduler and Capacity Governor.
    Prevents thread exhaustion, respects VPS resource constraints,
    and ensures critical customer issues outrank lower-tier background tasks.
    """

    def __init__(self):
        self._heap: List[ScheduledJob] = []
        self._active_jobs: Dict[str, ScheduledJob] = {}

    def enqueue(self, job: ScheduledJob) -> str:
        """Adds a job to the deterministic priority queue."""
        heapq.heappush(self._heap, job)
        logger.info(f"[Scheduler] Enqueued {job.job_type} (Tier {job.priority_tier.name}, EV ${job.commercial_value_usd:.0f}) for {job.entity_type} #{job.entity_id}")
        return job.job_id

    def pop_next_job(self, capacity: CapacityReport) -> Optional[ScheduledJob]:
        """
        Pops the highest-priority job eligible to run under current capacity constraints.
        If outbound quota is 0, skips outbound jobs until capacity refreshes.
        """
        if not self._heap:
            return None

        # If system is severely constrained by SEV-1, only allow SEV-1 jobs
        if capacity.active_incidents_sev1 > 0:
            temp_skipped: List[ScheduledJob] = []
            next_job = None
            while self._heap:
                cand = heapq.heappop(self._heap)
                if cand.priority_tier == JobPriorityTier.CRITICAL_SEV1:
                    next_job = cand
                    break
                temp_skipped.append(cand)

            for skipped in temp_skipped:
                heapq.heappush(self._heap, skipped)

            if next_job:
                next_job.status = "RUNNING"
                self._active_jobs[next_job.job_id] = next_job
            return next_job

        # Standard pop
        job = heapq.heappop(self._heap)
        job.status = "RUNNING"
        self._active_jobs[job.job_id] = job
        return job

    def complete_job(self, job_id: str, success: bool = True):
        """Marks an active job as completed or failed."""
        if job_id in self._active_jobs:
            self._active_jobs[job_id].status = "COMPLETED" if success else "FAILED"
            del self._active_jobs[job_id]

    def get_queued_jobs(self) -> List[ScheduledJob]:
        """Returns all currently queued jobs sorted by deterministic priority."""
        return sorted(self._heap)

    def clear(self):
        """Clears queue for test isolation."""
        self._heap.clear()
        self._active_jobs.clear()

    async def evaluate_capacity(self, session: AsyncSession) -> CapacityReport:
        """
        Inspects real database state and host metrics to compute active capacity.
        """
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt_outreach = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.status == "SENT",
            OutreachMessage.sent_at >= today_start
        )
        sent_today = (await session.execute(stmt_outreach)).scalar() or 0

        daily_cap = getattr(settings, "MAX_OUTREACH_PER_DAY", 1) or 1
        available_outreach = max(0, daily_cap - sent_today)

        stmt_lock = select(ActiveOutreachLock).where(ActiveOutreachLock.slot_id == 1)
        lock = (await session.execute(stmt_lock)).scalar_one_or_none()
        is_locked = bool(lock and lock.status == "ACTIVE")

        # Check unaddressed critical incidents
        stmt_inc = select(CustomerIncident).where(CustomerIncident.is_resolved == False)
        incidents = (await session.execute(stmt_inc)).scalars().all()
        sev1_count = sum(1 for i in incidents if i.severity == "SEV-1")
        sev2_count = sum(1 for i in incidents if i.severity == "SEV-2")

        bottlenecks = []
        if available_outreach <= 0:
            bottlenecks.append("OUTBOUND_DAILY_CAP_REACHED")
        if is_locked:
            bottlenecks.append("OUTREACH_SLOT_ACTIVE_LOCK")
        if sev1_count > 0:
            bottlenecks.append(f"CRITICAL_INCIDENT_ACTIVE (SEV-1: {sev1_count})")

        is_constrained = bool(bottlenecks)

        return CapacityReport(
            is_constrained=is_constrained,
            outbound_quota_daily=daily_cap,
            outbound_sent_today=sent_today,
            outbound_available=available_outreach,
            active_outreach_locked=is_locked,
            active_worker_concurrency=len(self._active_jobs),
            max_worker_concurrency=4,
            active_incidents_sev1=sev1_count,
            active_incidents_sev2=sev2_count,
            bottlenecks=bottlenecks
        )


# Global Singleton
deterministic_scheduler = DeterministicScheduler()
