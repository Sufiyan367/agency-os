"""
Agency OS — Supervised Client Automation Orchestrator.

Central coordinating engine that:
1. Ingests raw multi-channel events (calls, messages, web inquiries).
2. Verifies tenant configuration, module enablement, and business hours.
3. Automatically routes routine tasks:
   - Missed calls -> MissedCallAutomationService
   - FAQ / inquiries -> KnowledgeEngine
   - Lead responses -> ClientLeadQualifier
   - Slot requests & bookings -> AppointmentAutomationService
4. Enforces human supervisor escalation on:
   - Explicit human operator requests
   - Low retrieval confidence / ungrounded questions
   - Severe complaints or compliance concerns
5. Publishes canonical events to the UnifiedEventBus so n8n observes state.
"""

from __future__ import annotations
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from app.core.event_bus import AgencyEvent, event_bus
from app.client_automation.brain import shared_brain_manager
from app.client_automation.models import (
    ClientAutomationConfig,
    AutomationModule,
    LeadRecord,
    LeadStage,
    EscalationEvent,
    EscalationReason,
)
from app.client_automation.missed_call import missed_call_automation, MissedCallAutomationService
from app.client_automation.knowledge import knowledge_engine, KnowledgeEngine
from app.client_automation.qualification import client_lead_qualifier, ClientLeadQualifier
from app.client_automation.appointments import appointment_automation, AppointmentAutomationService
from app.client_automation.crm import client_crm_state_machine

logger = logging.getLogger("agency.client_automation.orchestrator")


class SupervisedClientOrchestrator:
    """
    Supervises autonomous client automation pipelines, executing routine tasks
    and gating sensitive interactions for operator review.
    """

    def __init__(
        self,
        missed_call_svc: Optional[MissedCallAutomationService] = None,
        appointment_svc: Optional[AppointmentAutomationService] = None,
    ):
        self.missed_call_svc = missed_call_svc or missed_call_automation
        self.appointment_svc = appointment_svc or appointment_automation

    async def route_inbound_event(
        self,
        client_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Main entry point for client automation events.
        """
        brain = shared_brain_manager.get_brain(client_id)
        if not brain:
            return {
                "success": False,
                "status": "REJECTED_UNKNOWN_CLIENT",
                "error": f"Client '{client_id}' is not registered in Agency OS brain.",
            }

        config = brain.config
        normalized_type = event_type.upper()

        # -------------------------------------------------------------
        # 1. MISSED CALL EVENT
        # -------------------------------------------------------------
        if normalized_type in ("MISSED_CALL", "INBOUND_MISSED_CALL"):
            res = await self.missed_call_svc.handle_missed_call(
                client_id=client_id,
                caller_phone=payload.get("caller_phone", ""),
                caller_name=payload.get("caller_name"),
                is_suppressed=payload.get("is_suppressed", False),
            )
            # Emit event to bus for n8n observation
            await event_bus.publish(AgencyEvent(
                event_id=f"EVT-MC-{uuid.uuid4().hex[:8]}",
                correlation_id=payload.get("correlation_id", f"CORR-{uuid.uuid4().hex[:8]}"),
                event_type="CLIENT_MISSED_CALL_PROCESSED",
                entity_type="client_automation",
                entity_id=0,
                payload={"client_id": client_id, **res},
            ))
            return res

        # -------------------------------------------------------------
        # 2. INBOUND QUESTION / FAQ INQUIRY
        # -------------------------------------------------------------
        elif normalized_type in ("INBOUND_QUESTION", "CUSTOMER_QUERY", "FAQ_REQUEST"):
            if not config.has_module(AutomationModule.FAQ_KNOWLEDGE):
                return {
                    "success": False,
                    "status": "MODULE_DISABLED",
                    "error": "FAQ and Knowledge module disabled for this client.",
                }

            query = payload.get("query") or payload.get("message") or ""
            caller_phone = payload.get("caller_phone") or payload.get("phone")
            res = await knowledge_engine.answer_query(
                client_id=client_id,
                query=query,
                caller_phone=caller_phone,
            )

            # If escalated, publish escalation event
            if res.get("escalate"):
                await event_bus.publish(AgencyEvent(
                    event_id=f"EVT-ESC-{uuid.uuid4().hex[:8]}",
                    correlation_id=payload.get("correlation_id", f"CORR-{uuid.uuid4().hex[:8]}"),
                    event_type="CLIENT_ESCALATION_TRIGGERED",
                    entity_type="client_automation",
                    entity_id=0,
                    payload={"client_id": client_id, "query": query, **res},
                ))
            return res

        # -------------------------------------------------------------
        # 3. LEAD QUALIFICATION SUBMISSION
        # -------------------------------------------------------------
        elif normalized_type in ("LEAD_SUBMISSION", "QUALIFICATION_SUBMITTED"):
            lead_id = payload.get("lead_id")
            answers = payload.get("answers", {})

            # If lead doesn't exist, create initial record
            if not brain.get_lead(lead_id):
                lead_id = lead_id or f"LEAD-{uuid.uuid4().hex[:8].upper()}"
                new_lead = LeadRecord(
                    lead_id=lead_id,
                    client_id=client_id,
                    contact_name=payload.get("contact_name", "Inbound Prospect"),
                    contact_phone=payload.get("contact_phone"),
                    contact_email=payload.get("contact_email"),
                    stage=LeadStage.INQUIRY,
                    source=payload.get("source", "WEB_INQUIRY"),
                )
                brain.upsert_lead(new_lead)

            qual_result = await client_lead_qualifier.evaluate_lead(
                client_id=client_id,
                lead_id=lead_id,
                answers=answers,
            )

            res = qual_result.to_dict()
            await event_bus.publish(AgencyEvent(
                event_id=f"EVT-QUAL-{uuid.uuid4().hex[:8]}",
                correlation_id=payload.get("correlation_id", f"CORR-{uuid.uuid4().hex[:8]}"),
                event_type="CLIENT_LEAD_QUALIFIED" if qual_result.is_qualified else "CLIENT_LEAD_EVALUATED",
                entity_type="client_automation",
                entity_id=0,
                payload={"client_id": client_id, **res},
            ))
            return res

        # -------------------------------------------------------------
        # 4. APPOINTMENT BOOKING REQUEST
        # -------------------------------------------------------------
        elif normalized_type in ("BOOKING_REQUEST", "SCHEDULE_APPOINTMENT"):
            lead_id = payload.get("lead_id")
            service_id = payload.get("service_id", "srv_default")
            start_time_raw = payload.get("start_time")
            start_time = datetime.fromisoformat(start_time_raw) if isinstance(start_time_raw, str) else start_time_raw

            booking_res = await self.appointment_svc.book_appointment(
                client_id=client_id,
                lead_id=lead_id,
                service_id=service_id,
                start_time=start_time,
                notes=payload.get("notes"),
            )

            if booking_res.get("success"):
                await event_bus.publish(AgencyEvent(
                    event_id=f"EVT-BKG-{uuid.uuid4().hex[:8]}",
                    correlation_id=payload.get("correlation_id", f"CORR-{uuid.uuid4().hex[:8]}"),
                    event_type="CLIENT_APPOINTMENT_BOOKED",
                    entity_type="client_automation",
                    entity_id=0,
                    payload={"client_id": client_id, **booking_res},
                ))
            return booking_res

        # -------------------------------------------------------------
        # 5. UNRECOGNIZED / UNSUPPORTED EVENT -> ESCALATE
        # -------------------------------------------------------------
        else:
            brain.record_escalation(
                EscalationEvent(
                    escalation_id=f"ESC-UNREC-{uuid.uuid4().hex[:8]}",
                    client_id=client_id,
                    reason=EscalationReason.UNKNOWN_INTENT,
                    message=f"Received unsupported client automation event type: '{event_type}'",
                    context=payload,
                )
            )
            return {
                "success": False,
                "status": "ESCALATED_UNRECOGNIZED_EVENT",
                "error": f"Event '{event_type}' not supported for automatic execution; routed to supervisor.",
            }


supervised_client_orchestrator = SupervisedClientOrchestrator()
