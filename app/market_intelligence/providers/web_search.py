import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import quote_plus

from app.market_intelligence.providers.base import BaseMarketResearchProvider
from app.market_intelligence.models import RawEvidenceItem, EvidenceTier
from app.market_intelligence.cost_guard import market_cost_guard
from app.core.security import is_safe_url, normalize_domain
from app.core.logging import logger

class WebSearchMarketResearchProvider(BaseMarketResearchProvider):
    """
    Production public search provider using privacy-respecting search indices.
    Extracts authentic public excerpts, verifies domains, and adheres to SSRF safety.
    """

    def __init__(self, timeout_seconds: float = 8.0):
        self.timeout_seconds = timeout_seconds
        self._total_searches = 0
        self._successful_searches = 0
        self._failed_searches = 0

    @property
    def name(self) -> str:
        return "public_web_search"

    def is_available(self) -> bool:
        return True

    def get_health(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "status": "HEALTHY",
            "searches": self._total_searches,
            "successful": self._successful_searches,
            "failed": self._failed_searches
        }

    async def search_market_evidence(
        self,
        country_code: str,
        country_name: str,
        niche_slug: str,
        service_id: str,
        queries: List[str]
    ) -> List[RawEvidenceItem]:
        items: List[RawEvidenceItem] = []
        c = country_code.upper()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            for q in queries[:2]:  # Limit to 2 queries per call to protect rate limits and cost budget
                if not market_cost_guard.can_request():
                    logger.warning("[WebSearchProvider] Budget limit reached. Halting external requests.")
                    break

                self._total_searches += 1
                market_cost_guard.record_request()
                url = f"https://html.duckduckgo.com/html/?q={quote_plus(q)}"

                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        self._successful_searches += 1
                        soup = BeautifulSoup(resp.text, "html.parser")
                        results = soup.select(".result")

                        for r in results[:3]:
                            title_el = r.select_one(".result__title")
                            snippet_el = r.select_one(".result__snippet")
                            url_el = r.select_one(".result__url")

                            title = title_el.get_text(strip=True) if title_el else ""
                            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                            raw_url = url_el.get_text(strip=True) if url_el else ""

                            if not raw_url.startswith("http"):
                                raw_url = f"https://{raw_url}"

                            domain = normalize_domain(raw_url)
                            if not domain or any(skip in domain for x in ["duckduckgo", "facebook", "youtube", "tiktok"] if x in domain):
                                continue

                            safe, _ = is_safe_url(raw_url)
                            if not safe or len(snippet) < 10:
                                continue

                            items.append(
                                RawEvidenceItem(
                                    claim=f"{title}: {snippet[:150]}",
                                    source_url=raw_url,
                                    source_domain=domain,
                                    publisher=domain.split(".")[0].capitalize(),
                                    publication_date=datetime.utcnow(),
                                    raw_excerpt=snippet,
                                    signal_type="SERVICE_DEMAND",
                                    country_code=c,
                                    niche_slug=niche_slug,
                                    service_id=service_id,
                                    source_type="public_web",
                                    source_tier=EvidenceTier.TIER_3_PUBLIC_WEB.value,
                                    supports_claim=True,
                                    confidence=0.75
                                )
                            )
                except Exception as e:
                    self._failed_searches += 1
                    logger.debug(f"[WebSearchProvider] Search error for query '{q}': {e}")

        return items
