"""
Autonomous Revenue Agent Orchestrator.
Coordinates the end-to-end One-Prospect Loop:
FIND ONE -> VERIFY -> AUDIT -> SCORE -> QUALIFY -> CONTACT -> CONVERSE -> NEXT.
Enforces Emergency Kill Switch, Autonomous Outreach toggles, and Dry-Run safety gates.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.models.entities import LocalBusiness
from app.agents.state_machine import ProspectState, AgentStateMachine, StateTransitionRecord
from app.agents.decision_engine import DecisionEngine, DecisionResult
from app.agents.prospect_agent import SingleProspectAgent
from app.agents.conversation_agent import ConversationAgent
from app.communications.router import ContactRouter, ChannelType
from app.communications.email_provider import DryRunEmailProvider
from app.communications.voice_provider import DryRunVoiceProvider

logger = logging.getLogger(__name__)


class RevenueAgentOrchestrator:
    """Master orchestrator running the one-prospect-at-a-time autonomous loop."""

    def __init__(self):
        self.is_running: bool = False
        self.is_paused: bool = False
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
            "kill_switch_active": not getattr(settings, "AUTONOMOUS_AGENT_ENABLED", False),
            "autonomous_outreach_active": getattr(settings, "AUTONOMOUS_OUTREACH", False),
            "commercial_floor_usd": getattr(settings, "MINIMUM_SERVICE_VALUE_USD", 500.0),
            "current_state": self.current_state.value,
            "current_prospect": self.current_prospect,
            "decision": self.last_decision.dict() if self.last_decision else None,
            "stats": self.stats
        }

    def start(self) -> Dict[str, Any]:
        """Starts autonomous agent operation."""
        self.is_running = True
        self.is_paused = False
        return {"status": "RUNNING", "message": "Autonomous Revenue Agent started."}

    def pause(self) -> Dict[str, Any]:
        """Pauses autonomous agent operation."""
        self.is_paused = True
        return {"status": "PAUSED", "message": "Autonomous Revenue Agent paused."}

    def stop(self) -> Dict[str, Any]:
        """Stops autonomous agent operation."""
        self.is_running = False
        self.is_paused = False
        return {"status": "IDLE", "message": "Autonomous Revenue Agent stopped."}

    def trigger_kill_switch(self) -> Dict[str, Any]:
        """Emergency kill switch: disables autonomous agent immediately."""
        self.is_running = False
        self.is_paused = False
        settings.AUTONOMOUS_AGENT_ENABLED = False
        settings.AUTONOMOUS_OUTREACH = False
        return {"status": "KILLED", "kill_switch_active": True, "message": "EMERGENCY KILL SWITCH ACTIVATED. Agent halted."}

    async def step_single_prospect(
        self,
        candidate_data: Dict[str, Any],
        commercial_floor: float = 500.0
    ) -> Dict[str, Any]:
        """
        Executes one full lifecycle pass on exactly one prospect.
        Guarantees isolation: does not loop through a second prospect until this cycle finishes.
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
            return {"status": "SKIPPED", "reason": dec.reason}

        # 2. State: AUDIT & SCORE
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
            self.stats["prospects_skipped"] += 1
            return {"status": "SKIPPED", "reason": dec_score.reason}

        # 3. State: CONTACT_DISCOVERY -> Route channel
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
            return {"status": "SKIPPED", "reason": route.reason}

        # 4. State: OUTREACH_PREP -> Channel Action
        self.current_state = ProspectState.OUTREACH_PREP
        self._record_transition(b_name, ProspectState.CONTACT_DISCOVERY, ProspectState.OUTREACH_PREP, f"Routed to {route.channel.value}", 0.95)

        # 5. Safety Gate Check (Autonomous outreach disabled by default)
        auto_outreach = getattr(settings, "AUTONOMOUS_OUTREACH", False)
        agent_enabled = getattr(settings, "AUTONOMOUS_AGENT_ENABLED", False)

        if not auto_outreach or not agent_enabled:
            # Hold in OUTREACH_PENDING for human operator review
            self.current_state = ProspectState.OUTREACH_PENDING
            self._record_transition(
                b_name,
                ProspectState.OUTREACH_PREP,
                ProspectState.OUTREACH_PENDING,
                "Safety Gate: Held in OUTREACH_PENDING awaiting operator approval.",
                1.0
            )
            self.stats["prospects_processed"] += 1
            return {"status": "HELD_FOR_APPROVAL", "channel": route.channel.value, "prospect": b_name}

        # 6. Execute Mock / Dry-Run Outreach
        if route.channel == ChannelType.EMAIL:
            await self.email_provider.send_email(route.destination, f"Turnaround diagnostic for {b_name}", "Audit summary...")
        elif route.channel == ChannelType.VOICE:
            await self.voice_provider.place_call(route.destination, "Audit consultation script...")

        self.current_state = ProspectState.CONTACTED
        self._record_transition(b_name, ProspectState.OUTREACH_PREP, ProspectState.CONTACTED, f"Contact attempt placed via {route.channel.value} (DRY RUN).", 0.95)
        self.stats["contacts_attempted"] += 1
        self.stats["prospects_processed"] += 1

        self.current_state = ProspectState.WAITING_RESPONSE
        return {"status": "CONTACTED", "channel": route.channel.value, "next": "WAITING_RESPONSE"}

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
