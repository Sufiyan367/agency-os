"""
Commercial Objection Memory Service for Agency OS.

Persists commercial objections separately per lead:
- Normalized objection types: PRICE, TIMING, TRUST, ALREADY_HAVE_SOLUTION, NOT_INTERESTED, NEED_MORE_INFORMATION, OTHER.
- Tracks:
  - Exact supporting customer statement/event.
  - Normalized objection category.
  - Status (OPEN, RESOLVED, ABANDONED).
  - Resolution if later resolved.

Ensures future responses do not blindly repeat the same pitch.
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import ProspectMemory
from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType
from app.crm.objections import ObjectionCategory, objection_detector
from app.core.logging import logger


class NormalizedObjectionType(str, Enum):
    PRICE = "PRICE"
    TIMING = "TIMING"
    TRUST = "TRUST"
    ALREADY_HAVE_SOLUTION = "ALREADY_HAVE_SOLUTION"
    NOT_INTERESTED = "NOT_INTERESTED"
    NEED_MORE_INFORMATION = "NEED_MORE_INFORMATION"
    OTHER = "OTHER"


class ObjectionStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ABANDONED = "ABANDONED"


class ObjectionMemoryService:
    """Manages persistent structured objection tracking per prospect."""

    CATEGORY_MAPPING = {
        ObjectionCategory.PRICE_HIGH: NormalizedObjectionType.PRICE,
        ObjectionCategory.PRICE_LOW: NormalizedObjectionType.PRICE,
        ObjectionCategory.NO_BUDGET: NormalizedObjectionType.PRICE,
        ObjectionCategory.PAYMENT_CONCERN: NormalizedObjectionType.PRICE,
        ObjectionCategory.COMPETITOR_COMPARISON: NormalizedObjectionType.PRICE,

        ObjectionCategory.TIMING: NormalizedObjectionType.TIMING,
        ObjectionCategory.NOT_NOW: NormalizedObjectionType.TIMING,
        ObjectionCategory.NEED_TO_THINK: NormalizedObjectionType.TIMING,

        ObjectionCategory.TRUST_CONCERN: NormalizedObjectionType.TRUST,
        ObjectionCategory.NEED_PROOF: NormalizedObjectionType.TRUST,
        ObjectionCategory.NEED_CASE_STUDY: NormalizedObjectionType.TRUST,

        ObjectionCategory.ALREADY_HAVE_PROVIDER: NormalizedObjectionType.ALREADY_HAVE_SOLUTION,

        ObjectionCategory.NOT_INTERESTED: NormalizedObjectionType.NOT_INTERESTED,
        ObjectionCategory.OPT_OUT: NormalizedObjectionType.NOT_INTERESTED,

        ObjectionCategory.NEED_MORE_INFO: NormalizedObjectionType.NEED_MORE_INFORMATION,
        ObjectionCategory.SCOPE_CLARIFICATION: NormalizedObjectionType.NEED_MORE_INFORMATION,
        ObjectionCategory.NEED_OWNER_APPROVAL: NormalizedObjectionType.NEED_MORE_INFORMATION,
        ObjectionCategory.TECHNICAL_CONCERN: NormalizedObjectionType.NEED_MORE_INFORMATION,
    }

    @classmethod
    def normalize_category(cls, raw_category: str | ObjectionCategory) -> NormalizedObjectionType:
        """Maps an objection category into the normalized taxonomy."""
        if isinstance(raw_category, ObjectionCategory):
            return cls.CATEGORY_MAPPING.get(raw_category, NormalizedObjectionType.OTHER)
        try:
            enum_val = ObjectionCategory(raw_category)
            return cls.CATEGORY_MAPPING.get(enum_val, NormalizedObjectionType.OTHER)
        except Exception:
            upper = str(raw_category).upper()
            if "PRICE" in upper or "BUDGET" in upper or "COST" in upper:
                return NormalizedObjectionType.PRICE
            if "TIME" in upper or "LATER" in upper or "NOW" in upper:
                return NormalizedObjectionType.TIMING
            if "TRUST" in upper or "PROOF" in upper:
                return NormalizedObjectionType.TRUST
            if "PROVIDER" in upper or "AGENCY" in upper or "VENDOR" in upper or "HAVE" in upper:
                return NormalizedObjectionType.ALREADY_HAVE_SOLUTION
            if "INTEREST" in upper or "PASS" in upper or "UNSUB" in upper:
                return NormalizedObjectionType.NOT_INTERESTED
            if "INFO" in upper or "DETAILS" in upper or "QUESTION" in upper:
                return NormalizedObjectionType.NEED_MORE_INFORMATION
            return NormalizedObjectionType.OTHER

    @classmethod
    async def record_objection(
        cls,
        session: AsyncSession,
        *,
        business_id: int,
        objection_type: NormalizedObjectionType | str,
        statement: str,
        source_event_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records an objection for the prospect."""
        q = select(ProspectMemory).where(ProspectMemory.business_id == business_id)
        memory = (await session.execute(q)).scalars().first()

        norm_type = cls.normalize_category(objection_type).value
        obj_id = f"obj_{uuid.uuid4().hex[:8]}"

        record = {
            "id": obj_id,
            "objection_type": norm_type,
            "statement": statement.strip(),
            "status": ObjectionStatus.OPEN.value,
            "resolution": None,
            "source_event_id": source_event_id,
            "recorded_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        if memory:
            existing = list(memory.objection_history or [])
            # Avoid duplicate identical open objections
            is_dup = any(o.get("objection_type") == norm_type and o.get("status") == "OPEN" and o.get("statement") == statement.strip() for o in existing)
            if not is_dup:
                existing.append(record)
                memory.objection_history = existing
                flag_modified(memory, "objection_history")
                memory.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(memory)

        await activity_broadcaster.record_event(
            session=session,
            run_id=f"OBJ-{business_id}",
            event_type=AgentEventType.OBJECTION_DETECTED.value,
            message=f"Commercial objection ({norm_type}) detected for business #{business_id}: '{statement[:80]}...'",
            business_id=business_id,
            status="INFO",
            metadata_json=record
        )

        return record

    @classmethod
    async def resolve_objection(
        cls,
        session: AsyncSession,
        *,
        business_id: int,
        objection_id_or_type: str,
        resolution: str
    ) -> Optional[Dict[str, Any]]:
        """Marks an objection as resolved with explanation."""
        q = select(ProspectMemory).where(ProspectMemory.business_id == business_id)
        memory = (await session.execute(q)).scalars().first()
        if not memory or not memory.objection_history:
            return None

        history = list(memory.objection_history)
        resolved_item = None

        for o in history:
            if o.get("id") == objection_id_or_type or o.get("objection_type") == objection_id_or_type:
                if o.get("status") == ObjectionStatus.OPEN.value:
                    o["status"] = ObjectionStatus.RESOLVED.value
                    o["resolution"] = resolution
                    o["updated_at"] = datetime.utcnow().isoformat()
                    resolved_item = o
                    break

        if resolved_item:
            memory.objection_history = history
            flag_modified(memory, "objection_history")
            memory.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(memory)

            await activity_broadcaster.record_event(
                session=session,
                run_id=f"OBJ-{business_id}",
                event_type=AgentEventType.MEMORY_UPDATED.value,
                message=f"Objection {resolved_item.get('objection_type')} resolved for business #{business_id}.",
                business_id=business_id,
                status="SUCCESS",
                metadata_json=resolved_item
            )

        return resolved_item

    @classmethod
    async def get_active_objections(
        cls,
        session: AsyncSession,
        business_id: int
    ) -> List[Dict[str, Any]]:
        """Retrieves all open/unresolved objections for a prospect."""
        q = select(ProspectMemory).where(ProspectMemory.business_id == business_id)
        memory = (await session.execute(q)).scalars().first()
        if not memory or not memory.objection_history:
            return []

        return [o for o in memory.objection_history if o.get("status") == ObjectionStatus.OPEN.value]


objection_service = ObjectionMemoryService()
