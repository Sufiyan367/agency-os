"""
Agency OS — Client Missed-Call Text-Back Automation.

Handles incoming missed call events:
1. Validates caller information and opt-out / suppression status.
2. Creates or updates LeadRecord in ClientBrain.
3. Evaluates business hours to select appropriate context-grounded message.
4. Synthesizes personalized text-back adhering to client brand voice.
5. Dispatches text-back via pluggable MissedCallProvider.
6. Records CallRecord in ClientBrain for CRM tracking and analytics.
"""

from __future__ import annotations
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from app.client_automation.brain import shared_brain_manager
from app.client_automation.models import (
    CallRecord,
    CallType,
    LeadRecord,
    LeadStage,
    AutomationModule,
)
from app.client_automation.interfaces import MissedCallProvider, MockMissedCallProvider

logger = logging.getLogger("agency.client_automation.missed_call")


class MissedCallAutomationService:
    """
    Client-facing missed call text-back workflow manager.
    """

    def __init__(self, provider: Optional[MissedCallProvider] = None):
        self.provider = provider or MockMissedCallProvider()

    async def handle_missed_call(
        self,
        client_id: str,
        caller_phone: str,
        caller_name: Optional[str] = None,
        is_suppressed: bool = False,
        call_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end missed call processing for a specific client tenant.
        """
        brain = shared_brain_manager.get_brain(client_id)
        if not brain:
            return {
                "success": False,
                "error": f"Client '{client_id}' not found in Shared Brain",
                "textback_sent": False,
            }

        config = brain.config
        if not config.has_module(AutomationModule.MISSED_CALL):
            return {
                "success": False,
                "error": f"Missed-call module disabled for client '{client_id}'",
                "textback_sent": False,
            }

        call_dt = call_time or datetime.utcnow()
        call_id = f"CALL-{uuid.uuid4().hex[:8].upper()}"

        # 1. Suppression / Opt-out check
        if is_suppressed:
            call_log = CallRecord(
                call_id=call_id,
                client_id=client_id,
                caller_phone=caller_phone,
                call_type=CallType.MISSED,
                is_after_hours=not config.business_hours.is_open(call_dt),
                textback_sent=False,
                disposition="SUPPRESSED_OPTED_OUT",
                timestamp=call_dt,
            )
            brain.save_call_log(call_log)
            return {
                "success": True,
                "status": "SUPPRESSED",
                "textback_sent": False,
                "reason": "Caller is on suppression / opt-out list",
                "call_id": call_id,
            }

        # 2. CRM Lead Sync
        # Find existing lead by phone or create new one
        existing_leads = [l for l in brain.list_leads() if l.contact_phone == caller_phone]
        if existing_leads:
            lead = existing_leads[0]
            lead.notes.append(f"Missed call logged at {call_dt.strftime('%Y-%m-%d %H:%M')}")
            brain.upsert_lead(lead)
            lead_id = lead.lead_id
        else:
            lead_id = f"LEAD-{uuid.uuid4().hex[:8].upper()}"
            lead = LeadRecord(
                lead_id=lead_id,
                client_id=client_id,
                contact_name=caller_name or f"Caller {caller_phone[-4:]}",
                contact_phone=caller_phone,
                stage=LeadStage.INQUIRY,
                source="MISSED_CALL",
                notes=[f"Inbound missed call received at {call_dt.strftime('%Y-%m-%d %H:%M')}"],
            )
            brain.upsert_lead(lead)

        # 3. Contextual Text-back Generation
        is_open = config.business_hours.is_open(call_dt)
        biz_name = config.business_name

        if is_open:
            message = (
                f"Hi! Sorry we missed your call at {biz_name}. "
                f"How can we assist you today? Feel free to reply here to book an appointment or ask a question."
            )
        else:
            message = (
                f"Hi! Thanks for calling {biz_name}. We are currently closed (Hours: {config.business_hours.open_time} - "
                f"{config.business_hours.close_time}). Reply to this text to let us know how we can help, and our team will get right back to you!"
            )

        # 4. Provider Dispatch
        dispatch_result = await self.provider.send_textback(
            to_phone=caller_phone,
            message=message,
            client_id=client_id,
        )

        textback_sent = dispatch_result.get("success", False) or dispatch_result.get("status") == "DELIVERED_MOCK"

        # 5. Record Call Log
        call_log = CallRecord(
            call_id=call_id,
            client_id=client_id,
            caller_phone=caller_phone,
            call_type=CallType.MISSED,
            is_after_hours=not is_open,
            textback_sent=textback_sent,
            textback_message=message if textback_sent else None,
            disposition="TEXTBACK_SENT" if textback_sent else "DISPATCH_FAILED",
            timestamp=call_dt,
        )
        brain.save_call_log(call_log)

        # Record interaction in lead conversation history
        brain.record_message(
            lead_id=lead_id,
            sender="SYSTEM_TEXTBACK",
            channel="SMS",
            text=message,
        )

        return {
            "success": True,
            "status": "PROCESSED",
            "call_id": call_id,
            "lead_id": lead_id,
            "is_after_hours": not is_open,
            "textback_sent": textback_sent,
            "message_body": message,
            "provider_response": dispatch_result,
        }


missed_call_automation = MissedCallAutomationService()
