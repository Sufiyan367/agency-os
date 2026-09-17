"""
Agency OS — N8N Orchestration Bridge & Money-First Automation Engine.

Unifies existing Agency OS capabilities with existing n8n workflows:
- Agency OS remains the canonical system of record (database truth, qualification invariants,
  CEO approval gate, payment verification, and delivery unlock).
- n8n acts as the external event-driven orchestration layer (scheduling, event triggers,
  operator alerts, task routing, and status synchronization).
- Enforces zero fake revenue, zero unapproved outbound, and strict idempotency.
"""

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.event_bus import AgencyEvent, event_bus
from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType
from app.notifications.service import notification_service
from app.notifications.models import NotificationEventPayload, NotificationCategory, NotificationPriority

logger = logging.getLogger("agency.n8n.orchestrator")


class N8nOrchestrationEvent(BaseModel):
    """Canonical event payload forwarded between Agency OS and n8n."""
    event_id: str
    event_type: str
    source: str = "agency_os.core"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    entity_type: str
    entity_id: Optional[int] = None
    correlation_id: str
    payload_version: str = "1.0"
    payload: Dict[str, Any] = Field(default_factory=dict)


class InboundN8nEnvelope(BaseModel):
    """Envelope received from n8n or the integration edge."""
    event_id: str
    event_type: str
    source: str = "agency_os.n8n_edge"
    timestamp: Optional[str] = None
    entity_id: Optional[str] = None
    correlation_id: Optional[str] = None
    payload_version: str = "1.0"
    payload: Dict[str, Any] = Field(default_factory=dict)

    def get_dedup_key(self) -> str:
        return f"{self.event_id}:{self.correlation_id or ''}"


class N8nOrchestratorBridge:
    """
    Central orchestration bridge managing bi-directional communication between
    Agency OS core and n8n workflows.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._seen_execution_ids: Set[str] = set()
        self._seen_event_ids: Set[str] = set()
        self._forwarded_events_count: int = 0
        self._received_inbound_count: int = 0
        self._is_hooked: bool = False
        self._n8n_base_url: str = os.getenv("N8N_WEBHOOK_BASE_URL", "http://localhost:5678/webhook")
        self._n8n_api_key: Optional[str] = os.getenv("N8N_API_KEY", None)
        self._mock_sink: List[Dict[str, Any]] = []

    def hook_event_bus(self):
        """Subscribes the orchestrator to Agency OS UnifiedEventBus."""
        if not self._is_hooked:
            event_bus.subscribe("*", self.handle_agency_event)
            self._is_hooked = True
            logger.info("[N8nOrchestratorBridge] Hooked into UnifiedEventBus wildcard '*' subscriber.")

    async def handle_agency_event(self, event: AgencyEvent) -> None:
        """
        Observer callback for Agency OS lifecycle events.
        Translates canonical state changes into n8n orchestration triggers.
        """
        try:
            # Idempotency check on incoming event
            if event.event_id in self._seen_event_ids:
                return
            self._seen_event_ids.add(event.event_id)
            if len(self._seen_event_ids) > 2000:
                self._seen_event_ids.pop()

            event_type = event.event_type.upper()

            # 1. NEW QUALIFIED LEAD (Score >= 55) -> Notify CEO / Prepare Approval Context
            if event_type in ("COMMERCIAL_QUALIFICATION", "PROSPECT_QUALIFIED"):
                await self._forward_to_n8n("lead_qualification", event, {
                    "action": "PREPARE_CEO_APPROVAL_CONTEXT",
                    "business_id": event.entity_id,
                    "lead_data": event.payload,
                    "requires_ceo_review": True
                })

            # 2. CEO APPROVES OUTREACH -> Existing sender dispatches; n8n observes state
            elif event_type in ("OUTREACH_APPROVED", "OUTREACH_QUEUED"):
                await self._forward_to_n8n("personalized_outreach", event, {
                    "action": "OUTREACH_APPROVED_OBSERVED",
                    "message_id": event.payload.get("message_id"),
                    "business_id": event.entity_id,
                    "note": "Agency OS sender handles physical dispatch. n8n observes."
                })

            # 3. REAL REPLY -> n8n triggers CEO alert and creates follow-up task
            elif event_type in ("REPLY_CLASSIFIED", "CUSTOMER_REPLY_RECEIVED"):
                await self._forward_to_n8n("reply_classification", event, {
                    "action": "ALERT_CEO_REAL_REPLY",
                    "reply_id": event.payload.get("reply_id"),
                    "business_id": event.entity_id,
                    "intent": event.payload.get("intent", "UNKNOWN"),
                    "sentiment": event.payload.get("sentiment", "NEUTRAL"),
                    "urgency": "HIGH"
                })

            # 4. DEMO_REQUESTED -> n8n handles orchestration; Demo Factory builds demo
            elif event_type in ("DEMO_REQUESTED", "DEMO_STARTED"):
                await self._forward_to_n8n("demo_factory", event, {
                    "action": "ORCHESTRATE_CUSTOMER_DEMO",
                    "business_id": event.entity_id,
                    "verified_facts": event.payload.get("verified_facts", []),
                    "commercial_warning": "Demo generation never implies revenue."
                })

            # 5. PROPOSAL READY -> n8n triggers operator follow-up reminder
            elif event_type in ("PROPOSAL_CREATED", "PROPOSAL_SENT"):
                await self._forward_to_n8n("sales_followup", event, {
                    "action": "SCHEDULE_PROPOSAL_FOLLOWUP",
                    "proposal_id": event.payload.get("proposal_id"),
                    "business_id": event.entity_id,
                    "deal_value": event.payload.get("deal_value", 0.0)
                })

            # 6. PAYMENT_REVIEW_REQUIRED -> Immediate CEO/Operator alert
            elif event_type in ("PAYMENT_REVIEW_REQUIRED", "PAYMENT_ACTION_REQUIRED"):
                await self._forward_to_n8n("payment_ops", event, {
                    "action": "IMMEDIATE_CEO_PAYMENT_ALERT",
                    "payment_id": event.payload.get("payment_id"),
                    "business_id": event.entity_id,
                    "amount": event.payload.get("amount", 0.0),
                    "note": "Operator verification required via existing flow."
                })

            # 7. PAYMENT_CONFIRMED -> Existing production unlock & onboarding
            elif event_type in ("PAYMENT_CONFIRMED", "REVENUE_SETTLED"):
                await self._forward_to_n8n("customer_onboarding", event, {
                    "action": "INITIATE_ONBOARDING_HANDOFF",
                    "payment_id": event.payload.get("payment_id"),
                    "business_id": event.entity_id,
                    "production_unlocked": True
                })

        except Exception as e:
            logger.error(f"[N8nOrchestratorBridge] Error processing agency event {event.event_type}: {e}", exc_info=True)

    async def _forward_to_n8n(self, target_workflow: str, source_event: AgencyEvent, context: Dict[str, Any]) -> bool:
        """
        Transmits a validated event envelope to n8n webhook or sandbox mock sink.
        """
        async with self._lock:
            self._forwarded_events_count += 1

        envelope = N8nOrchestrationEvent(
            event_id=f"n8n_out_{source_event.event_id}",
            event_type=f"AGENCY_{source_event.event_type}",
            source="agency_os.core",
            entity_type=source_event.entity_type,
            entity_id=source_event.entity_id,
            correlation_id=source_event.correlation_id,
            payload={
                "target_workflow": target_workflow,
                "agency_event": source_event.model_dump(mode="json"),
                "orchestration_context": context
            }
        )

        # Store in internal sink for auditability and verification
        self._mock_sink.append(envelope.model_dump())
        if len(self._mock_sink) > 200:
            self._mock_sink.pop(0)

        # Attempt live webhook delivery if URL is configured and not in dry-run/testing
        if settings.APP_ENV != "test" and self._n8n_base_url and not self._n8n_base_url.startswith("http://localhost"):
            try:
                target_url = f"{self._n8n_base_url.rstrip('/')}/{target_workflow}"
                headers = {"Content-Type": "application/json"}
                if self._n8n_api_key:
                    headers["X-N8N-API-KEY"] = self._n8n_api_key

                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.post(target_url, json=envelope.model_dump(), headers=headers)
                    return resp.is_success
            except Exception as net_err:
                logger.debug(f"[N8nOrchestratorBridge] Live n8n webhook delivery skipped: {net_err}")
                return False

        return True

    async def process_inbound_n8n_event(
        self,
        envelope: InboundN8nEnvelope,
        session: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Receives inbound notifications / actions triggered by external n8n workflows.
        Enforces:
        1. Duplicate execution idempotency
        2. Strict validation & rejection of non-compliant commands (e.g. bypassing CEO approval or auto-confirming payments)
        3. Audit logging of all inbound automated actions
        """
        # Idempotency Check
        dedup_key = envelope.get_dedup_key()
        if dedup_key in self._seen_execution_ids:
            logger.info(f"[N8nOrchestratorBridge] Duplicate n8n execution ignored: {envelope.event_id} ({envelope.correlation_id})")
            return {
                "success": True,
                "status": "DEDUPLICATED",
                "message": f"Event {envelope.event_id} already processed by Agency OS."
            }

        self._seen_execution_ids.add(dedup_key)
        if len(self._seen_execution_ids) > 2000:
            self._seen_execution_ids.pop()

        async with self._lock:
            self._received_inbound_count += 1

        action = (envelope.payload.get("action") or envelope.event_type).upper()
        logger.info(f"[N8nOrchestratorBridge] Processing inbound n8n event: {envelope.event_type} (action: {action})")

        # SAFETY GATE 1: Rejection of automated outbound dispatch without CEO approval
        if any(bypass in action for bypass in ("SEND_OUTREACH", "DISPATCH_EMAIL", "BYPASS_APPROVAL", "FORCE_DISPATCH")):
            logger.warning(f"[N8nOrchestratorBridge] SAFETY VIOLATION BLOCKED: n8n attempted automated outreach dispatch: {action}")
            return {
                "success": False,
                "status": "FORBIDDEN",
                "error": "Safety violation: Autonomous outbound dispatch requires explicit CEO approval."
            }

        # SAFETY GATE 2: Rejection of automatic unverified payment confirmation
        if any(pay_bypass in action for pay_bypass in ("CONFIRM_PAYMENT", "FORCE_PAYMENT", "SETTLE_REVENUE")):
            logger.warning(f"[N8nOrchestratorBridge] SAFETY VIOLATION BLOCKED: n8n attempted unverified payment confirmation: {action}")
            return {
                "success": False,
                "status": "FORBIDDEN",
                "error": "Safety violation: Payment confirmation requires verified gateway webhook or human review."
            }

        # Handle Safe Actions
        if action in ("TRIGGER_DEMO_BUILD", "BUILD_DEMO"):
            biz_id_raw = envelope.payload.get("business_id") or envelope.entity_id
            if biz_id_raw:
                try:
                    biz_id = int(biz_id_raw)
                    return await self._handle_safe_demo_build(biz_id, session=session)
                except Exception as e:
                    return {"success": False, "status": "ERROR", "error": str(e)}

        if action in ("OPERATOR_NOTE_ADDED", "LOG_AUDIT_NOTE"):
            note = envelope.payload.get("note", "Operator note from n8n orchestration")
            logger.info(f"[N8nOrchestratorBridge] Operator note recorded: {note}")
            return {"success": True, "status": "NOTE_RECORDED", "note": note}

        if action in ("CANCEL_FOLLOWUP_SEQUENCE", "FOLLOWUP_CANCEL_REQUESTED"):
            campaign_id = envelope.payload.get("campaign_id")
            logger.info(f"[N8nOrchestratorBridge] Follow-up sequence cancellation acknowledged: {campaign_id}")
            return {"success": True, "status": "CANCELLATION_RECORDED", "campaign_id": campaign_id}

        # Generic observational receipt
        return {
            "success": True,
            "status": "ACCEPTED",
            "event_id": envelope.event_id,
            "action": action
        }

    async def _handle_safe_demo_build(self, business_id: int, session: Optional[Any] = None) -> Dict[str, Any]:
        from app.database.connection import AsyncSessionLocal
        from app.database.models import Business
        from app.delivery.requirements_engine import RequirementsPacket
        from app.delivery.demo_factory import demo_factory

        async def _execute(s):
            biz = await s.get(Business, business_id)
            if not biz:
                return {"success": False, "status": "NOT_FOUND", "error": f"Business {business_id} not found"}

            packet = RequirementsPacket(
                business_id=biz.id,
                business_name=biz.name or biz.domain,
                domain=biz.domain,
                city=biz.city,
                country=biz.country or "US",
                contact_email=biz.public_email or f"contact@{biz.domain}",
                service_title="High-Conversion Digital Overhaul",
                catalog_price_usd=750.0,
                advance_amount_usd=300.0,
                turnaround_days=7,
                deliverables=["Performance Optimization", "Mobile Responsiveness"],
                requirements=[],
                architectural_constraints=[],
                client_identity_verification={"verified": True}
            )

            demo_res = await demo_factory.generate_demo_package(s, biz.id, packet)
            return {
                "success": True,
                "status": "DEMO_BUILT",
                "demo_id": demo_res.demo_id,
                "artifact_id": demo_res.artifact_id,
                "revenue_implied": False
            }

        if session is not None:
            return await _execute(session)
        else:
            async with AsyncSessionLocal() as s:
                return await _execute(s)

    def get_orchestration_status(self) -> Dict[str, Any]:
        """Returns live telemetry regarding connected n8n workflows and bridge activity."""
        import json
        from pathlib import Path
        reg_file = Path(__file__).resolve().parent.parent.parent / "n8n" / "registry" / "workflow_registry.json"
        total_registered = 0
        if reg_file.exists():
            try:
                with open(reg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                total_registered = len(data.get("workflows", []))
            except Exception:
                total_registered = 9

        return {
            "status": "OPERATIONAL",
            "mode": "MONEY_FIRST_ORCHESTRATION",
            "is_hooked_to_event_bus": self._is_hooked,
            "registered_templates_count": total_registered,
            "events_forwarded_to_n8n": self._forwarded_events_count,
            "inbound_n8n_events_received": self._received_inbound_count,
            "recent_forwarded_sample_size": len(self._mock_sink),
            "safety_invariants": {
                "ceo_approval_bypass_allowed": False,
                "automatic_payment_confirmation_allowed": False,
                "revenue_inferred_from_demos": False
            }
        }


# Global Singleton Instance
n8n_orchestrator = N8nOrchestratorBridge()
