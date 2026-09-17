"""
Agency OS — Evidence Engine.
Enforces epistemic truthfulness:
- Strict segregation: OBSERVATION vs INFERENCE vs RECOMMENDATION.
- Grounded provenance: observation, source, timestamp, confidence.
- Prohibition against turning inference into fact or fabricating financial/operational metrics.
"""
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    OBSERVATION = "OBSERVATION"       # Verifiable ground truth directly observed from digital assets/APIs
    INFERENCE = "INFERENCE"           # Deductive interpretation supported by explicit observations
    RECOMMENDATION = "RECOMMENDATION" # Proposed Agency OS capability or workflow intervention


class EvidenceItem(BaseModel):
    """
    A grounded epistemic claim with full provenance and truthfulness tracking.
    """
    id: str
    claim_type: ClaimType
    statement: str
    source: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: List[str] = Field(default_factory=list)
    is_factual: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "claim_type": self.claim_type.value,
            "statement": self.statement,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "supporting_evidence": self.supporting_evidence,
            "is_factual": self.is_factual,
            "metadata": self.metadata
        }


class EvidenceEngine:
    """
    Epistemic engine preventing AI from presenting inferences as facts.
    """

    @classmethod
    def record_observation(
        cls,
        observation_id: str,
        statement: str,
        source: str,
        confidence: float = 0.95,
        supporting_evidence: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> EvidenceItem:
        """
        Records an empirical observation directly measured from web/audit/API.
        Always marked is_factual=True.
        """
        return EvidenceItem(
            id=observation_id,
            claim_type=ClaimType.OBSERVATION,
            statement=statement,
            source=source,
            confidence=min(1.0, max(0.0, confidence)),
            supporting_evidence=supporting_evidence or [],
            is_factual=True,
            metadata=metadata or {}
        )

    @classmethod
    def derive_inference(
        cls,
        inference_id: str,
        hypothesis: str,
        supporting_observations: List[EvidenceItem],
        reasoning: str,
        confidence_discount: float = 0.85
    ) -> EvidenceItem:
        """
        Derives an inference strictly grounded in supporting observations.
        Cannot be factual (is_factual=False). Confidence cannot exceed supporting observations.
        """
        if not supporting_observations:
            raise ValueError("Epistemic violation: Inferences must be grounded in at least one supporting observation.")

        # Inferences cannot be more confident than their weakest premise
        base_confidence = min(obs.confidence for obs in supporting_observations)
        effective_confidence = round(base_confidence * confidence_discount, 2)

        evidence_summaries = [
            f"[{obs.id}] {obs.statement} (Source: {obs.source}, conf={obs.confidence})"
            for obs in supporting_observations
        ]

        return EvidenceItem(
            id=inference_id,
            claim_type=ClaimType.INFERENCE,
            statement=hypothesis,
            source="rule_based_inference_engine",
            confidence=effective_confidence,
            supporting_evidence=evidence_summaries,
            is_factual=False,
            metadata={"reasoning": reasoning, "observation_ids": [o.id for o in supporting_observations]}
        )

    @classmethod
    def propose_recommendation(
        cls,
        recommendation_id: str,
        capability_id: str,
        recommendation_text: str,
        supporting_inferences: List[EvidenceItem],
        action_name: str
    ) -> EvidenceItem:
        """
        Synthesizes an actionable recommendation grounded in supporting inferences.
        Cannot be factual (is_factual=False).
        """
        if not supporting_inferences:
            raise ValueError("Epistemic violation: Recommendations must be grounded in supporting inferences.")

        avg_conf = sum(inf.confidence for inf in supporting_inferences) / len(supporting_inferences)
        rec_confidence = round(avg_conf * 0.90, 2)

        evidence_summaries = [
            f"[{inf.id}] {inf.statement} (conf={inf.confidence})"
            for inf in supporting_inferences
        ]

        return EvidenceItem(
            id=recommendation_id,
            claim_type=ClaimType.RECOMMENDATION,
            statement=recommendation_text,
            source="solution_catalog_matcher",
            confidence=rec_confidence,
            supporting_evidence=evidence_summaries,
            is_factual=False,
            metadata={"capability_id": capability_id, "action": action_name}
        )

    @classmethod
    def validate_claim_integrity(cls, item: EvidenceItem) -> Tuple[bool, Optional[str]]:
        """
        Audits an evidence item for epistemic truthfulness:
        - Inferences/Recommendations MUST NOT be labeled factual.
        - Factual claims MUST have non-empty source and positive confidence.
        """
        if item.claim_type in (ClaimType.INFERENCE, ClaimType.RECOMMENDATION) and item.is_factual:
            return False, f"Epistemic violation: Claim '{item.id}' of type '{item.claim_type.value}' cannot be marked as factual."
        if item.is_factual and not item.source:
            return False, f"Epistemic violation: Factual claim '{item.id}' lacks verified provenance source."
        if item.confidence <= 0.0 or item.confidence > 1.0:
            return False, f"Epistemic violation: Claim '{item.id}' has invalid confidence {item.confidence}."
        return True, None


evidence_engine = EvidenceEngine()
