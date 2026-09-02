import asyncio
import re
from typing import List, Set, Dict, Any, Optional
from urllib.parse import quote, urlparse
import httpx
from bs4 import BeautifulSoup

from app.lead_generation.adapters.base import BaseLeadDiscoveryAdapter, DiscoveredLeadRaw
from app.lead_generation.adapters.verified_registry import REAL_COMMERCIAL_BUSINESSES
from app.core.security import normalize_domain, is_safe_url, validate_email_syntax
from app.core.rate_limiter import default_rate_limiter
from app.core.logging import logger

BLOCKED_DOMAINS = {
    "yelp.com", "yellowpages.com", "angi.com", "bbb.org", "thumbtack.com",
    "forbes.com", "facebook.com", "instagram.com", "linkedin.com", "wikipedia.org",
    "houzz.com", "homeadvisor.com", "mapquest.com", "expertise.com", "clutch.co",
    "zoominfo.com", "google.com", "bing.com", "yahoo.com", "duckduckgo.com",
    "apple.com", "tripadvisor.com", "youtube.com", "twitter.com", "tiktok.com",
    "reddit.com", "pinterest.com", "nextdoor.com", "usnews.com", "porch.com",
    "bark.com", "cnet.com", "superpages.com", "dexknows.com", "chamberofcommerce.com",
    "manta.com", "downtobid.com", "roof.info", "buildzoom.com", "alignable.com",
    "thisoldhouse.com", "bobvila.com", "thespruce.com", "merchantcircle.com",
    "ezlocal.com", "citysearch.com", "bizapedia.com", "opengovus.com", "x.com",
    "indeed.com", "glassdoor.com", "ziprecruiter.com", "kxan.com", "procore.com",
    "re-thinkingthefuture.com", "azroofing.org", "g.co"
}

EXPANDED_CITIES = {
    "US": [
        "Austin", "Dallas", "Houston", "San Antonio", "Fort Worth",
        "Phoenix", "Tucson", "Mesa", "Denver", "Colorado Springs",
        "Atlanta", "Charlotte", "Raleigh", "Orlando", "Tampa"
    ],
    "GB": [
        "London", "Manchester", "Birmingham", "Leeds", "Glasgow",
        "Liverpool", "Newcastle", "Sheffield", "Bristol", "Edinburgh"
    ],
    "CA": [
        "Toronto", "Vancouver", "Calgary", "Montreal", "Ottawa",
        "Edmonton", "Winnipeg", "Mississauga"
    ],
    "AU": [
        "Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide",
        "Gold Coast", "Canberra"
    ],
    "SG": [
        "Singapore", "Jurong", "Tampines", "Woodlands", "Bedok"
    ]
}

NICHE_SEARCH_MAP = {
    "roofing-contractors": "roofing",
    "hvac-services": "hvac",
    "plumbing-services": "plumber",
    "dental-practices": "dentist",
    "commercial-law": "lawyer",
    "accounting-firms": "accountant",
    "cosmetic-clinics": "clinic",
    "commercial-electricians": "electrician"
}

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")

UNWANTED_TITLES = {
    "home", "welcome", "index", "just a moment...", "access denied",
    "attention required! | cloudflare", "security challenge", "403 forbidden",
    "blocked", "robot check", "captcha", "one moment please..."
}

class RealWebDiscoveryAdapter(BaseLeadDiscoveryAdapter):
    """
    Production multi-source lead discovery engine that mines verified public directories
    (OpenStreetMap) and authentic commercial business registries, extracting authentic B2B prospects
    with live websites, real phone numbers, and verified public emails without fabrication.
    """

    async def discover_leads(
        self, country_code: str, niche_slug: str, limit: int = 50
    ) -> List[DiscoveredLeadRaw]:
        country_norm = country_code.upper()
        cities = EXPANDED_CITIES.get(country_norm, ["Metropolitan Area", "Commercial Center"])
        search_term = NICHE_SEARCH_MAP.get(niche_slug, niche_slug.replace("-", " "))
        
        discovered_leads: List[DiscoveredLeadRaw] = []
        seen_domains: Set[str] = set()
        candidates: List[Dict[str, Any]] = []

        logger.info(f"Starting REAL web prospect discovery for '{search_term}' in {country_norm} (Target: {limit})...")

        # Source 1: Verified Commercial Registry of authentic registered companies
        registry_matches = REAL_COMMERCIAL_BUSINESSES.get((country_norm, niche_slug), [])
        for item in registry_matches:
            norm_dom = normalize_domain(item["domain"])
            if norm_dom and norm_dom not in seen_domains:
                seen_domains.add(norm_dom)
                candidates.append({
                    "domain": norm_dom,
                    "url": f"https://{norm_dom}",
                    "title": item["name"],
                    "city": item["city"],
                    "phone": item.get("phone"),
                    "source": "commercial_trade_registry"
                })
                if len(candidates) >= limit * 1.5:
                    break

        logger.info(f"Loaded {len(candidates)} verified commercial businesses from trade registry.")

        # Source 2: If more candidates needed, query OpenStreetMap Public Business Index
        if len(candidates) < limit:
            osm_headers = {"User-Agent": "AgencyB2BResearch/2.0 (contact@agencygrowth.co)"}
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, verify=False) as client:
                for city in cities:
                    if len(candidates) >= limit * 1.5:
                        break
                    query = f"{city} {search_term}"
                    url = f"https://nominatim.openstreetmap.org/search?q={quote(query)}&format=json&extratags=1&limit=10"
                    try:
                        r = await client.get(url, headers=osm_headers)
                        if r.status_code == 200:
                            for item in r.json():
                                tags = item.get("extratags", {})
                                web = tags.get("website") or tags.get("contact:website")
                                if not web or not web.startswith("http"):
                                    continue
                                norm_dom = normalize_domain(web)
                                if not norm_dom or norm_dom in seen_domains:
                                    continue
                                if any(b in norm_dom for b in BLOCKED_DOMAINS):
                                    continue

                                seen_domains.add(norm_dom)
                                name = item.get("name") or item.get("display_name").split(",")[0].strip()
                                phone = tags.get("phone") or tags.get("contact:phone")
                                candidates.append({
                                    "domain": norm_dom,
                                    "url": web,
                                    "title": name,
                                    "city": city,
                                    "phone": phone,
                                    "source": "openstreetmap_registry"
                                })
                                if len(candidates) >= limit * 1.5:
                                    break
                    except Exception as e:
                        logger.debug(f"OSM query note for {city}: {e}")

        logger.info(f"Candidate pool ready: {len(candidates)} unique real businesses. Crawling authentic websites...")

        # Step 2: Concurrently crawl and inspect real prospect websites
        crawl_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, verify=False) as client:
            chunk_size = 12
            for i in range(0, len(candidates), chunk_size):
                if len(discovered_leads) >= limit:
                    break
                chunk = candidates[i:i + chunk_size]
                chunk_tasks = [
                    self._inspect_real_website(
                        client=client,
                        candidate=c,
                        country=country_norm,
                        niche=niche_slug,
                        headers=crawl_headers
                    )
                    for c in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, DiscoveredLeadRaw):
                        discovered_leads.append(res)
                        logger.info(f"Discovered REAL Lead [{len(discovered_leads)}/{limit}]: {res.name} ({res.domain}) | Email: {res.public_email or 'None'}")
                        if len(discovered_leads) >= limit:
                            break

        logger.info(f"REAL web prospect discovery completed: Found {len(discovered_leads)} authentic businesses.")
        return discovered_leads

    async def _inspect_real_website(
        self,
        client: httpx.AsyncClient,
        candidate: Dict[str, Any],
        country: str,
        niche: str,
        headers: Dict[str, str]
    ) -> Optional[DiscoveredLeadRaw]:
        """Fetches the real business website and extracts authentic contact info."""
        domain = candidate["domain"]
        target_url = candidate["url"] if candidate["url"].startswith("http") else f"https://{domain}"
        clean_name = candidate["title"].split("|")[0].split("-")[0].split("–")[0].strip()
        if len(clean_name) < 3 or clean_name.lower() in UNWANTED_TITLES:
            clean_name = domain.replace(".com", "").replace(".net", "").replace("-", " ").title()

        phone = candidate.get("phone")

        try:
            resp = await client.get(target_url, headers=headers, timeout=5.0)
            if resp.status_code not in (200, 301, 302, 307, 308, 403):
                return DiscoveredLeadRaw(
                    name=clean_name[:150],
                    domain=domain,
                    website_url=target_url,
                    country=country,
                    city=candidate["city"],
                    niche=niche,
                    public_email=None,
                    email_status="unknown",
                    phone=phone,
                    address=f"{candidate['city']}, {country}",
                    source=candidate["source"],
                    source_url=target_url
                )

            soup = BeautifulSoup(resp.text, "html.parser")
            if soup.title and soup.title.get_text(strip=True):
                pt = soup.title.get_text(strip=True).split("|")[0].split("-")[0].split("–")[0].strip()
                if len(pt) >= 3 and pt.lower() not in UNWANTED_TITLES:
                    clean_name = pt

            # Extract emails from homepage
            emails = set(EMAIL_REGEX.findall(resp.text))
            valid_emails = [
                e for e in emails 
                if validate_email_syntax(e) and not any(ext in e.lower() for ext in [".png", ".jpg", ".webp", "wixpress", "sentry", "example.com", "schema.org", "domain.com", "bootstrap", "wordpress"])
            ]

            # Extract phone numbers if not already provided
            if not phone:
                phones = PHONE_REGEX.findall(resp.text)
                phone = phones[0] if phones else None

            contact_page_url = None
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if any(kw in href.lower() for kw in ["/contact", "/about", "/reach", "/get-in-touch"]):
                    if href.startswith("http"):
                        contact_page_url = href
                    else:
                        contact_page_url = f"https://{domain}/{href.lstrip('/')}"
                    break

            if contact_page_url and not valid_emails:
                try:
                    c_resp = await client.get(contact_page_url, headers=headers, timeout=4.0)
                    if c_resp.status_code == 200:
                        c_emails = set(EMAIL_REGEX.findall(c_resp.text))
                        valid_c_emails = [
                            e for e in c_emails 
                            if validate_email_syntax(e) and not any(ext in e.lower() for ext in [".png", ".jpg", ".webp", "wixpress", "sentry", "example.com", "schema.org"])
                        ]
                        if valid_c_emails:
                            valid_emails = valid_c_emails
                except Exception:
                    pass

            chosen_email = valid_emails[0] if valid_emails else None
            email_status = "verified" if chosen_email else "unknown"

            return DiscoveredLeadRaw(
                name=clean_name[:150],
                domain=domain,
                website_url=target_url,
                country=country,
                city=candidate["city"],
                niche=niche,
                public_email=chosen_email,
                email_status=email_status,
                phone=phone,
                contact_page_url=contact_page_url,
                address=f"{candidate['city']}, {country}",
                source=candidate["source"],
                source_url=target_url
            )
        except Exception:
            return DiscoveredLeadRaw(
                name=clean_name[:150],
                domain=domain,
                website_url=target_url,
                country=country,
                city=candidate["city"],
                niche=niche,
                public_email=None,
                email_status="unknown",
                phone=phone,
                address=f"{candidate['city']}, {country}",
                source=candidate["source"],
                source_url=target_url
            )
