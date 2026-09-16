"""
Agency OS — Persistent Knowledge Model & Epistemic Separation.
Provides atomic models and persistence helpers for ground-truth observations,
inferences, recommendations, and explainable intelligence summaries.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import KnowledgeFact


class SourceTier:
    OFFICIAL_DNS_REGISTRY = 1   # Confidence 0.99
    DIRECT_HTTP_AUDIT = 2       # Confidence 0.95
    SCRAPED_CONTENT = 3         # Confidence 0.85
    INFERRED_HEURISTIC = 4      # Confidence 0.60


def calculate_source_confidence(tier: int) -> float:
    """Assigns deterministic confidence score based on source verification tier."""
    if tier == SourceTier.OFFICIAL_DNS_REGISTRY:
        return 0.99
    elif tier == SourceTier.DIRECT_HTTP_AUDIT:
        return 0.95
    elif tier == SourceTier.SCRAPED_CONTENT:
        return 0.85
    return 0.60


class Observation(BaseModel):
    """
    Ground-truth observable fact with provenance and verifiable source.
    """
    id: str = Field(default_factory=lambda: f"obs_{uuid.uuid4().hex[:8]}")
    entity_type: str = "business"
    entity_id: str
    category: str
    fact_key: str
    fact_value: Dict[str, Any] = Field(default_factory=dict)
    source: str = "audit_engine"
    source_tier: int = SourceTier.DIRECT_HTTP_AUDIT
    confidence: float = 0.95
    raw_evidence: str = ""
    observed_at: datetime = Field(default_factory=datetime.utcnow)
    provenance: Dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **data):
        super().__init__(**data)
        if "confidence" not in data or data["confidence"] == 0.95:
            self.confidence = calculate_source_confidence(self.source_tier)


class Inference(BaseModel):
    """
    Deduction derived from one or more supporting ground-truth observations.
    """
    id: str = Field(default_factory=lambda: f"inf_{uuid.uuid4().hex[:8]}")
    entity_type: str = "business"
    entity_id: str
    category: str
    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_observation_keys: List[str] = Field(default_factory=list)
    risk_factor: str = "LOW"  # LOW, MEDIUM, HIGH
    reasoning: str


class Recommendation(BaseModel):
    """
    Concrete actionable solution or software deployment proposal.
    """
    id: str = Field(default_factory=lambda: f"rec_{uuid.uuid4().hex[:8]}")
    capability_id: str
    title: str
    description: str
    rationale: str
    expected_impact: str
    effort_days: int = 5
    target_price_usd: float = 1000.0
    confidence: float = 0.85
    prerequisites: List[str] = Field(default_factory=list)
    ceo_gate_required: bool = False


class ExplainableIntelligence(BaseModel):
    """
    Standardized explainable output detailing what was seen, what is believed,
    why it matters, what to do, and whether CEO human sign-off is mandatory.
    """
    observation: str
    belief: str
    rationale: str
    recommendation: str
    evidence: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    ceo_gate_required: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# Persistent Knowledge Operations
# ==============================================================================

async def store_fact(session: AsyncSession, observation: Observation) -> KnowledgeFact:
    """Persists an atomic observation to the KnowledgeFact database table."""
    fact = KnowledgeFact(
        entity_type=observation.entity_type,
        entity_id=str(observation.entity_id),
        category=observation.category,
        fact_key=observation.fact_key,
        fact_value=observation.fact_value,
        source=observation.source,
        confidence=observation.confidence,
        epistemic_status="OBSERVED_FACT",
        observed_at=observation.observed_at,
        provenance={
            **observation.provenance,
            "observation_id": observation.id,
            "raw_evidence": observation.raw_evidence,
            "source_tier": observation.source_tier,
        }
    )
    session.add(fact)
    await session.commit()
    await session.refresh(fact)
    return fact


async def store_batch_observations(
    session: AsyncSession,
    observations: List[Observation]
) -> List[KnowledgeFact]:
    """Atomically persists a collection of observations."""
    facts = []
    for obs in observations:
        fact = KnowledgeFact(
            entity_type=obs.entity_type,
            entity_id=str(obs.entity_id),
            category=obs.category,
            fact_key=obs.fact_key,
            fact_value=obs.fact_value,
            source=obs.source,
            confidence=obs.confidence,
            epistemic_status="OBSERVED_FACT",
            observed_at=obs.observed_at,
            provenance={
                **obs.provenance,
                "observation_id": obs.id,
                "raw_evidence": obs.raw_evidence,
                "source_tier": obs.source_tier,
            }
        )
        session.add(fact)
        facts.append(fact)
    await session.commit()
    return facts


async def get_facts_for_entity(
    session: AsyncSession,
    entity_type: str,
    entity_id: str,
    category: Optional[str] = None
) -> List[KnowledgeFact]:
    """Queries persistent knowledge facts for a target entity."""
    stmt = select(KnowledgeFact).where(
        KnowledgeFact.entity_type == entity_type,
        KnowledgeFact.entity_id == str(entity_id)
    )
    if category:
        stmt = stmt.where(KnowledgeFact.category == category)
    stmt = stmt.order_by(KnowledgeFact.observed_at.desc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def store_inference(session: AsyncSession, inference: Inference) -> KnowledgeFact:
    """Persists an epistemic inference to the KnowledgeFact database table."""
    fact = KnowledgeFact(
        entity_type=inference.entity_type,
        entity_id=str(inference.entity_id),
        category=inference.category,
        fact_key=f"inference_{inference.id}",
        fact_value={
            "hypothesis": inference.hypothesis,
            "reasoning": inference.reasoning,
            "risk_factor": inference.risk_factor,
            "supporting_keys": inference.supporting_observation_keys
        },
        source="inference_engine",
        confidence=inference.confidence,
        epistemic_status="INFERENCE",
        observed_at=datetime.utcnow(),
        provenance={"inference_id": inference.id}
    )
    session.add(fact)
    await session.commit()
    await session.refresh(fact)
    return fact


async def store_recommendation(session: AsyncSession, recommendation: Recommendation, entity_id: str) -> KnowledgeFact:
    """Persists an actionable recommendation to the KnowledgeFact database table."""
    fact = KnowledgeFact(
        entity_type="business",
        entity_id=str(entity_id),
        category="commercial_recommendation",
        fact_key=f"rec_{recommendation.capability_id}",
        fact_value={
            "capability_id": recommendation.capability_id,
            "title": recommendation.title,
            "description": recommendation.description,
            "rationale": recommendation.rationale,
            "expected_impact": recommendation.expected_impact,
            "target_price_usd": recommendation.target_price_usd,
            "ceo_gate_required": recommendation.ceo_gate_required
        },
        source="recommendation_engine",
        confidence=recommendation.confidence,
        epistemic_status="RECOMMENDATION",
        observed_at=datetime.utcnow(),
        provenance={"recommendation_id": recommendation.id}
    )
    session.add(fact)
    await session.commit()
    await session.refresh(fact)
    return fact


async def store_failure_pattern(
    session: AsyncSession,
    entity_id: str,
    failure_type: str,
    failure_signature: str,
    suggested_fix: str,
    occurrence_count: int = 1
) -> KnowledgeFact:
    """Persists a learned failure pattern to KnowledgeFact for continuous improvement."""
    fact = KnowledgeFact(
        entity_type="system_pattern",
        entity_id=str(entity_id),
        category="failure_pattern",
        fact_key=f"failure_{failure_type}_{failure_signature[:30]}",
        fact_value={
            "failure_type": failure_type,
            "signature": failure_signature,
            "suggested_fix": suggested_fix,
            "occurrence_count": occurrence_count
        },
        source="failure_learning_loop",
        confidence=min(0.99, 0.50 + (occurrence_count * 0.15)),
        epistemic_status="FAILURE_PATTERN",
        observed_at=datetime.utcnow(),
        provenance={"failure_type": failure_type}
    )
    session.add(fact)
    await session.commit()
    await session.refresh(fact)
    return fact
