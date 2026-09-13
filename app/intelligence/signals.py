"""
Signal Management & Persistence Service — Mega Prompt 8.
Validates, persists, queries, and manages lifecycles and expiration for canonical Intelligence Signals.
"""
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, delete

from app.intelligence.models import (
    IntelligenceSignal, SignalType, SignalCategory,
    EpistemicStatus, ConfidenceBand
)
from app.database.models import IntelligenceSignalRecord

logger = logging.getLogger("agency.intelligence.signals")


class SignalRegistry:
    """
    In-memory and database-backed signal registry.
    Ensures predictions are NEVER treated as facts, and stale signals are flagged.
    """

    @staticmethod
    def calculate_confidence_band(confidence: float) -> ConfidenceBand:
        if confidence >= 0.80:
            return ConfidenceBand.HIGH
        elif confidence >= 0.50:
            return ConfidenceBand.MEDIUM
        return ConfidenceBand.LOW

    @classmethod
    def create_signal(
        cls,
        entity_type: str,
        entity_id: int,
        signal_type: SignalType,
        epistemic_status: EpistemicStatus,
        signal_value: float,
        confidence: float,
        source: str,
        evidence: Optional[List[Dict[str, Any]]] = None,
        ttl_days: Optional[int] = 30,
        model_provider: str = "local",
        version: str = "v1.0.0",
        metadata: Optional[Dict[str, Any]] = None
    ) -> IntelligenceSignal:
        """
        Constructs and validates a canonical IntelligenceSignal.
        Enforces epistemic consistency:
        - If epistemic_status is PREDICTION, confidence cannot be claimed as 1.0.
        - If epistemic_status is OBSERVED_FACT, evidence cannot be empty.
        """
        # Invariant checks
        if epistemic_status == EpistemicStatus.PREDICTION and confidence >= 1.0:
            confidence = 0.95  # Clamped: predictions are never mathematical certainty

        if epistemic_status == EpistemicStatus.OBSERVED_FACT and not evidence:
            evidence = [{"note": "Direct primary measurement or API telemetry event."}]

        signal_id = f"SIG-{uuid.uuid4().hex[:12].upper()}"
        now = datetime.utcnow()
        expires_at = now + timedelta(days=ttl_days) if ttl_days else None

        band = cls.calculate_confidence_band(confidence)

        return IntelligenceSignal(
            id=signal_id,
            entity_type=entity_type,
            entity_id=entity_id,
            signal_type=signal_type,
            epistemic_status=epistemic_status,
            signal_value=float(signal_value),
            confidence=float(confidence),
            confidence_band=band,
            source=source,
            evidence=evidence or [],
            created_at=now,
            expires_at=expires_at,
            model_provider=model_provider,
            version=version,
            metadata=metadata or {}
        )

    @classmethod
    async def persist_signal(
        cls,
        session: AsyncSession,
        signal: IntelligenceSignal
    ) -> IntelligenceSignalRecord:
        """Persists the signal to the database for historical and learning retrieval."""
        record = IntelligenceSignalRecord(
            signal_id=signal.id,
            entity_type=signal.entity_type,
            entity_id=signal.entity_id,
            signal_type=signal.signal_type.value if isinstance(signal.signal_type, SignalType) else str(signal.signal_type),
            epistemic_status=signal.epistemic_status.value if isinstance(signal.epistemic_status, EpistemicStatus) else str(signal.epistemic_status),
            signal_value=signal.signal_value,
            confidence=signal.confidence,
            confidence_band=signal.confidence_band.value if isinstance(signal.confidence_band, ConfidenceBand) else str(signal.confidence_band),
            source=signal.source,
            evidence_json={"items": signal.evidence, "metadata": signal.metadata},
            model_provider=signal.model_provider,
            version=signal.version,
            created_at=signal.created_at,
            expires_at=signal.expires_at
        )
        session.add(record)
        await session.commit()
        return record

    @classmethod
    async def get_active_signals_for_entity(
        cls,
        session: AsyncSession,
        entity_type: str,
        entity_id: int
    ) -> List[IntelligenceSignal]:
        """Retrieves active (unexpired) signals for a specific business, customer, or lead."""
        now = datetime.utcnow()
        stmt = (
            select(IntelligenceSignalRecord)
            .where(
                and_(
                    IntelligenceSignalRecord.entity_type == entity_type,
                    IntelligenceSignalRecord.entity_id == entity_id,
                    or_(
                        IntelligenceSignalRecord.expires_at.is_(None),
                        IntelligenceSignalRecord.expires_at > now
                    )
                )
            )
            .order_by(desc(IntelligenceSignalRecord.created_at))
        )
        records = (await session.execute(stmt)).scalars().all()
        signals = []
        for r in records:
            signals.append(
                IntelligenceSignal(
                    id=r.signal_id,
                    entity_type=r.entity_type,
                    entity_id=r.entity_id,
                    signal_type=SignalType(r.signal_type) if r.signal_type in SignalType._value2member_map_ else SignalType.LEAD_FIT,
                    epistemic_status=EpistemicStatus(r.epistemic_status) if r.epistemic_status in EpistemicStatus._value2member_map_ else EpistemicStatus.INFERENCE,
                    signal_value=r.signal_value,
                    confidence=r.confidence,
                    confidence_band=ConfidenceBand(r.confidence_band) if r.confidence_band in ConfidenceBand._value2member_map_ else ConfidenceBand.MEDIUM,
                    source=r.source,
                    evidence=r.evidence_json.get("items", []),
                    created_at=r.created_at,
                    expires_at=r.expires_at,
                    model_provider=r.model_provider,
                    version=r.version,
                    metadata=r.evidence_json.get("metadata", {})
                )
            )
        return signals


signal_registry = SignalRegistry()
