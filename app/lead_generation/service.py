import re
import logging
from typing import List, Tuple, Set, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.lead_generation.targeting import TargetingConfig
from app.lead_generation.schemas import (
    NormalizedBusinessRecord,
    DiscoveryStats,
    ScoredProspect,
    ProspectClassification,
    RejectionReason,
    EstimatedServiceValue
)
from app.lead_generation.providers.base import BaseLeadDiscoveryProvider
from app.lead_generation.providers.mock import MockLeadDiscoveryProvider
from app.lead_generation.providers.prospect_provider import BaseProspectProvider, MockProspectProvider
from app.lead_generation.buyer_scoring import HighValueBuyerScorer
from app.models.entities import LocalBusiness, LocalLead, LocalLeadEvent, EventType, LeadStatus

logger = logging.getLogger(__name__)

class ProspectQualityFilter:
    """
    Detects and rejects directory aggregators, social media profiles without business domains,
    parked/placeholder domains, and unformatted domains.
    """

    DIRECTORY_DOMAINS = {
        "yelp.com", "yellowpages.com", "angi.com", "bbb.org", "thumbtack.com",
        "forbes.com", "houzz.com", "homeadvisor.com", "mapquest.com", "expertise.com",
        "clutch.co", "zoominfo.com", "google.com", "bing.com", "yahoo.com",
        "duckduckgo.com", "tripadvisor.com", "bark.com", "superpages.com",
        "manta.com", "trustpilot.com", "chamberofcommerce.com", "usnews.com",
        "cnet.com", "buildzoom.com", "alignable.com", "merchantcircle.com",
        "ezlocal.com", "citysearch.com", "bizapedia.com", "porch.com", "dexknows.com",
        "opengovus.com", "re-thinkingthefuture.com", "downtobid.com"
    }

    SOCIAL_DOMAINS = {
        "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
        "youtube.com", "tiktok.com", "pinterest.com", "reddit.com", "nextdoor.com"
    }

    PARKED_DOMAINS = {
        "godaddy.com", "namecheap.com", "domainmarket.com", "sedo.com", "dan.com",
        "hugedomains.com", "example.com", "test.com", "myshopify.com", "wordpress.com",
        "wixsite.com"
    }

    @classmethod
    def check_validity(cls, domain: Optional[str], website: Optional[str]) -> Tuple[bool, Optional[RejectionReason]]:
        if not domain and not website:
            return False, RejectionReason.NON_BUSINESS_PAGE

        target = (domain or "").lower().strip()
        if not target and website:
            clean = re.sub(r"^https?://", "", website.lower())
            clean = re.sub(r"^www\.", "", clean)
            target = clean.split("/")[0].split("?")[0].strip()

        if not target:
            return False, RejectionReason.NON_BUSINESS_PAGE

        # Check directory aggregators
        for d in cls.DIRECTORY_DOMAINS:
            if target == d or target.endswith("." + d):
                return False, RejectionReason.DIRECTORY_AGGREGATOR

        # Check social profiles
        for s in cls.SOCIAL_DOMAINS:
            if target == s or target.endswith("." + s):
                return False, RejectionReason.SOCIAL_PROFILE

        # Check parked domains
        for p in cls.PARKED_DOMAINS:
            if target == p or target.endswith("." + p):
                return False, RejectionReason.PARKED_DOMAIN

        # Format validation
        if not re.match(r"^[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", target) or target.endswith("."):
            return False, RejectionReason.INACCESSIBLE_WEBSITE

        return True, None


class LeadDiscoveryService:
    """
    Coordinates local business discovery, multi-vector deduplication,
    junk/directory rejection, high-value buyer scoring, $1,000+ commercial qualification,
    and database persistence.
    """

    def __init__(self, provider: Optional[Any] = None):
        self.provider = provider or MockProspectProvider()

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
        """Extracts standard phone digits for deterministic deduplication."""
        if not phone:
            return None
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        return digits if len(digits) >= 7 else None

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
        filters junk/directories, evaluates High-Value Buyer Score & $1,000+ valuation, and persists.
        """
        if hasattr(self.provider, "discover_businesses"):
            raw_candidates = await self.provider.discover_businesses(targeting)
        elif hasattr(self.provider, "discover_prospects"):
            raw_candidates = []
            for city in targeting.cities:
                for niche in targeting.niches:
                    res = await self.provider.discover_prospects(
                        country=targeting.country_code,
                        city=city,
                        niche=niche,
                        limit=targeting.filters.target_results_per_city
                    )
                    raw_candidates.extend(res)
        else:
            raw_candidates = []

        total_discovered = len(raw_candidates)
        scorer = HighValueBuyerScorer(targeting.commercial)

        seen_domains: Set[str] = set()
        seen_phones: Set[str] = set()
        seen_name_city: Set[Tuple[str, str]] = set()

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
        invalid_rejected = 0
        discarded_count = 0
        high_buyer_count = 0
        high_opp_count = 0
        priority_count = 0
        thousand_plus_count = 0
        total_buyer_score = 0.0
        total_opp_score = 0.0
        rejection_reasons: Dict[str, int] = {}

        with_websites = 0
        with_phones = 0
        cities_covered: Set[str] = set()

        for candidate in raw_candidates:
            norm_dom = self.normalize_domain(candidate.website or candidate.domain)
            norm_phone = self.normalize_phone(candidate.phone)
            norm_name = self.normalize_name(candidate.business_name)
            city_key = candidate.city.lower()

            # 1. Quality & Junk Filter (Directories, Social Profiles, Parked Domains)
            is_valid_quality, reject_reason = ProspectQualityFilter.check_validity(norm_dom, candidate.website)
            if not is_valid_quality and reject_reason:
                invalid_rejected += 1
                r_key = reject_reason.value
                rejection_reasons[r_key] = rejection_reasons.get(r_key, 0) + 1
                continue

            # 2. Multi-Vector Deduplication
            is_duplicate = False
            dup_reason = None
            if norm_dom and norm_dom in seen_domains:
                is_duplicate = True
                dup_reason = RejectionReason.DUPLICATE_DOMAIN.value
            elif norm_phone and norm_phone in seen_phones:
                is_duplicate = True
                dup_reason = RejectionReason.DUPLICATE_PHONE.value
            elif (norm_name, city_key) in seen_name_city:
                is_duplicate = True
                dup_reason = RejectionReason.DUPLICATE_NAME_LOCATION.value

            if is_duplicate:
                duplicates_removed += 1
                rejection_reasons[dup_reason] = rejection_reasons.get(dup_reason, 0) + 1
                continue

            # 3. Basic Targeting Filter Checks
            filters = targeting.filters
            if filters.require_website and not norm_dom:
                invalid_rejected += 1
                rejection_reasons["MISSING_WEBSITE"] = rejection_reasons.get("MISSING_WEBSITE", 0) + 1
                continue
            if filters.require_phone and not norm_phone:
                discarded_count += 1
                rejection_reasons["MISSING_PHONE"] = rejection_reasons.get("MISSING_PHONE", 0) + 1
                continue
            if candidate.rating is not None and (candidate.rating < filters.min_rating or candidate.rating > filters.max_rating):
                discarded_count += 1
                rejection_reasons[RejectionReason.RATING_OUT_OF_BOUNDS.value] = rejection_reasons.get(RejectionReason.RATING_OUT_OF_BOUNDS.value, 0) + 1
                continue
            if candidate.review_count is not None and candidate.review_count < filters.min_reviews:
                discarded_count += 1
                rejection_reasons[RejectionReason.LOW_REVIEW_COUNT.value] = rejection_reasons.get(RejectionReason.LOW_REVIEW_COUNT.value, 0) + 1
                continue

            # 4. Evaluate High-Value Buyer, Opportunity Scores & $1,000+ Valuation
            scored: ScoredProspect = scorer.evaluate_prospect(candidate)

            if scored.classification == ProspectClassification.DISCARD:
                discarded_count += 1
                rejection_reasons[RejectionReason.NO_LEGITIMATE_CONTACT.value] = rejection_reasons.get(RejectionReason.NO_LEGITIMATE_CONTACT.value, 0) + 1
                continue

            # Track Commercial Analytics
            if scored.buyer_score.score >= targeting.commercial.high_value_buyer_threshold:
                high_buyer_count += 1
            if scored.opportunity_score >= targeting.commercial.opportunity_score_threshold:
                high_opp_count += 1
            if scored.estimated_service_value.min_value >= targeting.commercial.minimum_target_service_value_usd:
                thousand_plus_count += 1
            if scored.classification == ProspectClassification.PRIORITY_PROSPECT:
                priority_count += 1

            total_buyer_score += scored.buyer_score.score
            total_opp_score += scored.opportunity_score

            if norm_dom:
                seen_domains.add(norm_dom)
            if norm_phone:
                seen_phones.add(norm_phone)
            seen_name_city.add((norm_name, city_key))

            if norm_dom:
                with_websites += 1
            if norm_phone:
                with_phones += 1
            cities_covered.add(candidate.city)

            # 5. Persist LocalBusiness
            clean_domain = norm_dom or f"lead-{len(seen_domains)+1}.local"
            biz = LocalBusiness(
                name=candidate.business_name,
                domain=clean_domain,
                website_url=candidate.website or "",
                niche=candidate.category,
                address=candidate.address,
                city=candidate.city,
                state=candidate.region or "Regional",
                country=candidate.country,
                phone=candidate.phone,
                email=candidate.email if candidate.email else None,
                rating=candidate.rating,
                review_count=candidate.review_count,
                source=candidate.source,
                source_url=candidate.source_url
            )
            biz._scored = scored
            db.add(biz)
            await db.flush()

            # 6. Persist LocalLead with Commercial Valuation
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

            # 7. Record Audit Trail Event with Commercial Valuation Details
            event = LocalLeadEvent(
                lead_id=lead.id,
                event_type=EventType.LEAD_DISCOVERED.value,
                payload={
                    "business_name": biz.name,
                    "city": biz.city,
                    "country": biz.country,
                    "rating": biz.rating,
                    "review_count": biz.review_count,
                    "buyer_score": scored.buyer_score.score,
                    "buyer_tier": scored.buyer_score.tier.value,
                    "estimated_service_value": {
                        "min": scored.estimated_service_value.min_value,
                        "max": scored.estimated_service_value.max_value,
                        "currency": scored.estimated_service_value.currency,
                        "reasoning": scored.estimated_service_value.reasoning
                    },
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
            markets_searched=len(targeting.cities),
            businesses_discovered=total_discovered,
            valid_businesses=valid_count,
            duplicates_removed=duplicates_removed,
            invalid_rejected=invalid_rejected,
            websites_audited=valid_count,
            with_websites=with_websites,
            with_phone_numbers=with_phones,
            cities_covered=sorted(list(cities_covered)),
            high_value_buyer_candidates=high_buyer_count,
            high_opportunity_candidates=high_opp_count,
            priority_prospects=priority_count,
            thousand_plus_prospects=thousand_plus_count,
            discarded_prospects=discarded_count,
            average_buyer_score=avg_buyer,
            average_opportunity_score=avg_opp,
            rejection_reasons=rejection_reasons
        )

        logger.info(
            f"Prospecting Run Finished: {stats.businesses_discovered} raw -> "
            f"{stats.valid_businesses} valid ({stats.duplicates_removed} duplicates, "
            f"{stats.invalid_rejected} invalid junk, {stats.thousand_plus_prospects} $1,000+ prospects, "
            f"{stats.priority_prospects} PRIORITY PROSPECTS)"
        )
        return valid_prospects, stats
