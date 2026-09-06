from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Business, ProspectEvidence, PipelineStage, VerificationStatus
from app.core.logging import logger

MIN_VERIFIED_SOURCES = 2
MIN_EFFECTIVE_SCORE = 0.60


class GateEvaluationResult(BaseModel):
    """Structured evaluation output from ProspectEvidenceGate."""
    is_passed: bool
    status: str  # 'VERIFIED' or 'INSUFFICIENT_EVIDENCE'
    reason: str
    evidence_count: int
    distinct_sources_count: int
    effective_evidence_score: float
    evidence_confidence: float
    source_tiers_present: List[int] = Field(default_factory=list)
    can_outreach: bool
    can_auto_approve: bool
    details: Dict[str, Any] = Field(default_factory=dict)


class ProspectEvidenceGate:
    """
    Hard empirical evidence verification gate for acquired prospects.
    Enforces that zero-evidence, single-source, or weak-evidence prospects
    CANNOT become contactable, enter the commercial outreach queue, or receive auto-approval.
    """

    def evaluate_evidence(
        self,
        evidence_items: List[ProspectEvidence]
    ) -> GateEvaluationResult:
        """
        Pure deterministic evaluation of collected evidence items against strict validation rules.
        """
        if not evidence_items:
            logger.info("[ProspectEvidenceGate] Hard gate failed: 0 evidence items found.")
            return GateEvaluationResult(
                is_passed=False,
                status="INSUFFICIENT_EVIDENCE",
                reason="Zero verified evidence items found for prospect.",
                evidence_count=0,
                distinct_sources_count=0,
                effective_evidence_score=0.0,
                evidence_confidence=0.0,
                source_tiers_present=[],
                can_outreach=False,
                can_auto_approve=False,
                details={"failure_code": "ZERO_EVIDENCE"}
            )

        valid_items: List[ProspectEvidence] = []
        distinct_domains: Set[str] = set()
        distinct_types: Set[str] = set()
        tiers_present: List[int] = []

        for item in evidence_items:
            # 1. Verification flag check
            if not getattr(item, "is_verified", True):
                continue

            # 2. Explicit rejection or unreachable check
            v_status = getattr(item, "verification_status", "VERIFIED")
            if v_status in ("UNREACHABLE", "REJECTED"):
                continue
            if v_status == "UNVERIFIED" and not getattr(item, "is_verified", False):
                continue

            # 3. HTTP status check (must be 200)
            http_st = getattr(item, "http_status", 200)
            if http_st is not None and http_st != 200:
                continue

            # 4. Business identity match check (explicit False means wrong company)
            id_match = getattr(item, "business_identity_match", None)
            if id_match is False:
                continue

            src_url = getattr(item, "source_url", "") or ""
            claim = getattr(item, "claim", "") or ""
            if not src_url.strip() or not claim.strip():
                continue

            valid_items.append(item)
            domain = (getattr(item, "source_domain", "") or "").lower().strip()
            # Group by independence group or domain to guarantee distinct public sources
            group = getattr(item, "source_independence_group", None) or domain
            if group:
                distinct_domains.add(group)
            stype = getattr(item, "source_type", "") or "public_web"
            distinct_types.add(stype)
            tier = getattr(item, "source_tier", 3) or 3
            tiers_present.append(tier)

        ev_count = len(valid_items)
        # Distinct sources strictly required independent domains/entities
        distinct_sources_count = len(distinct_domains)

        if ev_count == 0:
            return GateEvaluationResult(
                is_passed=False,
                status="INSUFFICIENT_EVIDENCE",
                reason="No valid verified claims after strict provenance inspection.",
                evidence_count=0,
                distinct_sources_count=0,
                effective_evidence_score=0.0,
                evidence_confidence=0.0,
                source_tiers_present=[],
                can_outreach=False,
                can_auto_approve=False,
                details={"failure_code": "NO_VALID_CLAIMS"}
            )

        if ev_count < MIN_VERIFIED_SOURCES or distinct_sources_count < MIN_VERIFIED_SOURCES:
            logger.info(f"[ProspectEvidenceGate] Hard gate failed: {ev_count} items across {distinct_sources_count} distinct sources (< {MIN_VERIFIED_SOURCES}).")
            return GateEvaluationResult(
                is_passed=False,
                status="INSUFFICIENT_EVIDENCE",
                reason=f"Insufficient independent evidence sources ({distinct_sources_count}/{MIN_VERIFIED_SOURCES} required).",
                evidence_count=ev_count,
                distinct_sources_count=distinct_sources_count,
                effective_evidence_score=0.30,
                evidence_confidence=0.40,
                source_tiers_present=sorted(list(set(tiers_present))),
                can_outreach=False,
                can_auto_approve=False,
                details={
                    "failure_code": "INSUFFICIENT_SOURCES",
                    "distinct_domains": list(distinct_domains),
                    "distinct_types": list(distinct_types)
                }
            )


        weighted_scores: List[float] = []
        confidences: List[float] = []

        for item in valid_items:
            conf_val = getattr(item, "confidence_score", None)
            conf = float(conf_val) if conf_val is not None else 0.5
            sq_val = getattr(item, "source_quality_score", None)
            sq = float(sq_val) if sq_val is not None else 0.5
            fresh_val = getattr(item, "freshness_score", None)
            fresh = float(fresh_val) if fresh_val is not None else 1.0
            tier_val = getattr(item, "source_tier", None)
            tier = int(tier_val) if tier_val is not None else 3

            tier_bonus = 0.15 if tier == 1 else (0.08 if tier == 2 else 0.0)
            item_score = min(1.0, (conf * 0.45 + sq * 0.35 + fresh * 0.20) + tier_bonus)

            weighted_scores.append(item_score)
            confidences.append(conf)

        avg_effective_score = round(sum(weighted_scores) / len(weighted_scores), 3)
        avg_confidence = round(sum(confidences) / len(confidences), 3)

        if avg_effective_score < MIN_EFFECTIVE_SCORE:
            logger.info(f"[ProspectEvidenceGate] Hard gate failed: effective score {avg_effective_score:.2f} < {MIN_EFFECTIVE_SCORE}.")
            return GateEvaluationResult(
                is_passed=False,
                status="INSUFFICIENT_EVIDENCE",
                reason=f"Effective evidence score ({avg_effective_score:.2f}) below required threshold ({MIN_EFFECTIVE_SCORE:.2f}).",
                evidence_count=ev_count,
                distinct_sources_count=distinct_sources_count,
                effective_evidence_score=avg_effective_score,
                evidence_confidence=avg_confidence,
                source_tiers_present=sorted(list(set(tiers_present))),
                can_outreach=False,
                can_auto_approve=False,
                details={
                    "failure_code": "LOW_EVIDENCE_SCORE",
                    "score": avg_effective_score,
                    "threshold": MIN_EFFECTIVE_SCORE
                }
            )

        logger.info(f"[ProspectEvidenceGate] Hard gate PASSED: {ev_count} items, {distinct_sources_count} sources, score={avg_effective_score:.2f}.")
        return GateEvaluationResult(
            is_passed=True,
            status="VERIFIED",
            reason=f"Passed hard evidence gate with {ev_count} verified items across {distinct_sources_count} sources (score: {avg_effective_score:.2f}).",
            evidence_count=ev_count,
            distinct_sources_count=distinct_sources_count,
            effective_evidence_score=avg_effective_score,
            evidence_confidence=avg_confidence,
            source_tiers_present=sorted(list(set(tiers_present))),
            can_outreach=True,
            can_auto_approve=True,
            details={
                "distinct_domains": list(distinct_domains),
                "distinct_types": list(distinct_types),
                "has_tier_1_or_2": any(t in (1, 2) for t in tiers_present)
            }
        )

    async def evaluate_and_apply(
        self,
        session: AsyncSession,
        business: Business
    ) -> GateEvaluationResult:
        ev_stmt = select(ProspectEvidence).where(ProspectEvidence.business_id == business.id)
        ev_res = await session.execute(ev_stmt)
        evidence_items = list(ev_res.scalars().all())

        gate_result = self.evaluate_evidence(evidence_items)

        business.evidence_count = gate_result.evidence_count
        business.effective_evidence_score = gate_result.effective_evidence_score
        business.evidence_confidence = gate_result.evidence_confidence

        if gate_result.is_passed:
            business.verification_status = VerificationStatus.VERIFIED.value
            business.research_status = "VERIFIED"
        else:
            business.verification_status = "INSUFFICIENT_EVIDENCE"
            business.research_status = "RESEARCH_REQUIRED"
            if business.pipeline_stage in [PipelineStage.VERIFIED.value, PipelineStage.AUDITED.value, PipelineStage.QUALIFIED.value]:
                business.pipeline_stage = PipelineStage.DISCOVERED.value

        session.add(business)
        await session.flush()
        return gate_result


prospect_evidence_gate = ProspectEvidenceGate()
