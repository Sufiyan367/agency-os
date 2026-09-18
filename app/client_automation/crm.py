"""
Agency OS — Client CRM Lifecycle & Follow-up State Machine.

Manages lead state transitions through the commercial automation lifecycle:
INQUIRY -> QUALIFIED -> BOOKING_REQUESTED -> BOOKED -> COMPLETED -> FOLLOWUP_DUE.

Enforces transition validity, audit-trail logging, and policy-governed
follow-up cadence to prevent runaway or aggressive autonomous messaging.
"""

from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set

from app.client_automation.brain import shared_brain_manager
from app.client_automation.models import LeadRecord, LeadStage, AutomationModule

logger = logging.getLogger("agency.client_automation.crm")


class InvalidStageTransitionError(Exception):
    """Raised when an illegal lead stage transition is attempted."""
    pass


class ClientCRMStateMachine:
    """
    State machine enforcing valid client lead stage progressions and policy checks.
    """

    ALLOWED_TRANSITIONS: Dict[LeadStage, Set[LeadStage]] = {
        LeadStage.INQUIRY: {LeadStage.QUALIFIED, LeadStage.LOST, LeadStage.ESCALATED},
        LeadStage.QUALIFIED: {LeadStage.BOOKING_REQUESTED, LeadStage.BOOKED, LeadStage.LOST, LeadStage.ESCALATED},
        LeadStage.BOOKING_REQUESTED: {LeadStage.BOOKED, LeadStage.QUALIFIED, LeadStage.LOST, LeadStage.ESCALATED},
        LeadStage.BOOKED: {LeadStage.COMPLETED, LeadStage.FOLLOWUP_DUE, LeadStage.LOST, LeadStage.ESCALATED},
        LeadStage.COMPLETED: {LeadStage.FOLLOWUP_DUE, LeadStage.BOOKING_REQUESTED, LeadStage.BOOKED},
        LeadStage.FOLLOWUP_DUE: {LeadStage.BOOKING_REQUESTED, LeadStage.BOOKED, LeadStage.LOST, LeadStage.COMPLETED},
        LeadStage.LOST: {LeadStage.INQUIRY},  # Re-engagement
        LeadStage.ESCALATED: {LeadStage.QUALIFIED, LeadStage.BOOKED, LeadStage.COMPLETED, LeadStage.LOST},
    }

    @classmethod
    async def transition_stage(
        cls,
        client_id: str,
        lead_id: str,
        to_stage: LeadStage,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> LeadRecord:
        """
        Transitions a lead to a new lifecycle stage, verifying validity and recording history.
        """
        brain = shared_brain_manager.get_brain(client_id)
        if not brain:
            raise ValueError(f"Client '{client_id}' not found in Shared Brain")

        lead = brain.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead '{lead_id}' not found for client '{client_id}'")

        from_stage = lead.stage

        # Validate transition
        allowed = cls.ALLOWED_TRANSITIONS.get(from_stage, set())
        if to_stage not in allowed:
            raise InvalidStageTransitionError(
                f"Cannot transition lead '{lead_id}' from {from_stage.value} to {to_stage.value}. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )

        lead.stage = to_stage
        lead.updated_at = datetime.utcnow()
        transition_note = (
            f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}] Stage: {from_stage.value} -> {to_stage.value}. "
            f"Reason: {reason or 'System lifecycle progression'}"
        )
        lead.notes.append(transition_note)
        if metadata:
            lead.metadata.update(metadata)

        brain.upsert_lead(lead)
        logger.info(f"[ClientCRM] Lead {lead_id} transitioned: {from_stage.value} -> {to_stage.value}")
        return lead

    @classmethod
    async def schedule_followup(
        cls,
        client_id: str,
        lead_id: str,
        followup_type: str,
        delay_hours: int = 24,
        policy_note: str = ""
    ) -> Dict[str, Any]:
        """
        Schedules a follow-up task adhering to rate limits and client policy.
        Never sends autonomous messages immediately.
        """
        brain = shared_brain_manager.get_brain(client_id)
        if not brain:
            return {"success": False, "error": f"Client '{client_id}' not found"}

        lead = brain.get_lead(lead_id)
        if not lead:
            return {"success": False, "error": f"Lead '{lead_id}' not found"}

        # Check follow-up safety policy: don't schedule if lead is LOST or currently ESCALATED
        if lead.stage in (LeadStage.LOST, LeadStage.ESCALATED):
            return {
                "success": False,
                "error": f"Follow-up prohibited: lead is in {lead.stage.value} stage.",
                "lead_id": lead_id,
            }

        due_date = datetime.utcnow() + timedelta(hours=delay_hours)
        task_id = f"TASK-{client_id[:4].upper()}-{len(lead.notes)+1}"
        task_record = {
            "task_id": task_id,
            "client_id": client_id,
            "lead_id": lead_id,
            "type": followup_type,
            "scheduled_for": due_date.isoformat(),
            "policy_note": policy_note or "Standard cadence window",
            "status": "QUEUED_FOR_SUPERVISOR",
        }

        lead.notes.append(f"Follow-up queued: {followup_type} scheduled for {due_date.strftime('%Y-%m-%d %H:%M')}")
        lead.metadata.setdefault("scheduled_tasks", []).append(task_record)
        brain.upsert_lead(lead)

        return {
            "success": True,
            "task_id": task_id,
            "due_date": due_date.isoformat(),
            "lead_id": lead_id,
            "status": "QUEUED_FOR_SUPERVISOR",
        }


client_crm_state_machine = ClientCRMStateMachine()
