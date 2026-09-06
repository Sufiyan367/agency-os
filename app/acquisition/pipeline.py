import asyncio
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from app.acquisition.models import StandardizedProspect, CountryConfigDTO
from app.acquisition.providers.registry import discovery_registry
from app.lead_generation.verification import lead_verification_engine
from app.core.security import normalize_domain
from app.core.logging import logger

class CountryPipeline:
    """
    Dedicated discovery and research worker for a specific country.
    Operates independently and asynchronously within defined concurrency limits.
    """

    def __init__(self, config: CountryConfigDTO):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.concurrency_limit)
        self.country_code = config.country_code.upper()

    async def run_discovery(
        self,
        target_count: int = 5,
        niche: Optional[str] = None,
        exclude_domains: Optional[Set[str]] = None
    ) -> List[StandardizedProspect]:
        """
        Executes country-targeted prospect discovery and verification.
        Bounded by the country's configured concurrency limits.
        """
        if not self.config.enabled:
            logger.info(f"[CountryPipeline:{self.country_code}] Pipeline is disabled. Skipping.")
            return []

        async with self.semaphore:
            target_niche = niche or (self.config.target_niches[0] if self.config.target_niches else "local-services")
            cities = self.config.target_cities or []
            excluded = set(exclude_domains or [])

            logger.info(f"[CountryPipeline:{self.country_code}] Starting discovery for Niche='{target_niche}', Target={target_count}")

            # 1. Discover raw prospects via provider registry (with fallback)
            raw_prospects = await discovery_registry.execute_discovery_with_fallback(
                country_code=self.country_code,
                niche=target_niche,
                limit=target_count,
                cities=cities,
                exclude_domains=excluded
            )

            verified_prospects: List[StandardizedProspect] = []

            # 2. Run multi-vector verification
            for p in raw_prospects:
                norm_dom = normalize_domain(p.domain)
                if not norm_dom or norm_dom in excluded:
                    continue

                is_valid, reason, details = await lead_verification_engine.verify_lead(
                    norm_dom, p.website, p.public_email
                )

                p.verification_status = "VERIFIED" if is_valid else "REJECTED"
                p.evidence["verification_reason"] = reason
                p.evidence["verification_details"] = details
                p.confidence = 0.90 if is_valid else 0.40

                if is_valid:
                    p.audit_status = "READY_FOR_AUDIT"
                    verified_prospects.append(p)
                    excluded.add(norm_dom)

                if len(verified_prospects) >= target_count:
                    break

            logger.info(f"[CountryPipeline:{self.country_code}] Discovered {len(verified_prospects)} verified prospects.")
            return verified_prospects
