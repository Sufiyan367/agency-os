"""
Real-Time Agent Activity Event Broadcaster & Telemetry Persistence Layer.
Manages canonical observability events, persistent storage in SQLite,
and live WebSocket distribution to the dashboard.
"""
import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Set
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.database.models import AgentActivityEvent

logger = logging.getLogger("agency.activity")


class AgentEventType(str, Enum):
    # Lifecycle & Run
    RUN_STARTED = "RUN_STARTED"
    MARKET_SELECTED = "MARKET_SELECTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"

    # Single-Prospect Pipeline
    DISCOVERY_STARTED = "DISCOVERY_STARTED"
    PROSPECT_FOUND = "PROSPECT_FOUND"
    PROSPECT_DUPLICATE_SKIPPED = "PROSPECT_DUPLICATE_SKIPPED"

    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"

    AUDIT_STARTED = "AUDIT_STARTED"
    AUDIT_COMPLETED = "AUDIT_COMPLETED"

    SCORING_STARTED = "SCORING_STARTED"
    SCORING_COMPLETED = "SCORING_COMPLETED"

    COMMERCIAL_QUALIFICATION = "COMMERCIAL_QUALIFICATION"
    PROSPECT_DISQUALIFIED = "PROSPECT_DISQUALIFIED"

    COMPLIANCE_STARTED = "COMPLIANCE_STARTED"
    COMPLIANCE_PASSED = "COMPLIANCE_PASSED"
    COMPLIANCE_BLOCKED = "COMPLIANCE_BLOCKED"

    OFFER_GENERATION_STARTED = "OFFER_GENERATION_STARTED"
    OFFER_GENERATED = "OFFER_GENERATED"

    OUTREACH_DRAFT_STARTED = "OUTREACH_DRAFT_STARTED"
    OUTREACH_DRAFTED = "OUTREACH_DRAFTED"

    OUTREACH_DISPATCH_STARTED = "OUTREACH_DISPATCH_STARTED"
    OUTREACH_DISPATCHED = "OUTREACH_DISPATCHED"
    OUTREACH_FAILED = "OUTREACH_FAILED"

    MEMORY_PERSIST_STARTED = "MEMORY_PERSIST_STARTED"
    MEMORY_PERSISTED = "MEMORY_PERSISTED"

    NEXT_PROSPECT = "NEXT_PROSPECT"

    # Inbound Event & CRM
    INBOUND_EVENT_RECEIVED = "INBOUND_EVENT_RECEIVED"
    PROSPECT_MEMORY_RESTORED = "PROSPECT_MEMORY_RESTORED"
    REPLY_CLASSIFIED = "REPLY_CLASSIFIED"
    CONVERSATION_RESPONSE_GENERATED = "CONVERSATION_RESPONSE_GENERATED"

    # Website Build
    WEBSITE_BUILD_STARTED = "WEBSITE_BUILD_STARTED"
    WEBSITE_BUILD_PROGRESS = "WEBSITE_BUILD_PROGRESS"
    WEBSITE_BUILD_COMPLETED = "WEBSITE_BUILD_COMPLETED"
    WEBSITE_BUILD_FAILED = "WEBSITE_BUILD_FAILED"

    # Safety & Human Intervention
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"


class AgentActivityBroadcaster:
    """
    Central hub for recording, persisting, and streaming agent activity telemetry.
    Thread-safe and async compatible.
    """

    def __init__(self):
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._global_seq = 0

    async def register(self, websocket: WebSocket):
        """Registers a new connected WebSocket client."""
        async with self._lock:
            self._clients.add(websocket)
            logger.info(f"[ActivityBroadcaster] Client connected. Total active clients: {len(self._clients)}")

    async def unregister(self, websocket: WebSocket):
        """Unregisters a disconnected WebSocket client."""
        async with self._lock:
            self._clients.discard(websocket)
            logger.info(f"[ActivityBroadcaster] Client disconnected. Total active clients: {len(self._clients)}")

    def get_active_client_count(self) -> int:
        return len(self._clients)

    async def record_event(
        self,
        session: AsyncSession,
        run_id: str,
        event_type: str,
        message: str,
        business_id: Optional[int] = None,
        domain: Optional[str] = None,
        status: str = "INFO",
        metadata_json: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> AgentActivityEvent:
        """
        Persists an activity event to SQLite and broadcasts it in real-time to all connected WebSocket clients.
        """
        async with self._lock:
            self._global_seq += 1
            seq = self._global_seq

        clean_meta = metadata_json or {}
        now = datetime.utcnow()

        event = AgentActivityEvent(
            run_id=run_id,
            business_id=business_id,
            domain=domain,
            event_type=event_type,
            status=status,
            message=message,
            metadata_json=clean_meta,
            sequence_number=seq,
            error=error,
            created_at=now,
            completed_at=now if status in ("SUCCESS", "FAILED") else None
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)

        # Broadcast payload
        payload = {
            "id": event.id,
            "run_id": event.run_id,
            "business_id": event.business_id,
            "domain": event.domain,
            "event_type": event.event_type,
            "status": event.status,
            "message": event.message,
            "metadata_json": event.metadata_json,
            "sequence_number": event.sequence_number,
            "error": event.error,
            "created_at": event.created_at.isoformat(),
            "completed_at": event.completed_at.isoformat() if event.completed_at else None
        }

        asyncio.create_task(self._broadcast(payload))
        return event

    async def _broadcast(self, payload: Dict[str, Any]):
        """Dispatches event payload to all active WebSocket clients."""
        msg_str = json.dumps(payload)
        dead_clients = []
        clients_copy = list(self._clients)

        for client in clients_copy:
            try:
                await client.send_text(msg_str)
            except Exception as e:
                logger.debug(f"[ActivityBroadcaster] Send error to client: {e}")
                dead_clients.append(client)

        if dead_clients:
            async with self._lock:
                for dc in dead_clients:
                    self._clients.discard(dc)

    async def get_recent_events(
        self,
        session: AsyncSession,
        limit: int = 100,
        run_id: Optional[str] = None,
        since_seq: Optional[int] = None,
        business_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Queries persisted activity events with filtering."""
        q = select(AgentActivityEvent)
        if run_id:
            q = q.where(AgentActivityEvent.run_id == run_id)
        if since_seq is not None:
            q = q.where(AgentActivityEvent.sequence_number > since_seq)
        if business_id is not None:
            q = q.where(AgentActivityEvent.business_id == business_id)

        q = q.order_by(desc(AgentActivityEvent.sequence_number)).limit(limit)
        res = await session.execute(q)
        records = res.scalars().all()

        # Return in ascending sequence order for natural timeline rendering
        serialized = []
        for r in reversed(records):
            serialized.append({
                "id": r.id,
                "run_id": r.run_id,
                "business_id": r.business_id,
                "domain": r.domain,
                "event_type": r.event_type,
                "status": r.status,
                "message": r.message,
                "metadata_json": r.metadata_json or {},
                "sequence_number": r.sequence_number,
                "error": r.error,
                "created_at": r.created_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None
            })
        return serialized


# Global singleton instance
activity_broadcaster = AgentActivityBroadcaster()
