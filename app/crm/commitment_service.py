"""
Commitment Tracking Service for Agency OS.

Maintains explicit, isolated commitments for each lead:
- Customer Commitments: e.g. "I'll check the demo tomorrow", "We will decide by Friday".
- Agency Commitments: e.g. "I'll send the proposal today", "I will prepare the audit".

Principles:
- Stored persistently in ProspectMemory.commitments (or database events).
- Status lifecycle: OPEN -> COMPLETED / MISSED / CANCELLED.
- Never invent due dates when none are explicitly stated.
"""
import uuid
import re
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import ProspectMemory, Business
from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType
from app.core.logging import logger


class CommitmentType(str, Enum):
    CUSTOMER = "CUSTOMER"
    AGENCY = "AGENCY"


class CommitmentStatus(str, Enum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"


class CommitmentService:
    """Service to track and manage Customer and Agency commitments per prospect."""

    @classmethod
    def detect_commitments_from_text(
        cls,
        text: str,
        speaker_type: str = "CUSTOMER"
    ) -> List[Dict[str, Any]]:
        """
        Deterministically detects commitments in conversational text.
        Extracts commitment description and optional due date if explicitly stated.
        Never invents due dates.
        """
        if not text:
            return []

        lower = text.lower()
        commitments: List[Dict[str, Any]] = []

        # Customer pattern examples: "I'll check...", "I will look at...", "we will review...", "let me see..."
        # Agency pattern examples: "I'll send...", "We will follow up...", "I will prepare..."
        patterns = [
            (r"(?:i'll|i will|we will|we'll)\s+(check|look at|review|test|view)\s+(?:the|your)?\s*([a-zA-Z0-9_\-\s]{2,40})", "review"),
            (r"(?:i'll|i will|we will|we'll)\s+(send|forward|share|email)\s+(?:the|our|your)?\s*([a-zA-Z0-9_\-\s]{2,40})", "send"),
            (r"(?:i'll|i will|we will|we'll)\s+(talk to|discuss with|ask)\s+(?:the|my|our)?\s*([a-zA-Z0-9_\-\s]{2,40})", "consult"),
            (r"(?:i'll|i will|we will|we'll)\s+(get back to you|circle back|reply)", "follow_up"),
            (r"(?:let me)\s+(check|review|look at|talk to)\s+([a-zA-Z0-9_\-\s]{2,40})", "review")
        ]

        # Extract due date if explicitly stated
        due_at = None
        now = datetime.utcnow()
        if "tomorrow" in lower:
            due_at = (now + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0).isoformat()
        elif "today" in lower or "this afternoon" in lower or "tonight" in lower:
            due_at = now.replace(hour=18, minute=0, second=0, microsecond=0).isoformat()
        elif "next week" in lower:
            due_at = (now + timedelta(days=7)).replace(hour=12, minute=0, second=0, microsecond=0).isoformat()
        elif "by friday" in lower:
            days_ahead = (4 - now.weekday()) % 7 or 7
            due_at = (now + timedelta(days=days_ahead)).replace(hour=17, minute=0, second=0, microsecond=0).isoformat()

        for pattern, action_type in patterns:
            match = re.search(pattern, lower)
            if match:
                desc = match.group(0).strip()
                commitments.append({
                    "description": desc,
                    "action_type": action_type,
                    "raw_statement": text.strip(),
                    "due_at": due_at
                })
                break  # avoid multiple duplicates from single sentence

        return commitments

    @classmethod
    async def add_commitment(
        cls,
        session: AsyncSession,
        *,
        business_id: int,
        commitment_type: CommitmentType | str,
        description: str,
        raw_statement: str = "",
        due_at: Optional[str] = None,
        source_event_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Adds a new commitment to the prospect's memory record."""
        q = select(ProspectMemory).where(ProspectMemory.business_id == business_id)
        memory = (await session.execute(q)).scalars().first()

        c_type = commitment_type.value if isinstance(commitment_type, CommitmentType) else str(commitment_type)
        commitment_id = f"cmt_{uuid.uuid4().hex[:8]}"

        record = {
            "id": commitment_id,
            "commitment_type": c_type,
            "description": description,
            "raw_statement": raw_statement or description,
            "due_at": due_at,
            "status": CommitmentStatus.OPEN.value,
            "source_event_id": source_event_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        if memory:
            existing = list(memory.commitments or [])
            existing.append(record)
            memory.commitments = existing
            flag_modified(memory, "commitments")
            memory.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(memory)

        await activity_broadcaster.record_event(
            session=session,
            run_id=f"CMT-{business_id}",
            event_type=AgentEventType.COMMITMENT_CREATED.value,
            message=f"New {c_type} commitment recorded for business #{business_id}: '{description}'",
            business_id=business_id,
            status="INFO",
            metadata_json=record
        )

        return record

    @classmethod
    async def update_commitment_status(
        cls,
        session: AsyncSession,
        *,
        business_id: int,
        commitment_id: str,
        status: CommitmentStatus | str
    ) -> Optional[Dict[str, Any]]:
        """Updates status of a commitment (OPEN, COMPLETED, MISSED, CANCELLED)."""
        q = select(ProspectMemory).where(ProspectMemory.business_id == business_id)
        memory = (await session.execute(q)).scalars().first()
        if not memory or not memory.commitments:
            return None

        status_str = status.value if isinstance(status, CommitmentStatus) else str(status)
        commitments = list(memory.commitments)
        updated_item = None

        for c in commitments:
            if c.get("id") == commitment_id:
                c["status"] = status_str
                c["updated_at"] = datetime.utcnow().isoformat()
                updated_item = c
                break

        if updated_item:
            memory.commitments = commitments
            flag_modified(memory, "commitments")
            memory.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(memory)

            event_type = AgentEventType.COMMITMENT_COMPLETED.value if status_str == CommitmentStatus.COMPLETED.value else AgentEventType.MEMORY_UPDATED.value
            await activity_broadcaster.record_event(
                session=session,
                run_id=f"CMT-{business_id}",
                event_type=event_type,
                message=f"Commitment {commitment_id} updated to {status_str} for business #{business_id}.",
                business_id=business_id,
                status="SUCCESS",
                metadata_json=updated_item
            )

        return updated_item

    @classmethod
    async def get_commitments(
        cls,
        session: AsyncSession,
        business_id: int,
        status: Optional[CommitmentStatus | str] = None,
        commitment_type: Optional[CommitmentType | str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves commitments filtered by optional status or type."""
        q = select(ProspectMemory).where(ProspectMemory.business_id == business_id)
        memory = (await session.execute(q)).scalars().first()
        if not memory or not memory.commitments:
            return []

        status_str = (status.value if isinstance(status, CommitmentStatus) else str(status)) if status else None
        type_str = (commitment_type.value if isinstance(commitment_type, CommitmentType) else str(commitment_type)) if commitment_type else None

        results = []
        for c in memory.commitments:
            if status_str and c.get("status") != status_str:
                continue
            if type_str and c.get("commitment_type") != type_str:
                continue
            results.append(c)

        return results


commitment_service = CommitmentService()
