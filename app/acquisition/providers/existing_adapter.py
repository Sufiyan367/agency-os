from typing import List, Dict, Any, Optional, Set
from app.acquisition.providers.base import BaseDiscoveryProvider
from app.acquisition.models import StandardizedProspect
from app.lead_generation.adapters.real_web_discovery import RealWebDiscoveryAdapter
from app.lead_generation.adapters.web_search import WebSearchDiscoveryAdapter
from app.core.security import normalize_domain
from app.core.logging import logger

class ExistingDiscoveryAdapterProvider(BaseDiscoveryProvider):
    """
    Discovery provider wrapping existing public web search adapters
    (RealWebDiscoveryAdapter & WebSearchDiscoveryAdapter).
    """

    def __init__(self):
        self.real_adapter = RealWebDiscoveryAdapter()
        self.web_search_adapter = WebSearchDiscoveryAdapter()
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0

    @property
    def name(self) -> str:
        return "existing_web_search"

    def is_available(self) -> bool:
        return True

    def get_health(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "status": "HEALTHY",
            "available": True,
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests
        }

    async def discover_prospects(
        self,
        country_code: str,
        niche: str,
        limit: int = 10,
        cities: Optional[List[str]] = None,
        exclude_domains: Optional[Set[str]] = None
    ) -> List[StandardizedProspect]:
        self._total_requests += 1
        normalized_country = "GB" if country_code.upper() in ("UK", "GB") else country_code.upper()
        excluded = set(exclude_domains or [])
        results: List[StandardizedProspect] = []

        try:
            # 1. Primary real web discovery adapter
            leads = await self.real_adapter.discover_leads(
                country_code=normalized_country,
                niche_slug=niche,
                limit=limit,
                exclude_domains=excluded
            )
            for l in leads:
                norm_dom = normalize_domain(l.domain)
                if norm_dom and norm_dom not in excluded:
                    results.append(StandardizedProspect(
                        business_name=l.name,
                        website=l.website_url,
                        domain=norm_dom,
                        country=country_code.upper(),
                        city=l.city,
                        niche=l.niche or niche,
                        public_email=l.public_email,
                        public_phone=l.phone,
                        discovery_source="real_web_discovery",
                        verification_status="VERIFIED",
                        confidence=0.88,
                        evidence={
                            "source_url": l.source_url,
                            "contact_page_url": l.contact_page_url,
                            "address": l.address,
                            "social_profiles": l.social_profiles
                        },
                        contactability=80.0 if l.public_email else 40.0,
                        audit_status="PENDING",
                        raw_signals={"source": l.source}
                    ))
                    excluded.add(norm_dom)

            # 2. If needed, supplement with web search adapter
            if len(results) < limit:
                needed = limit - len(results)
                supp_leads = await self.web_search_adapter.discover_leads(
                    country_code=normalized_country,
                    niche_slug=niche,
                    limit=needed,
                    exclude_domains=excluded
                )
                for l in supp_leads:
                    norm_dom = normalize_domain(l.domain)
                    if norm_dom and norm_dom not in excluded:
                        results.append(StandardizedProspect(
                            business_name=l.name,
                            website=l.website_url,
                            domain=norm_dom,
                            country=country_code.upper(),
                            city=l.city,
                            niche=l.niche or niche,
                            public_email=l.public_email,
                            public_phone=l.phone,
                            discovery_source="web_search",
                            verification_status="VERIFIED",
                            confidence=0.82,
                            evidence={"source_url": l.source_url},
                            contactability=75.0 if l.public_email else 35.0,
                            audit_status="PENDING"
                        ))
                        excluded.add(norm_dom)

            self._successful_requests += 1
            return results[:limit]

        except Exception as e:
            self._failed_requests += 1
            logger.warning(f"[ExistingDiscoveryProvider] Error in discovery for {country_code}/{niche}: {e}")
            return results
