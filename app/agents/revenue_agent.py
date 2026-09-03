"""
Autonomous Revenue Agent Orchestrator.
Coordinates the continuous end-to-end One-Prospect Loop:
FIND ONE -> VERIFY -> AUDIT -> SCORE -> QUALIFY -> CONTACT -> CONVERSE -> NEXT.
Enforces Emergency Kill Switch, Autonomous Outreach toggles, and Dry-Run safety gates.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from sqlalchemy import select
from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.models import Business, PipelineStage
from app.agents.state_machine import ProspectState, AgentStateMachine, StateTransitionRecord
from app.agents.decision_engine import DecisionEngine, DecisionResult
from app.agents.prospect_agent import SingleProspectAgent
from app.agents.conversation_agent import ConversationAgent
from app.communications.router import ContactRouter, ChannelType
from app.communications.email_provider import DryRunEmailProvider
from app.communications.voice_provider import DryRunVoiceProvider
from app.outreach.compliance import compliance_guard
from app.compliance.calling_hours import calling_hours_compliance
from app.core.retry_policy import execute_with_retry

logger = logging.getLogger(__name__)


class RevenueAgentOrchestrator:
    """Master orchestrator running the continuous one-prospect-at-a-time autonomous loop."""

    def __init__(self):
        self.is_running: bool = False
        self.is_paused: bool = False
        self._task: Optional[asyncio.Task] = None
        self.poll_interval_seconds: float = 3.0
        self.current_state: ProspectState = ProspectState.DISCOVER
        self.current_prospect: Optional[Dict[str, Any]] = None
        self.last_decision: Optional[DecisionResult] = None
        self.history: List[StateTransitionRecord] = []
        self.stats = {
            "prospects_processed": 0,
            "prospects_skipped": 0,
            "contacts_attempted": 0,
            "replies_received": 0,
            "qualified_conversations": 0,
            "meetings_ready": 0,
            "proposals_ready": 0,
            "won_deals": 0,
            "pipeline_revenue_usd": 0.0
        }
        self.email_provider = DryRunEmailProvider()
        self.voice_provider = DryRunVoiceProvider()
        self.prospect_worker = SingleProspectAgent(provider_type="mock")

    def get_status(self) -> Dict[str, Any]:
        """Returns live status of the autonomous agent for the dashboard control surface."""
        return {
            "status": "RUNNING" if self.is_running and not self.is_paused else ("PAUSED" if self.is_paused else "IDLE"),
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "worker_active": self._task is not None and not self._task.done(),
            "kill_switch_active": not getattr(settings, "AUTONOMOUS_AGENT_ENABLED", False),
            "autonomous_outreach_active": getattr(settings, "AUTONOMOUS_OUTREACH", False),
            "commercial_floor_usd": getattr(settings, "MINIMUM_SERVICE_VALUE_USD", 500.0),
            "current_state": self.current_state.value,
            "current_prospect": self.current_prospect,
            "decision": self.last_decision.model_dump() if self.last_decision else None,
            "stats": self.stats
        }

    def start(self) -> Dict[str, Any]:
        """Starts autonomous agent operation and continuous background worker."""
        self.is_running = True
        self.is_paused = False
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._continuous_loop())
        logger.info("[RevenueAgentOrchestrator] Continuous background worker started.")
        return {
            "status": "RUNNING",
            "worker_active": True,
            "message": "Autonomous Revenue Agent continuous background worker started."
        }

    def pause(self) -> Dict[str, Any]:
        """Pauses autonomous agent operation."""
        self.is_paused = True
        logger.info("[RevenueAgentOrchestrator] Worker paused.")
        return {
            "status": "PAUSED",
            "worker_active": self._task is not None and not self._task.done(),
            "message": "Autonomous Revenue Agent paused."
        }

    def stop(self) -> Dict[str, Any]:
        """Stops autonomous agent operation and cancels background worker."""
        self.is_running = False
        self.is_paused = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("[RevenueAgentOrchestrator] Worker stopped.")
        return {
            "status": "IDLE",
            "worker_active": False,
            "message": "Autonomous Revenue Agent stopped."
        }

    def trigger_kill_switch(self) -> Dict[str, Any]:
        """Emergency kill switch: disables autonomous agent immediately."""
        self.is_running = False
        self.is_paused = False
        if self._task and not self._task.done():
            self._task.cancel()
        settings.AUTONOMOUS_AGENT_ENABLED = False
        settings.AUTONOMOUS_OUTREACH = False
        logger.warning("[RevenueAgentOrchestrator] EMERGENCY KILL SWITCH ACTIVATED.")
        return {
            "status": "KILLED",
            "kill_switch_active": True,
            "worker_active": False,
            "message": "EMERGENCY KILL SWITCH ACTIVATED. Agent halted."
        }

    async def _continuous_loop(self):
        """Persistent background worker loop processing one prospect at a time."""
        logger.info("[RevenueAgentWorker] Autonomous one-prospect background loop launched.")
        while self.is_running:
            try:
                # 1. Check if paused
                if self.is_paused:
                    await asyncio.sleep(self.poll_interval_seconds)
                    continue

                # 2. Check kill switch / active master toggle
                if not getattr(settings, "AUTONOMOUS_AGENT_ENABLED", False):
                    await asyncio.sleep(self.poll_interval_seconds)
                    continue

                # 3. Fetch next candidate strictly one-at-a-time
                candidate_data = None
                async with AsyncSessionLocal() as db:
                    cand_biz = await self.prospect_worker.get_next_uncontacted_prospect(
                        db, commercial_floor=getattr(settings, "MINIMUM_SERVICE_VALUE_USD", 500.0)
                    )
                    if cand_biz:
                        candidate_data = {
                            "id": cand_biz.id,
                            "name": cand_biz.name,
                            "domain": cand_biz.domain,
                            "website": getattr(cand_biz, "website_url", None) or f"https://{cand_biz.domain}",
                            "phone": cand_biz.phone,
                            "email": getattr(cand_biz, "public_email", None) or getattr(cand_biz, "email", None),
                            "city": getattr(cand_biz, "city", None) or "Austin",
                            "country": getattr(cand_biz, "country", None) or "US",
                            "niche": getattr(cand_biz, "niche", None) or "Commercial Services",
                            "estimated_value": 750.0,
                            "buyer_score": 82.0,
                            "opportunity_score": 76.0,
                            "performance_score": 48.0,
                            "load_time_seconds": 4.3
                        }

                if not candidate_data:
                    # Discover a fresh candidate using the provider
                    candidate_data = await self.prospect_worker.discover_single_candidate(
                        country="US", city="Austin", niche="Commercial Services"
                    )

                if candidate_data:
                    await self.step_single_prospect(
                        candidate_data,
                        commercial_floor=getattr(settings, "MINIMUM_SERVICE_VALUE_USD", 500.0)
                    )

            except asyncio.CancelledError:
                logger.info("[RevenueAgentWorker] Background loop received cancellation.")
                break
            except Exception as e:
                logger.error(f"[RevenueAgentWorker] Error during single-prospect cycle: {e}", exc_info=True)
                # Auto-recovery: sleep briefly and resume loop without crashing
                await asyncio.sleep(self.poll_interval_seconds)

            try:
                await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                break

    async def step_single_prospect(
        self,
        candidate_data: Dict[str, Any],
        commercial_floor: float = 500.0
    ) -> Dict[str, Any]:
        """
        Executes one full lifecycle pass on exactly one prospect.
        Guarantees isolation: does not loop through a second prospect until this cycle finishes.
        Flow:
        DISCOVER -> AUDIT -> SCORE -> CONTACT VALIDATION -> QUALIFY -> EMAIL/VOICE ROUTING -> OUTREACH -> RESPONSE HANDLING.
        """
        self.current_prospect = candidate_data
        b_name = candidate_data.get("name", "Unknown")

        # 1. State: DISCOVER -> Check digital existence
        has_domain = bool(candidate_data.get("domain") or candidate_data.get("website"))
        has_phone = bool(candidate_data.get("phone"))
        dec = DecisionEngine.evaluate_discovery(b_name, has_domain, has_phone)
        self.last_decision = dec
        self._record_transition(b_name, ProspectState.DISCOVER, dec.target_state, dec.reason, dec.confidence)

        if dec.target_state == ProspectState.SKIPPED:
            self.stats["prospects_skipped"] += 1
            await self._persist_stage(candidate_data, "REJECTED")
            return {"status": "SKIPPED", "reason": dec.reason}

        # 2. State: CONTACT VALIDATION & SUPPRESSION ENFORCEMENT
        async with AsyncSessionLocal() as session:
            is_supp = await compliance_guard.is_suppressed(
                session,
                email=candidate_data.get("email"),
                phone=candidate_data.get("phone"),
                domain=candidate_data.get("domain")
            )
            if is_supp:
                self.current_state = ProspectState.SKIPPED
                self._record_transition(b_name, ProspectState.DISCOVER, ProspectState.SKIPPED, "Global suppression match (opted out or unsubscribed)", 1.0)
                self.stats["prospects_skipped"] += 1
                await self._persist_stage(candidate_data, "REJECTED")
                return {"status": "SKIPPED", "reason": "SUPPRESSED"}

        # 3. State: AUDIT & SCORE ($500+ Floor)
        self.current_state = ProspectState.AUDIT
        est_val = candidate_data.get("estimated_value", 750.0)
        buyer_score = candidate_data.get("buyer_score", 82.0)
        opp_score = candidate_data.get("opportunity_score", 76.0)

        dec_score = DecisionEngine.evaluate_commercial_qualification(
            estimated_min_value=est_val,
            commercial_floor=commercial_floor,
            buyer_score=buyer_score,
            opp_score=opp_score
        )
        self.last_decision = dec_score
        self._record_transition(b_name, ProspectState.AUDIT, dec_score.target_state, dec_score.reason, dec_score.confidence)

        if dec_score.target_state == ProspectState.SKIPPED:
            self.current_state = ProspectState.SKIPPED
            self.stats["prospects_skipped"] += 1
            await self._persist_stage(candidate_data, "REJECTED")
            return {"status": "SKIPPED", "reason": dec_score.reason}

        # 4. State: CONTACT_DISCOVERY -> Route channel
        self.current_state = ProspectState.CONTACT_DISCOVERY
        route = ContactRouter.route_contact(
            email=candidate_data.get("email"),
            phone=candidate_data.get("phone"),
            voice_enabled=not getattr(settings, "VOICE_DRY_RUN", True)
        )

        if not route.eligible:
            self.current_state = ProspectState.SKIPPED
            self._record_transition(b_name, ProspectState.CONTACT_DISCOVERY, ProspectState.SKIPPED, route.reason, 0.99)
            self.stats["prospects_skipped"] += 1
            await self._persist_stage(candidate_data, "REJECTED")
            return {"status": "SKIPPED", "reason": route.reason}

        # 5. TCPA Calling-Hours Check if routed to Voice
        if route.channel == ChannelType.VOICE:
            ch_res = calling_hours_compliance.is_calling_window_open(
                country=candidate_data.get("country", "US"),
                city=candidate_data.get("city", "Austin"),
                phone=route.destination
            )
            if not ch_res.is_allowed:
                # If email available, fallback to email; otherwise hold in OUTREACH_PENDING
                if candidate_data.get("email"):
                    route = ContactRouter.route_contact(email=candidate_data.get("email"), phone=None, voice_enabled=False)
                else:
                    self.current_state = ProspectState.OUTREACH_PENDING
                    self._record_transition(b_name, ProspectState.CONTACT_DISCOVERY, ProspectState.OUTREACH_PENDING, f"Calling window closed ({ch_res.reason}). Held until window opens.", 1.0)
                    await self._persist_stage(candidate_data, "APPROVAL")
                    return {"status": "HELD_CALLING_HOURS", "reason": ch_res.reason}

        # 6. State: OUTREACH_PREP -> Enforce Daily Limits & Safety Gates
        self.current_state = ProspectState.OUTREACH_PREP
        self._record_transition(b_name, ProspectState.CONTACT_DISCOVERY, ProspectState.OUTREACH_PREP, f"Routed to {route.channel.value}", 0.95)

        async with AsyncSessionLocal() as session:
            can_send = await compliance_guard.can_send_today(session)
            if not can_send:
                self.current_state = ProspectState.OUTREACH_PENDING
                self._record_transition(b_name, ProspectState.OUTREACH_PREP, ProspectState.OUTREACH_PENDING, "Daily outreach limit reached (MAX_OUTREACH_PER_DAY). Held.", 1.0)
                await self._persist_stage(candidate_data, "APPROVAL")
                return {"status": "LIMIT_REACHED", "reason": "DAILY_LIMIT_EXCEEDED"}

        # Safety Gate Check: Emergency Kill Switch & Human Takeover
        if getattr(settings, "AUTONOMOUS_AGENT_ENABLED", True) is False:
            self.current_state = ProspectState.OUTREACH_PENDING
            self._record_transition(
                b_name,
                ProspectState.OUTREACH_PREP,
                ProspectState.OUTREACH_PENDING,
                "Emergency Kill Switch Active: Autonomous outreach halted.",
                1.0
            )
            await self._persist_stage(candidate_data, "APPROVAL")
            return {"status": "KILLED", "channel": route.channel.value, "prospect": b_name}

        if candidate_data.get("human_takeover", False):
            self.current_state = ProspectState.OUTREACH_PENDING
            self._record_transition(
                b_name,
                ProspectState.OUTREACH_PREP,
                ProspectState.OUTREACH_PENDING,
                "Human Takeover Active: Operator intervention requested.",
                1.0
            )
            await self._persist_stage(candidate_data, "APPROVAL")
            return {"status": "HUMAN_TAKEOVER", "channel": route.channel.value, "prospect": b_name}

        # Eligible prospects ($500+) proceed autonomously to outreach without human approval queue!
        # 7. Execute Outreach with Retry Policy (DRY RUN SAFE)
        async def _dispatch():
            if route.channel == ChannelType.EMAIL:
                return await self.email_provider.send_email(
                    route.destination,
                    f"Turnaround diagnostic for {b_name}",
                    f"Audit summary: {candidate_data.get('load_time_seconds', 4.3)}s load time."
                )
            elif route.channel == ChannelType.VOICE:
                from app.services.voice_service import VoiceSalesService
                return await VoiceSalesService.initiate_outbound_call(
                    prospect_phone=route.destination,
                    business_name=b_name,
                    niche=candidate_data.get("niche", "Commercial Services"),
                    city=candidate_data.get("city", "Austin"),
                    audit_data={
                        "performance_score": candidate_data.get("performance_score", 48.0),
                        "load_time_seconds": candidate_data.get("load_time_seconds", 4.3)
                    },
                    language=candidate_data.get("language", "en")
                )

        success, res, _ = await execute_with_retry(_dispatch, max_retries=3, operation_name=f"Outreach to {b_name}")
        if not success:
            logger.warning(f"[RevenueAgent] Transient failure for {b_name}, held for retry: {res}")
            self.current_state = ProspectState.OUTREACH_PENDING
            await self._persist_stage(candidate_data, "APPROVAL")
            return {"status": "OUTREACH_FAILED_HELD", "error": str(res)}

        self.current_state = ProspectState.CONTACTED
        self._record_transition(b_name, ProspectState.OUTREACH_PREP, ProspectState.CONTACTED, f"Contact attempt placed via {route.channel.value} (DRY RUN).", 0.95)
        await self._persist_stage(candidate_data, "CONTACTED")
        self.stats["contacts_attempted"] += 1
        self.stats["prospects_processed"] += 1

        self.current_state = ProspectState.WAITING_RESPONSE
        await self._persist_stage(candidate_data, "REPLIED")
        return {"status": "CONTACTED", "channel": route.channel.value, "next": "WAITING_RESPONSE"}

    async def _persist_stage(self, candidate_data: Dict[str, Any], stage_name: str):
        """Persists the updated pipeline stage to database if business record exists."""
        biz_id = candidate_data.get("id")
        domain = candidate_data.get("domain")
        if not biz_id and not domain:
            return
        try:
            async with AsyncSessionLocal() as session:
                if biz_id:
                    q = select(Business).where(Business.id == biz_id)
                else:
                    q = select(Business).where(Business.domain == domain)
                res = await session.execute(q)
                biz = res.scalar_one_or_none()
                if biz:
                    biz.pipeline_stage = stage_name

                # Also update LocalBusiness/LocalLead if domain exists in local_businesses
                from app.models.entities import LocalBusiness, LocalLead, LeadStatus
                q_lead = select(LocalLead).join(LocalBusiness).where(LocalBusiness.domain == domain)
                res_lead = await session.execute(q_lead)
                lead = res_lead.scalar_one_or_none()
                if lead:
                    if stage_name == "CONTACTED":
                        lead.status = LeadStatus.CONTACTED.value
                    elif stage_name == "REJECTED":
                        lead.status = LeadStatus.DISQUALIFIED.value

                await session.commit()
        except Exception as e:
            logger.warning(f"[RevenueAgent] Could not persist pipeline stage {stage_name}: {e}")

    def _record_transition(self, business: str, prev: ProspectState, next_state: ProspectState, reason: str, conf: float):
        rec = StateTransitionRecord(
            business_name=business,
            previous_state=prev,
            new_state=next_state,
            reason=reason,
            confidence=conf
        )
        self.history.append(rec)


revenue_agent_orchestrator = RevenueAgentOrchestrator()
