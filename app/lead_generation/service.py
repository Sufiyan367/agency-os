import re
import logging
from typing import List, Tuple, Set, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.lead_generation.targeting import TargetingConfig
from app.lead_generation.schemas import (
    NormalizedBusinessRecord,
    DiscoveryStats,
    ScoredProspect,
    ProspectClassification
)
from app.lead_generation.providers.base import BaseLeadDiscoveryProvider
from app.lead_generation.providers.mock import MockLeadDiscoveryProvider
from app.lead_generation.buyer_scoring import HighValueBuyerScorer
from app.models.entities import LocalBusiness, LocalLead, LocalLeadEvent, EventType, LeadStatus

logger = logging.getLogger(__name__)

class LeadDiscoveryService:
    """
    Coordinates local business discovery, multi-vector deduplication,
    high-value buyer scoring, validation filtering, and database persistence.
    """

    def __init__(self, provider: Optional[BaseLeadDiscoveryProvider] = None):
        self.provider = provider or MockLeadDiscoveryProvider()

    @staticmethod
    def normalize_domain(url_or_domain: Optional[str]) -> Optional[str]:
        """Extracts and normalizes clean domain string (e.g. 'lonestarhvac.com')."""
        if not url_or_domain:
            return None
        clean = url_or_domain.lower().strip()
        clean = re.sub(r"^https?://", "", clean)
        clean = re.sub(r"^www\.", "", clean)
        clean = clean.split("/")[0].split("?")[0].strip()
        return clean if clean else None

    @staticmethod
    def normalize_phone(phone: Optional[str]) -> Optional[str]:
        """Extracts 10-digit US phone digits for deterministic deduplication."""
        if not phone:
            return None
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        return digits if len(digits) == 10 else digits if digits else None

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalizes business name by removing punctuation and extra whitespace."""
        clean = re.sub(r"[^a-zA-Z0-9\s]", "", name.lower())
        return " ".join(clean.split())

    async def discover_and_process(
        self,
        targeting: TargetingConfig,
        db: AsyncSession,
        check_existing_db: bool = True
    ) -> Tuple[List[LocalBusiness], DiscoveryStats]:
        """
        Executes discovery from provider, deduplicates across domain/phone/name,
        evaluates High-Value Buyer Score & Opportunity Score, filters, and persists.
        """
        raw_candidates = await self.provider.discover_businesses(targeting)
        total_discovered = len(raw_candidates)

        scorer = HighValueBuyerScorer(targeting.commercial)

        # In-memory deduplication tracking sets
        seen_domains: Set[str] = set()
        seen_phones: Set[str] = set()
        seen_name_city: Set[Tuple[str, str]] = set()

        # Query existing database to prevent re-inserting existing domains/phones
        if check_existing_db:
            existing_res = await db.execute(select(LocalBusiness))
            existing_businesses = existing_res.scalars().all()
            for eb in existing_businesses:
                if eb.domain:
                    seen_domains.add(eb.domain)
                if eb.phone:
                    p_norm = self.normalize_phone(eb.phone)
                    if p_norm:
                        seen_phones.add(p_norm)
                if eb.name and eb.city:
                    seen_name_city.add((self.normalize_name(eb.name), eb.city.lower()))

        valid_prospects: List[LocalBusiness] = []
        duplicates_removed = 0
        discarded_count = 0
        high_buyer_count = 0
        high_opp_count = 0
        priority_count = 0
        total_buyer_score = 0.0
        total_opp_score = 0.0

        with_websites = 0
        with_phones = 0
        cities_covered: Set[str] = set()

        for candidate in raw_candidates:
            # 1. Normalization
            norm_dom = self.normalize_domain(candidate.website)
            norm_phone = self.normalize_phone(candidate.phone)
            norm_name = self.normalize_name(candidate.business_name)
            city_key = candidate.city.lower()

            # 2. Multi-Vector Deduplication Check
            is_duplicate = False
            if norm_dom and norm_dom in seen_domains:
                is_duplicate = True
            elif norm_phone and norm_phone in seen_phones:
                is_duplicate = True
            elif (norm_name, city_key) in seen_name_city:
                is_duplicate = True

            if is_duplicate:
                duplicates_removed += 1
                continue

            # 3. Basic Targeting Filter Checks
            filters = targeting.filters
            if filters.require_website and not norm_dom:
                discarded_count += 1
                continue
            if filters.require_phone and not norm_phone:
                discarded_count += 1
                continue
            if candidate.rating is not None and (candidate.rating < filters.min_rating or candidate.rating > filters.max_rating):
                discarded_count += 1
                continue
            if candidate.review_count is not None and candidate.review_count < filters.min_reviews:
                discarded_count += 1
                continue

            # 4. Evaluate High-Value Buyer & Opportunity Scores
            scored: ScoredProspect = scorer.evaluate_prospect(candidate)

            if scored.classification == ProspectClassification.DISCARD:
                discarded_count += 1
                continue

            # Track Commercial Analytics
            if scored.buyer_score.score >= targeting.commercial.high_value_buyer_threshold:
                high_buyer_count += 1
            if scored.opportunity_score >= targeting.commercial.opportunity_score_threshold:
                high_opp_count += 1
            if scored.classification == ProspectClassification.PRIORITY_PROSPECT:
                priority_count += 1

            total_buyer_score += scored.buyer_score.score
            total_opp_score += scored.opportunity_score

            # Record in seen sets
            if norm_dom:
                seen_domains.add(norm_dom)
            if norm_phone:
                seen_phones.add(norm_phone)
            seen_name_city.add((norm_name, city_key))

            # Track counters
            if norm_dom:
                with_websites += 1
            if norm_phone:
                with_phones += 1
            cities_covered.add(candidate.city)

            # 5. Create and Persist LocalBusiness
            clean_domain = norm_dom or f"lead-{len(seen_domains)+1}.local"
            biz = LocalBusiness(
                name=candidate.business_name,
                domain=clean_domain,
                website_url=candidate.website or "",
                niche=candidate.category,
                address=candidate.address,
                city=candidate.city,
                state="TX",
                country=candidate.country,
                phone=candidate.phone,
                email=f"contact@{clean_domain}" if norm_dom else None,
                rating=candidate.rating,
                review_count=candidate.review_count,
                source=candidate.source,
                source_url=candidate.source_url
            )
            # Attach evaluation object for in-memory consumers
            biz._scored = scored
            db.add(biz)
            await db.flush()

            # 6. Create associated initial Lead record with Commercial Classification
            lead_status = (
                LeadStatus.QUALIFIED.value
                if scored.classification == ProspectClassification.PRIORITY_PROSPECT
                else LeadStatus.NEW.value
            )
            lead = LocalLead(
                business_id=biz.id,
                contact_name=f"Managing Partner ({candidate.business_name})",
                contact_email=biz.email or f"info@{clean_domain}",
                contact_phone=candidate.phone,
                status=lead_status,
                qualification=scored.classification.value,
                lead_score=scored.buyer_score.score,
                reasoning=scored.classification_rationale,
                pain_points=scored.buyer_score.opportunity_signals
            )
            db.add(lead)
            await db.flush()

            # 7. Record Audit Trail Event with Commercial Metrics
            event = LocalLeadEvent(
                lead_id=lead.id,
                event_type=EventType.LEAD_DISCOVERED.value,
                payload={
                    "business_name": biz.name,
                    "city": biz.city,
                    "rating": biz.rating,
                    "review_count": biz.review_count,
                    "buyer_score": scored.buyer_score.score,
                    "buyer_tier": scored.buyer_score.tier.value,
                    "estimated_service_budget": scored.buyer_score.estimated_service_budget,
                    "opportunity_score": scored.opportunity_score,
                    "classification": scored.classification.value,
                    "classification_rationale": scored.classification_rationale,
                    "buying_capacity_signals": scored.buyer_score.buying_capacity_signals,
                    "opportunity_signals": scored.buyer_score.opportunity_signals
                }
            )
            db.add(event)
            valid_prospects.append(biz)

        await db.commit()

        valid_count = len(valid_prospects)
        avg_buyer = round(total_buyer_score / valid_count, 1) if valid_count > 0 else 0.0
        avg_opp = round(total_opp_score / valid_count, 1) if valid_count > 0 else 0.0

        stats = DiscoveryStats(
            businesses_discovered=total_discovered,
            valid_businesses=valid_count,
            duplicates_removed=duplicates_removed,
            with_websites=with_websites,
            with_phone_numbers=with_phones,
            cities_covered=sorted(list(cities_covered)),
            high_value_buyer_candidates=high_buyer_count,
            high_opportunity_candidates=high_opp_count,
            priority_prospects=priority_count,
            discarded_prospects=discarded_count,
            average_buyer_score=avg_buyer,
            average_opportunity_score=avg_opp
        )

        logger.info(
            f"Discovery Run Finished: {stats.businesses_discovered} raw -> "
            f"{stats.valid_businesses} valid ({stats.duplicates_removed} duplicates, {stats.discarded_prospects} discarded, "
            f"{stats.priority_prospects} PRIORITY PROSPECTS)"
        )
        return valid_prospects, stats
