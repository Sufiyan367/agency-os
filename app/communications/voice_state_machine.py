"""
Deterministic Voice Conversation State Machine — Phase 17.
Enforces strictly governed transitions across 15 conversation states.
Supports hydration, context persistence, and resumption of interrupted calls.
"""

from enum import Enum
from typing import Dict, Any, Optional, List, Set
from pydantic import BaseModel, Field
from datetime import datetime
from app.core.logging import logger

class VoiceCallState(str, Enum):
    CALL_INITIATED = "CALL_INITIATED"
    IDENTITY_CONFIRMED = "IDENTITY_CONFIRMED"
    DISCOVERY = "DISCOVERY"
    PAIN_QUALIFICATION = "PAIN_QUALIFICATION"
    SERVICE_EXPLANATION = "SERVICE_EXPLANATION"
    QUESTIONS = "QUESTIONS"
    OBJECTION_HANDLING = "OBJECTION_HANDLING"
    PRICE_DISCUSSION = "PRICE_DISCUSSION"
    NEGOTIATION = "NEGOTIATION"
    PROPOSAL_READY = "PROPOSAL_READY"
    PAYMENT_REQUESTED = "PAYMENT_REQUESTED"
    CALL_COMPLETED = "CALL_COMPLETED"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    DO_NOT_CONTACT = "DO_NOT_CONTACT"
    FAILED = "FAILED"


VALID_TRANSITIONS: Dict[VoiceCallState, Set[VoiceCallState]] = {
    VoiceCallState.CALL_INITIATED: {
        VoiceCallState.IDENTITY_CONFIRMED,
        VoiceCallState.DISCOVERY,
        VoiceCallState.PAIN_QUALIFICATION,
        VoiceCallState.SERVICE_EXPLANATION,
        VoiceCallState.QUESTIONS,
        VoiceCallState.OBJECTION_HANDLING,
        VoiceCallState.PRICE_DISCUSSION,
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.DO_NOT_CONTACT,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    VoiceCallState.IDENTITY_CONFIRMED: {
        VoiceCallState.DISCOVERY,
        VoiceCallState.PAIN_QUALIFICATION,
        VoiceCallState.SERVICE_EXPLANATION,
        VoiceCallState.QUESTIONS,
        VoiceCallState.OBJECTION_HANDLING,
        VoiceCallState.PRICE_DISCUSSION,
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.DO_NOT_CONTACT,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    VoiceCallState.DISCOVERY: {
        VoiceCallState.PAIN_QUALIFICATION,
        VoiceCallState.SERVICE_EXPLANATION,
        VoiceCallState.QUESTIONS,
        VoiceCallState.OBJECTION_HANDLING,
        VoiceCallState.PRICE_DISCUSSION,
        VoiceCallState.NEGOTIATION,
        VoiceCallState.PROPOSAL_READY,
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.DO_NOT_CONTACT,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    VoiceCallState.PAIN_QUALIFICATION: {
        VoiceCallState.SERVICE_EXPLANATION,
        VoiceCallState.QUESTIONS,
        VoiceCallState.OBJECTION_HANDLING,
        VoiceCallState.PROPOSAL_READY,
        VoiceCallState.DO_NOT_CONTACT,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    VoiceCallState.SERVICE_EXPLANATION: {
        VoiceCallState.QUESTIONS,
        VoiceCallState.OBJECTION_HANDLING,
        VoiceCallState.PRICE_DISCUSSION,
        VoiceCallState.PROPOSAL_READY,
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.DO_NOT_CONTACT,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    VoiceCallState.QUESTIONS: {
        VoiceCallState.SERVICE_EXPLANATION,
        VoiceCallState.OBJECTION_HANDLING,
        VoiceCallState.PRICE_DISCUSSION,
        VoiceCallState.PROPOSAL_READY,
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.DO_NOT_CONTACT,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    VoiceCallState.OBJECTION_HANDLING: {
        VoiceCallState.PRICE_DISCUSSION,
        VoiceCallState.NEGOTIATION,
        VoiceCallState.QUESTIONS,
        VoiceCallState.SERVICE_EXPLANATION,
        VoiceCallState.PROPOSAL_READY,
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.DO_NOT_CONTACT,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    VoiceCallState.PRICE_DISCUSSION: {
        VoiceCallState.NEGOTIATION,
        VoiceCallState.PROPOSAL_READY,
        VoiceCallState.OBJECTION_HANDLING,
        VoiceCallState.PAYMENT_REQUESTED,
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.DO_NOT_CONTACT,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    VoiceCallState.NEGOTIATION: {
        VoiceCallState.PROPOSAL_READY,
        VoiceCallState.PAYMENT_REQUESTED,
        VoiceCallState.PRICE_DISCUSSION,
        VoiceCallState.OBJECTION_HANDLING,
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.DO_NOT_CONTACT,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    VoiceCallState.PROPOSAL_READY: {
        VoiceCallState.PAYMENT_REQUESTED,
        VoiceCallState.NEGOTIATION,
        VoiceCallState.OBJECTION_HANDLING,
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.DO_NOT_CONTACT,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    VoiceCallState.PAYMENT_REQUESTED: {
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.HUMAN_ESCALATION,
        VoiceCallState.FAILED
    },
    # Terminal / Escaped states can be safely marked completed or failed
    VoiceCallState.HUMAN_ESCALATION: {
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.FAILED
    },
    VoiceCallState.DO_NOT_CONTACT: {
        VoiceCallState.CALL_COMPLETED,
        VoiceCallState.FAILED
    },
    VoiceCallState.CALL_COMPLETED: set(),
    VoiceCallState.FAILED: set()
}


class VoiceCallSession(BaseModel):
    call_sid: str
    business_id: Optional[int] = None
    recipient_phone: str
    current_state: VoiceCallState = VoiceCallState.CALL_INITIATED
    previous_state: Optional[VoiceCallState] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    offered_price: Optional[float] = None
    agreed_price: Optional[float] = None
    escalation_reason: Optional[str] = None
    proposal_id: Optional[int] = None
    payment_id: Optional[int] = None
    context: Dict[str, Any] = Field(default_factory=dict)

    def transition_to(self, new_state: VoiceCallState, reason: str = "") -> bool:
        """
        Executes a validated deterministic state transition.
        Raises ValueError on illegal transition.
        """
        if new_state == self.current_state:
            return True

        allowed = VALID_TRANSITIONS.get(self.current_state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Illegal voice state transition: '{self.current_state.value}' -> '{new_state.value}'. "
                f"Allowed destinations: {[s.value for s in allowed]}"
            )

        self.previous_state = self.current_state
        self.current_state = new_state
        self.updated_at = datetime.utcnow()

        self.history.append({
            "from_state": self.previous_state.value,
            "to_state": self.current_state.value,
            "timestamp": self.updated_at.isoformat(),
            "reason": reason
        })

        if new_state in (VoiceCallState.CALL_COMPLETED, VoiceCallState.FAILED, VoiceCallState.DO_NOT_CONTACT):
            self.completed_at = self.updated_at

        logger.info(f"[VoiceStateMachine] Call {self.call_sid}: {self.previous_state.value} -> {self.current_state.value} ({reason})")
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_sid": self.call_sid,
            "business_id": self.business_id,
            "recipient_phone": self.recipient_phone,
            "current_state": self.current_state.value,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "objections": self.objections,
            "offered_price": self.offered_price,
            "agreed_price": self.agreed_price,
            "escalation_reason": self.escalation_reason,
            "proposal_id": self.proposal_id,
            "payment_id": self.payment_id,
            "context": self.context
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceCallSession":
        session = cls(
            call_sid=data["call_sid"],
            business_id=data.get("business_id"),
            recipient_phone=data.get("recipient_phone", ""),
            current_state=VoiceCallState(data.get("current_state", VoiceCallState.CALL_INITIATED.value)),
            previous_state=VoiceCallState(data["previous_state"]) if data.get("previous_state") else None,
            objections=data.get("objections", []),
            offered_price=data.get("offered_price"),
            agreed_price=data.get("agreed_price"),
            escalation_reason=data.get("escalation_reason"),
            proposal_id=data.get("proposal_id"),
            payment_id=data.get("payment_id"),
            context=data.get("context", {})
        )
        return session
