"""
Canonical Support & Incident State Machine — Mega Prompt 7.
Enforces deterministic lifecycle transitions, transition guards, and append-only
audit events for tickets and incidents.
"""
import enum
import logging
from typing import Dict, Any, Optional, Set
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SupportTicket, CustomerIncident, IncidentEvent

logger = logging.getLogger("agency.support.state_machine")


class SupportLifecycleState(str, enum.Enum):
    SUPPORT_REQUESTED = "SUPPORT_REQUESTED"
    TICKET_CREATED = "TICKET_CREATED"
    TRIAGED = "TRIAGED"
    DIAGNOSING = "DIAGNOSING"
    ROOT_CAUSE_IDENTIFIED = "ROOT_CAUSE_IDENTIFIED"
    REMEDIATION_PLANNED = "REMEDIATION_PLANNED"
    FIX_AUTHORIZED = "FIX_AUTHORIZED"
    FIXING = "FIXING"
    QA_VALIDATION = "QA_VALIDATION"
    DEPLOYING = "DEPLOYING"
    VERIFYING = "VERIFYING"
    CUSTOMER_UPDATED = "CUSTOMER_UPDATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

    # Branch / Exception States
    WAITING_FOR_CUSTOMER = "WAITING_FOR_CUSTOMER"
    WAITING_FOR_EXTERNAL_PROVIDER = "WAITING_FOR_EXTERNAL_PROVIDER"
    ESCALATED_TO_HUMAN = "ESCALATED_TO_HUMAN"
    REOPENED = "REOPENED"


class StateTransitionError(Exception):
    """Raised when an invalid or unauthorized lifecycle transition is attempted."""
    pass


# Canonical aliases
SupportState = SupportLifecycleState
InvalidStateTransitionException = StateTransitionError


class SupportStateMachine:
    """
    Authoritative state machine governing support ticket and incident lifecycles.
    """

    ALLOWED_TRANSITIONS: Dict[SupportLifecycleState, Set[SupportLifecycleState]] = {
        SupportLifecycleState.SUPPORT_REQUESTED: {
            SupportLifecycleState.TICKET_CREATED
        },
        SupportLifecycleState.TICKET_CREATED: {
            SupportLifecycleState.TRIAGED,
            SupportLifecycleState.DIAGNOSING,
            SupportLifecycleState.CLOSED
        },
        SupportLifecycleState.TRIAGED: {
            SupportLifecycleState.DIAGNOSING,
            SupportLifecycleState.WAITING_FOR_CUSTOMER,
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.DIAGNOSING: {
            SupportLifecycleState.ROOT_CAUSE_IDENTIFIED,
            SupportLifecycleState.WAITING_FOR_EXTERNAL_PROVIDER,
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.ROOT_CAUSE_IDENTIFIED: {
            SupportLifecycleState.REMEDIATION_PLANNED,
            SupportLifecycleState.FIX_AUTHORIZED,
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.REMEDIATION_PLANNED: {
            SupportLifecycleState.FIX_AUTHORIZED,
            SupportLifecycleState.FIXING,
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.FIX_AUTHORIZED: {
            SupportLifecycleState.FIXING,
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.FIXING: {
            SupportLifecycleState.QA_VALIDATION,
            SupportLifecycleState.DEPLOYING,
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.QA_VALIDATION: {
            SupportLifecycleState.DEPLOYING,
            SupportLifecycleState.VERIFYING,
            SupportLifecycleState.FIXING,  # Bounded retry loop
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.DEPLOYING: {
            SupportLifecycleState.VERIFYING,
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.VERIFYING: {
            SupportLifecycleState.CUSTOMER_UPDATED,
            SupportLifecycleState.RESOLVED,
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.CUSTOMER_UPDATED: {
            SupportLifecycleState.RESOLVED,
            SupportLifecycleState.CLOSED
        },
        SupportLifecycleState.RESOLVED: {
            SupportLifecycleState.CLOSED,
            SupportLifecycleState.REOPENED
        },
        SupportLifecycleState.CLOSED: {
            SupportLifecycleState.REOPENED
        },
        SupportLifecycleState.WAITING_FOR_CUSTOMER: {
            SupportLifecycleState.DIAGNOSING,
            SupportLifecycleState.CLOSED,
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.WAITING_FOR_EXTERNAL_PROVIDER: {
            SupportLifecycleState.DIAGNOSING,
            SupportLifecycleState.ESCALATED_TO_HUMAN
        },
        SupportLifecycleState.ESCALATED_TO_HUMAN: {
            SupportLifecycleState.FIX_AUTHORIZED,
            SupportLifecycleState.FIXING,
            SupportLifecycleState.RESOLVED,
            SupportLifecycleState.CLOSED
        },
        SupportLifecycleState.REOPENED: {
            SupportLifecycleState.TRIAGED,
            SupportLifecycleState.DIAGNOSING
        }
    }

    @classmethod
    def can_transition(
        cls,
        current_state: str,
        target_state: str
    ) -> bool:
        try:
            curr = SupportLifecycleState(current_state)
            tgt = SupportLifecycleState(target_state)
            return tgt in cls.ALLOWED_TRANSITIONS.get(curr, set())
        except ValueError:
            return False

    @classmethod
    async def transition(
        cls,
        session: AsyncSession,
        ticket: SupportTicket,
        target_state: SupportLifecycleState,
        agent_role: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
        incident: Optional[CustomerIncident] = None
    ) -> SupportTicket:
        """
        Executes a deterministic state transition, updating ticket timestamps and
        appending an immutable IncidentEvent to the audit ledger.
        """
        curr_state_str = ticket.status
        target_state_str = target_state.value

        # Normalize legacy states if needed
        if curr_state_str == "NEW":
            curr_state = SupportLifecycleState.TICKET_CREATED
        elif curr_state_str == "CLASSIFIED":
            curr_state = SupportLifecycleState.TRIAGED
        elif curr_state_str == "FIX_PENDING_APPROVAL":
            curr_state = SupportLifecycleState.REMEDIATION_PLANNED
        elif curr_state_str == "REMEDIATING":
            curr_state = SupportLifecycleState.FIXING
        else:
            try:
                curr_state = SupportLifecycleState(curr_state_str)
            except ValueError:
                curr_state = SupportLifecycleState.TICKET_CREATED

        # Validate transition
        allowed = cls.ALLOWED_TRANSITIONS.get(curr_state, set())
        if target_state not in allowed:
            raise StateTransitionError(
                f"Invalid lifecycle transition: '{curr_state.value}' -> '{target_state_str}'. "
                f"Allowed destinations: {[s.value for s in allowed]}"
            )

        # Apply state
        ticket.status = target_state_str

        # Timestamp management
        now = datetime.utcnow()
        if target_state == SupportLifecycleState.DIAGNOSING and not ticket.first_action_at:
            ticket.first_action_at = now
        elif target_state == SupportLifecycleState.TRIAGED and not ticket.response_at:
            ticket.response_at = now
        elif target_state == SupportLifecycleState.RESOLVED:
            ticket.resolved_at = now
            if not ticket.resolution:
                ticket.resolution = reason
        elif target_state == SupportLifecycleState.CLOSED:
            ticket.closed_at = now

        # Append-only audit ledger entry
        inc = incident
        if not inc and session and ticket.id:
            from sqlalchemy import select
            inc_stmt = select(CustomerIncident).where(CustomerIncident.ticket_id == ticket.id)
            inc = (await session.execute(inc_stmt)).scalar_one_or_none()

        if inc:
            event = IncidentEvent(
                incident_id=inc.id,
                event_type="LIFECYCLE_TRANSITION",
                from_status=curr_state.value,
                to_status=target_state_str,
                agent_role=agent_role,
                details={
                    "reason": reason,
                    "timestamp": now.isoformat(),
                    **(details or {})
                }
            )
            session.add(event)
            await session.flush()

            # Sync incident status
            if target_state == SupportLifecycleState.RESOLVED:
                inc.is_resolved = True
                inc.resolved_at = now
                inc.status = "RESOLVED"
            elif target_state == SupportLifecycleState.FIXING:
                inc.status = "REMEDIATING"
            elif target_state == SupportLifecycleState.VERIFYING:
                inc.status = "VERIFYING"

        logger.info(
            f"[SupportStateMachine] Ticket #{ticket.ticket_number} transitioned "
            f"'{curr_state.value}' -> '{target_state_str}' by {agent_role}: {reason}"
        )
        return ticket


support_state_machine = SupportStateMachine()
