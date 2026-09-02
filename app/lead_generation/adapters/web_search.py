import httpx
from typing import List
from bs4 import BeautifulSoup
from app.lead_generation.adapters.base import BaseLeadDiscoveryAdapter, DiscoveredLeadRaw
from app.core.security import normalize_domain, is_safe_url
from app.core.logging import logger

class WebSearchDiscoveryAdapter(BaseLeadDiscoveryAdapter):
    """
    Discovers local businesses by searching public search engines / directories
    and extracting candidate websites and business names.
    """
    async def discover_leads(
        self, country_code: str, niche_slug: str, limit: int = 10
    ) -> List[DiscoveredLeadRaw]:
        query = f"{niche_slug.replace('-', ' ')} in {country_code} official website contact"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        leads: List[DiscoveredLeadRaw] = []
        
        # We attempt real search via DuckDuckGo HTML endpoint with graceful degradation
        try:
            url = f"https://html.duckduckgo.com/html/?q={query}"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.select(".result__url")
                    titles = soup.select(".result__title")
                    
                    for link_elem, title_elem in zip(links, titles):
                        raw_href = link_elem.get_text(strip=True)
                        title = title_elem.get_text(strip=True)
                        if not raw_href.startswith("http"):
                            raw_href = "https://" + raw_href

                        domain = normalize_domain(raw_href)
                        # Filter out global directory giants (yelp, yellowpages, tripadvisor, facebook, wikipedia)
                        if any(x in domain for x in ["duckduckgo", "yelp", "yellowpages", "facebook", "linkedin", "wikipedia", "tripadvisor"]):
                            continue
                            
                        safe, _ = is_safe_url(raw_href)
                        if safe and domain:
                            leads.append(
                                DiscoveredLeadRaw(
                                    name=title.split("-")[0].split("|")[0].strip(),
                                    domain=domain,
                                    website_url=f"https://{domain}",
                                    country=country_code,
                                    city="Regional Center",
                                    niche=niche_slug,
                                    public_email=None,
                                    email_status="unknown",
                                    source="duckduckgo_search",
                                    source_url=raw_href
                                )
                            )
                            if len(leads) >= limit:
                                break
        except Exception as e:
            logger.warning(f"Web search discovery encountered network note: {e}")
            
        return leads
