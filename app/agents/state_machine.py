"""
Autonomous Revenue Agent State Machine.
Defines every discrete lifecycle state, valid transitions, and transition audit records.
"""
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class ProspectState(str, Enum):
    DISCOVER = "DISCOVER"
    AUDIT = "AUDIT"
    SCORE = "SCORE"
    CONTACT_DISCOVERY = "CONTACT_DISCOVERY"
    OUTREACH_PREP = "OUTREACH_PREP"
    OUTREACH_PENDING = "OUTREACH_PENDING"
    CONTACTED = "CONTACTED"
    WAITING_RESPONSE = "WAITING_RESPONSE"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    CONVERSATION = "CONVERSATION"
    QUALIFIED = "QUALIFIED"
    MEETING_READY = "MEETING_READY"
    PROPOSAL_READY = "PROPOSAL_READY"
    PAYMENT_READY = "PAYMENT_READY"
    WON = "WON"
    LOST = "LOST"
    SKIPPED = "SKIPPED"
    REJECTED = "REJECTED"
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"


class StateTransitionRecord(BaseModel):
    prospect_id: Optional[int] = None
    business_name: str
    previous_state: Optional[ProspectState] = None
    new_state: ProspectState
    reason: str
    confidence: float = 1.0
    action_taken: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentStateMachine:
    """Manages explicit state progression for a single prospect."""

    VALID_TRANSITIONS: Dict[ProspectState, List[ProspectState]] = {
        ProspectState.DISCOVER: [ProspectState.AUDIT, ProspectState.SKIPPED, ProspectState.REJECTED],
        ProspectState.AUDIT: [ProspectState.SCORE, ProspectState.SKIPPED, ProspectState.REJECTED],
        ProspectState.SCORE: [ProspectState.CONTACT_DISCOVERY, ProspectState.SKIPPED, ProspectState.REJECTED],
        ProspectState.CONTACT_DISCOVERY: [ProspectState.OUTREACH_PREP, ProspectState.SKIPPED, ProspectState.REJECTED],
        ProspectState.OUTREACH_PREP: [ProspectState.OUTREACH_PENDING, ProspectState.CONTACTED, ProspectState.SKIPPED, ProspectState.REJECTED],
        ProspectState.OUTREACH_PENDING: [ProspectState.CONTACTED, ProspectState.SKIPPED, ProspectState.REJECTED, ProspectState.HUMAN_TAKEOVER],
        ProspectState.CONTACTED: [ProspectState.WAITING_RESPONSE, ProspectState.SKIPPED, ProspectState.REJECTED],
        ProspectState.WAITING_RESPONSE: [ProspectState.RESPONSE_RECEIVED, ProspectState.LOST, ProspectState.HUMAN_TAKEOVER],
        ProspectState.RESPONSE_RECEIVED: [ProspectState.CONVERSATION, ProspectState.HUMAN_TAKEOVER, ProspectState.LOST],
        ProspectState.CONVERSATION: [ProspectState.QUALIFIED, ProspectState.HUMAN_TAKEOVER, ProspectState.LOST],
        ProspectState.QUALIFIED: [ProspectState.MEETING_READY, ProspectState.PROPOSAL_READY, ProspectState.HUMAN_TAKEOVER],
        ProspectState.MEETING_READY: [ProspectState.PROPOSAL_READY, ProspectState.WON, ProspectState.LOST, ProspectState.HUMAN_TAKEOVER],
        ProspectState.PROPOSAL_READY: [ProspectState.PAYMENT_READY, ProspectState.WON, ProspectState.LOST, ProspectState.HUMAN_TAKEOVER],
        ProspectState.PAYMENT_READY: [ProspectState.WON, ProspectState.LOST, ProspectState.HUMAN_TAKEOVER],
        ProspectState.WON: [],
        ProspectState.LOST: [],
        ProspectState.SKIPPED: [],
        ProspectState.REJECTED: [],
        ProspectState.HUMAN_TAKEOVER: [ProspectState.CONVERSATION, ProspectState.QUALIFIED, ProspectState.WON, ProspectState.LOST]
    }

    @classmethod
    def can_transition(cls, current: ProspectState, next_state: ProspectState) -> bool:
        allowed = cls.VALID_TRANSITIONS.get(current, [])
        return next_state in allowed
