"""
Unified Agency Orchestrator — Mega Prompt 9.
Welds Acquisition, Intelligence, Sales, Delivery, Support, and Learning into ONE system.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.database.models import (
    Business, Customer, Project, SupportTicket, CustomerIncident,
    Payment, Proposal, OutreachMessage, ActiveOutreachLock
)
from app.lifecycle.canonical_lifecycle import (
    CanonicalLifecycleStage, canonical_lifecycle_manager
)
from app.orchestration.scheduler import deterministic_scheduler, ScheduledJob, JobPriorityTier
from app.intelligence.next_best_action import next_best_action_engine
from app.intelligence.prioritization import prospect_priority_engine
from app.intelligence.optimization import optimization_engine
from app.intelligence.revenue_optimization import revenue_optimization_engine
from app.intelligence.maintenance_intelligence import predictive_maintenance_engine
from app.delivery.lifecycle import DeliveryLifecycleService
from app.support.service import SupportService
from app.core.event_bus import event_bus, AgencyEvent
from app.core.config import settings

logger = logging.getLogger("agency.unified_orchestrator")


class UnifiedAgencyOrchestrator:
    """
    Central operational engine executing the closed-loop agency lifecycle.
    Deterministic Agency OS core remains the sole authority.
    """

    def __init__(self):
        self.delivery_service = DeliveryLifecycleService()
        self.support_service = SupportService()

    async def get_system_status(self, session: AsyncSession) -> Dict[str, Any]:
        """Returns comprehensive operational state across all integrated engines."""
        capacity = await deterministic_scheduler.evaluate_capacity(session)
        rev_summary = await revenue_optimization_engine.get_revenue_summary(session)
        host_maint = await predictive_maintenance_engine.analyze_host_trends(session)

        # Count businesses by canonical stage
        stmt_biz = select(Business.id)
        biz_ids = (await session.execute(stmt_biz)).scalars().all()

        stage_counts: Dict[str, int] = {s.value: 0 for s in CanonicalLifecycleStage}
        for b_id in biz_ids:
            biz = await session.get(Business, b_id)
            if biz:
                stage = canonical_lifecycle_manager.map_to_canonical(biz)
                stage_counts[stage.value] = stage_counts.get(stage.value, 0) + 1

        # Count active incidents
        stmt_inc = select(func.count(CustomerIncident.id)).where(CustomerIncident.is_resolved == False)
        active_incidents = (await session.execute(stmt_inc)).scalar() or 0

        # Count live customers
        stmt_cust = select(func.count(Customer.id))
        total_customers = (await session.execute(stmt_cust)).scalar() or 0

        return {
            "status": "OPERATIONAL",
            "timestamp": datetime.utcnow().isoformat(),
            "capacity": capacity.model_dump(),
            "revenue": rev_summary,
            "maintenance": host_maint,
            "total_prospects": len(biz_ids),
            "total_customers": total_customers,
            "active_unresolved_incidents": active_incidents,
            "pipeline_stage_counts": stage_counts,
            "scheduler_queued_jobs": len(deterministic_scheduler.get_queued_jobs())
        }

    async def step_prospect_lifecycle(
        self,
        session: AsyncSession,
        business_id: int,
        operator_override: bool = False
    ) -> Dict[str, Any]:
        """
        Determines next best action using policy-gated NextBestActionEngine,
        validates transition feasibility, and executes state advancement.
        """
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business #{business_id} not found.")

        current_stage = canonical_lifecycle_manager.map_to_canonical(biz)
        decision = await next_best_action_engine.determine_next_action(session, business_id)

        target_stage: Optional[CanonicalLifecycleStage] = None

        if current_stage == CanonicalLifecycleStage.DISCOVERED:
            target_stage = CanonicalLifecycleStage.QUALIFIED
        elif current_stage == CanonicalLifecycleStage.QUALIFIED:
            target_stage = CanonicalLifecycleStage.PRIORITIZED
        elif current_stage == CanonicalLifecycleStage.PRIORITIZED:
            target_stage = CanonicalLifecycleStage.CONTACTABLE
        elif current_stage == CanonicalLifecycleStage.CONTACTABLE:
            target_stage = CanonicalLifecycleStage.OUTREACH_ELIGIBLE
        elif current_stage == CanonicalLifecycleStage.OUTREACH_ELIGIBLE:
            # Policy check: outbound limit & approval
            capacity = await deterministic_scheduler.evaluate_capacity(session)
            if capacity.outbound_available > 0 and not capacity.active_outreach_locked:
                target_stage = CanonicalLifecycleStage.OUTREACH_SENT
            else:
                target_stage = CanonicalLifecycleStage.WAITING_FOR_CUSTOMER
        elif current_stage == CanonicalLifecycleStage.RESPONSE_RECEIVED:
            target_stage = CanonicalLifecycleStage.POSITIVE
        elif current_stage == CanonicalLifecycleStage.POSITIVE:
            target_stage = CanonicalLifecycleStage.DEMO_ELIGIBLE
        elif current_stage == CanonicalLifecycleStage.DEMO_ELIGIBLE:
            target_stage = CanonicalLifecycleStage.DEMO_READY
        elif current_stage == CanonicalLifecycleStage.DEMO_READY:
            target_stage = CanonicalLifecycleStage.PROPOSAL_READY
        elif current_stage == CanonicalLifecycleStage.PROPOSAL_READY:
            target_stage = CanonicalLifecycleStage.PROPOSAL_ACCEPTED
        elif current_stage == CanonicalLifecycleStage.PROPOSAL_ACCEPTED:
            target_stage = CanonicalLifecycleStage.PAYMENT_PENDING
        elif current_stage == CanonicalLifecycleStage.PAYMENT_VERIFIED:
            target_stage = CanonicalLifecycleStage.DELIVERY_UNLOCKED
        elif current_stage == CanonicalLifecycleStage.DELIVERY_UNLOCKED:
            target_stage = CanonicalLifecycleStage.ONBOARDING
        elif current_stage == CanonicalLifecycleStage.ONBOARDING:
            target_stage = CanonicalLifecycleStage.BUILDING
        elif current_stage == CanonicalLifecycleStage.BUILDING:
            target_stage = CanonicalLifecycleStage.QA
        elif current_stage == CanonicalLifecycleStage.QA:
            target_stage = CanonicalLifecycleStage.DEPLOYING
        elif current_stage == CanonicalLifecycleStage.DEPLOYING:
            target_stage = CanonicalLifecycleStage.LIVE
        elif current_stage == CanonicalLifecycleStage.LIVE:
            target_stage = CanonicalLifecycleStage.RETAINED

        if target_stage:
            audit = await canonical_lifecycle_manager.transition(
                session=session,
                business_id=business_id,
                target_stage=target_stage,
                actor="unified_orchestrator",
                reason=f"Action: {decision.action.value} — {decision.reasoning}",
                metadata={"commercial_value": decision.commercial_value_usd}
            )
            return {
                "business_id": business_id,
                "previous_stage": audit.from_stage.value if audit.from_stage else None,
                "current_stage": audit.to_stage.value,
                "action_taken": decision.action.value,
                "reasoning": decision.reasoning,
                "confidence": decision.confidence
            }

        return {
            "business_id": business_id,
            "current_stage": current_stage.value,
            "action_taken": decision.action.value,
            "reasoning": decision.reasoning,
            "confidence": decision.confidence,
            "notes": "No stage transition required; awaiting external event or condition."
        }


# Global Singleton
unified_orchestrator = UnifiedAgencyOrchestrator()
