"""
Unified Event Bus & Idempotency Engine — Mega Prompt 9.
Guarantees event correlation, auditability, and deterministic deduplication.
"""
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Awaitable, Set
from pydantic import BaseModel, Field

logger = logging.getLogger("agency.event_bus")


class AgencyEvent(BaseModel):
    """Immutable, auditable lifecycle event."""
    event_id: str = Field(default_factory=lambda: f"EVT-{uuid.uuid4().hex[:10].upper()}")
    correlation_id: str = Field(default_factory=lambda: f"CORR-{uuid.uuid4().hex[:8].upper()}")
    idempotency_key: Optional[str] = None
    event_type: str  # e.g., LIFECYCLE_TRANSITION, OUTREACH_SENT, INBOUND_REPLY, PAYMENT_VERIFIED
    entity_type: str  # business, customer, project, incident, ticket
    entity_id: int
    actor: str = "system"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: str = "PROCESSED"


class UnifiedEventBus:
    """
    Central event coordinator enforcing deduplication, audit trails, and pub/sub.
    """

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self._subscribers: Dict[str, List[Callable[[AgencyEvent], Awaitable[None]]]] = {}
        self._processed_idempotency_keys: Set[str] = set()
        self._history: List[AgencyEvent] = []

    def subscribe(self, event_type: str, handler: Callable[[AgencyEvent], Awaitable[None]]):
        """Registers an asynchronous subscriber for a specific event type or wildcard '*'."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    async def publish(self, event: AgencyEvent) -> bool:
        """
        Publishes an event. If an idempotency_key is present and was already processed,
        the event is safely deduplicated and ignored. Returns True if processed, False if deduplicated.
        """
        if event.idempotency_key:
            if event.idempotency_key in self._processed_idempotency_keys:
                logger.info(f"[EventBus] Deduplicated duplicate event: {event.event_type} with key '{event.idempotency_key}'")
                return False
            self._processed_idempotency_keys.add(event.idempotency_key)

        # Record in in-memory history
        self._history.append(event)
        if len(self._history) > self.max_history:
            self._history.pop(0)

        # Dispatch to handlers
        handlers = self._subscribers.get(event.event_type, []) + self._subscribers.get("*", [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"[EventBus] Error in handler for {event.event_type}: {e}", exc_info=True)

        return True

    def is_processed(self, idempotency_key: str) -> bool:
        """Checks if a given idempotency key has already been executed."""
        return idempotency_key in self._processed_idempotency_keys

    def get_history(
        self,
        limit: int = 50,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None
    ) -> List[AgencyEvent]:
        """Returns recent events matching filters."""
        results = []
        for ev in reversed(self._history):
            if entity_type and ev.entity_type != entity_type:
                continue
            if entity_id is not None and ev.entity_id != entity_id:
                continue
            results.append(ev)
            if len(results) >= limit:
                break
        return results

    def clear(self):
        """Clears in-memory idempotency cache and history (for test isolation)."""
        self._processed_idempotency_keys.clear()
        self._history.clear()


# Global Singleton
event_bus = UnifiedEventBus()
