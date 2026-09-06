import uuid
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models import MarketEvidence
from app.market_intelligence.models import RawEvidenceItem
from app.market_intelligence.source_quality import source_quality_classifier
from app.market_intelligence.evidence_freshness import evidence_freshness_calculator
from app.market_intelligence.evidence_validator import evidence_validator
from app.core.security import normalize_domain
from app.core.logging import logger

class EvidenceCollector:
    """Collects, persists, deduplicates, and resolves conflicting market evidence."""

    async def add_evidence(
        self, session: AsyncSession, item: RawEvidenceItem
    ) -> Tuple[Optional[MarketEvidence], bool]:
        """Adds a new verified market evidence record. Deduplicates by URL and claim."""
        valid, err = evidence_validator.validate(
            source_url=item.source_url,
            claim=item.claim,
            raw_excerpt=item.raw_excerpt,
            country_code=item.country_code,
            publication_date=item.publication_date,
            confidence=item.confidence
        )
        if not valid:
            logger.warning(f"[EvidenceCollector] Rejected invalid evidence: {err}")
            return None, False

        domain = normalize_domain(item.source_domain or item.source_url)
        tier, source_quality = source_quality_classifier.classify(domain)
        age_days, freshness, category = evidence_freshness_calculator.calculate(
            signal_type=item.signal_type,
            publication_date=item.publication_date
        )

        # Composite confidence: source quality x freshness x provider confidence
        confidence_score = round(source_quality * 0.4 + freshness * 0.3 + item.confidence * 0.3, 3)

        # Deduplication check
        stmt = select(MarketEvidence).where(
            and_(
                MarketEvidence.source_url == item.source_url,
                MarketEvidence.claim == item.claim
            )
        )
        existing = (await session.execute(stmt)).scalars().first()
        if existing:
            return existing, False

        record = MarketEvidence(
            evidence_id=f"EV-{uuid.uuid4().hex[:12].upper()}",
            country_code=item.country_code.upper(),
            niche_slug=item.niche_slug,
            service_id=item.service_id,
            claim=item.claim.strip(),
            source_url=item.source_url.strip(),
            source_domain=domain,
            source_type=item.source_type,
            source_tier=tier,
            publisher=item.publisher or domain,
            publication_date=item.publication_date,
            retrieved_at=datetime.utcnow(),
            raw_excerpt=item.raw_excerpt.strip(),
            signal_type=item.signal_type,
            source_quality_score=source_quality,
            freshness_score=freshness,
            confidence_score=confidence_score,
            supports_claim=item.supports_claim,
            contradicts_claim=item.contradicts_claim,
            metadata_json=item.metadata
        )
        session.add(record)
        await session.flush()
        return record, True

    async def get_evidence_for_opportunity(
        self,
        session: AsyncSession,
        country_code: str,
        niche_slug: Optional[str] = None,
        service_id: Optional[str] = None
    ) -> List[MarketEvidence]:
        """Retrieves all evidence associated with a country, niche, and service."""
        conditions = [MarketEvidence.country_code == country_code.upper()]
        if niche_slug:
            conditions.append(MarketEvidence.niche_slug.in_([niche_slug, None]))
        if service_id:
            conditions.append(MarketEvidence.service_id.in_([service_id, None]))

        stmt = select(MarketEvidence).where(and_(*conditions)).order_by(MarketEvidence.confidence_score.desc())
        res = await session.execute(stmt)
        return list(res.scalars().all())

    def resolve_conflicting_evidence(
        self, evidence_list: List[MarketEvidence]
    ) -> Tuple[float, str]:
        """
        Resolves contradictory claims through weighted confidence (source quality + freshness).
        Returns resolved value (0.0 to 1.0) and human-readable resolution explanation.
        """
        if not evidence_list:
            return 0.5, "No evidence available. Using conservative neutral prior (0.50)."

        supporting = [e for e in evidence_list if e.supports_claim and not e.contradicts_claim]
        contradicting = [e for e in evidence_list if e.contradicts_claim]

        if not contradicting:
            avg_conf = sum(e.confidence_score for e in supporting) / max(1, len(supporting))
            return round(min(1.0, 0.5 + 0.5 * avg_conf), 3), f"Unanimous consensus across {len(supporting)} independent source(s)."

        # Conflict resolution weighted by quality and freshness
        support_weight = sum(e.source_quality_score * e.freshness_score for e in supporting)
        contradict_weight = sum(e.source_quality_score * e.freshness_score for e in contradicting)
        total_weight = support_weight + contradict_weight

        if total_weight == 0:
            return 0.5, "Indeterminate conflict with zero confidence weights."

        net_support_ratio = support_weight / total_weight
        resolved_value = round(net_support_ratio, 3)

        explanation = (
            f"Resolved conflict between {len(supporting)} supporting sources (weight: {support_weight:.2f}) "
            f"and {len(contradicting)} contradicting sources (weight: {contradict_weight:.2f}). "
            f"Higher-tier and fresher evidence prioritized net score to {resolved_value:.2f}."
        )
        return resolved_value, explanation

evidence_collector = EvidenceCollector()
