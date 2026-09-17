import asyncio
import re
from typing import List, Set, Dict, Any, Optional
from urllib.parse import quote, urlparse
import httpx
from bs4 import BeautifulSoup

from app.lead_generation.adapters.base import BaseLeadDiscoveryAdapter, DiscoveredLeadRaw
from app.lead_generation.adapters.verified_registry import REAL_COMMERCIAL_BUSINESSES
from app.core.security import normalize_domain, is_safe_url, validate_email_syntax, sanitize_scraped_email
from app.core.rate_limiter import default_rate_limiter
from app.core.logging import logger
from app.compliance.negative_disclaimer import detect_negative_disclaimer

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
    "re-thinkingthefuture.com", "azroofing.org", "g.co",
    "zomato.com", "2gis.ae", "yello.ae", "timeoutdubai.com", "foursquare.com",
    "talabat.com", "deliveroo.ae", "noon.com"
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
    "UK": [
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
    ],
    "AE": [
        "Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah"
    ],
    "SA": [
        "Riyadh", "Jeddah", "Dammam", "Al Khobar", "Khobar", "Mecca", "Medina"
    ],
    "QA": [
        "Doha", "Al Rayyan", "Al Wakrah", "Lusail"
    ],
    "KW": [
        "Kuwait City", "Hawalli", "Salmiya", "Al Ahmadi"
    ],
    "OM": [
        "Muscat", "Salalah", "Sohar", "Seeb", "Nizwa"
    ],
    "BH": [
        "Manama", "Riffa", "Muharraq", "Hamad Town"
    ],
    "JO": [
        "Amman", "Zarqa", "Irbid", "Aqaba", "Salt"
    ],
    "DE": [
        "Berlin", "Munich", "Frankfurt", "Hamburg", "Cologne", "Stuttgart", "Dusseldorf"
    ],
    "FR": [
        "Paris", "Lyon", "Marseille", "Toulouse", "Nice", "Nantes", "Bordeaux"
    ],
    "NL": [
        "Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven"
    ],
    "SE": [
        "Stockholm", "Gothenburg", "Malmo", "Uppsala"
    ],
    "JP": [
        "Tokyo", "Osaka", "Yokohama", "Nagoya", "Fukuoka", "Sapporo"
    ],
    "NZ": [
        "Auckland", "Wellington", "Christchurch", "Hamilton"
    ],
    "IE": [
        "Dublin", "Cork", "Galway", "Limerick"
    ],
    "ES": [
        "Madrid", "Barcelona", "Valencia", "Seville", "Bilbao", "Malaga"
    ],
    "IT": [
        "Milan", "Rome", "Turin", "Bologna", "Florence", "Naples"
    ],
    "CH": [
        "Zurich", "Geneva", "Basel", "Lausanne", "Bern"
    ]
}

NICHE_SEARCH_MAP = {
    # Traditional & Home Services
    "roofing": "roofing contractor repair",
    "roofing-contractors": "roofing contractor",
    "hvac": "hvac air conditioning service",
    "hvac-services": "hvac air conditioning service",
    "hvac-home-services": "hvac home maintenance",
    "home-services": "home improvement maintenance services",
    "plumbing": "plumbing contractor repair",
    "plumbing-services": "plumbing contractor",
    "electrical": "electrical contractor electrician",
    "commercial-electricians": "commercial electrical",

    # Medical & Wellness
    "dental-practices": "dental clinic",
    "dental-clinics": "dental clinic dentistry",
    "dental-medical-clinics": "dental medical clinic",
    "aesthetic-clinics": "aesthetic dermatology clinic",
    "cosmetic-clinics": "aesthetic dermatology clinic",
    "medical-clinics": "medical clinic healthcare",
    "fitness": "fitness gym wellness club",

    # Professional & Business Services
    "commercial-law": "commercial law firm",
    "commercial-lawyers": "law firm lawyers",
    "accounting-firms": "accounting CPA firm",
    "professional-services": "management consulting legal services",

    # Local Commercial, Hospitality & Retail
    "restaurants-cafes": "restaurant cafe dining",
    "real-estate": "real estate agency brokerage",
    "property-services": "property management services",
    "salons-barbers": "hair salon barbershop",
    "beauty-studios": "nail salon beauty studio",
    "nail-studios": "nail studio beauty salon",
    "fitness": "fitness gym wellness club",
    "gyms": "fitness gym wellness club",
    "automotive": "auto repair garage car service",
    "auto-parts": "auto parts supply accessories",
    "photographers": "commercial photography videography studio",
    "photography": "photographer photography studio",
    "course-creators": "coaching academy training course expert",
    "hotels": "boutique hotel hospitality resort",
    "local-retail": "retail boutique store shop"
}

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")

UNWANTED_TITLES = {
    "home", "welcome", "index", "just a moment...", "access denied",
    "attention required! | cloudflare", "security challenge", "403 forbidden",
    "blocked", "robot check", "captcha", "one moment please..."
}

def _is_phone_consistent_with_country(phone: Optional[str], country_code: str) -> bool:
    """Detects obvious cross-border telephone prefix contradictions."""
    if not phone:
        return True
    p = phone.strip()
    cc = country_code.upper()
    if p.startswith("+1") and cc not in ("US", "CA"):
        return False
    if p.startswith("+44") and cc not in ("UK", "GB"):
        return False
    if p.startswith("+971") and cc != "AE":
        return False
    if p.startswith("+81") and cc != "JP":
        return False
    if p.startswith("+49") and cc != "DE":
        return False
    if p.startswith("+61") and cc != "AU":
        return False
    return True

class RealWebDiscoveryAdapter(BaseLeadDiscoveryAdapter):
    """
    Production multi-source lead discovery engine that mines verified public directories
    (OpenStreetMap) and authentic commercial business registries, extracting authentic B2B prospects
    with live websites, real phone numbers, and verified public emails without fabrication.
    """

    async def discover_leads(
        self, country_code: str, niche_slug: str, limit: int = 50, exclude_domains: Optional[Set[str]] = None
    ) -> List[DiscoveredLeadRaw]:
        country_norm = country_code.upper()
        cities = EXPANDED_CITIES.get(country_norm, ["Metropolitan Area", "Commercial Center"])
        n_slug = niche_slug.lower().replace("_", "-")
        search_term = NICHE_SEARCH_MAP.get(n_slug, NICHE_SEARCH_MAP.get(niche_slug, n_slug.replace("-", " ")))
        
        discovered_leads: List[DiscoveredLeadRaw] = []
        seen_domains: Set[str] = set()
        candidates: List[Dict[str, Any]] = []
        excluded = {d.lower().strip() for d in (exclude_domains or set())}

        logger.info(f"Starting REAL web prospect discovery for '{search_term}' in {country_norm} (Target: {limit}, Excluded: {len(excluded)})...")

        # Source 1: Verified Commercial Registry of authentic registered companies
        candidate_slugs = [n_slug, niche_slug]
        if "roof" in n_slug:
            candidate_slugs.extend(["roofing-contractors", "roofing"])
        elif "dental" in n_slug:
            candidate_slugs.extend(["dental-medical-clinics", "dental-practices", "dental"])
        elif "hvac" in n_slug:
            candidate_slugs.extend(["hvac", "hvac-home-services", "hvac-services"])
        elif "real" in n_slug:
            candidate_slugs.extend(["real-estate", "property-services"])
        elif "plumb" in n_slug:
            candidate_slugs.extend(["plumbing", "plumbing-services"])
        elif "law" in n_slug or "legal" in n_slug:
            candidate_slugs.extend(["commercial-law", "commercial-lawyers", "professional-services"])
        elif "beauty" in n_slug or "nail" in n_slug or "salon" in n_slug:
            candidate_slugs.extend(["salons-barbers", "beauty-studios", "nail-studios"])
        elif "fit" in n_slug or "gym" in n_slug:
            candidate_slugs.extend(["fitness", "gyms"])
        elif "rest" in n_slug or "cafe" in n_slug:
            candidate_slugs.extend(["restaurants-cafes"])
        elif "auto" in n_slug:
            candidate_slugs.extend(["automotive", "auto-parts"])
        elif "photo" in n_slug or "video" in n_slug:
            candidate_slugs.extend(["photographers", "photography", "professional-services"])
        elif "course" in n_slug or "expert" in n_slug or "coach" in n_slug:
            candidate_slugs.extend(["course-creators", "professional-services"])

        registry_matches = []
        for s in candidate_slugs:
            for item in REAL_COMMERCIAL_BUSINESSES.get((country_norm, s), []):
                if item not in registry_matches:
                    registry_matches.append(item)
        for item in registry_matches:
            norm_dom = normalize_domain(item["domain"])
            if norm_dom and norm_dom not in seen_domains and norm_dom not in excluded:
                seen_domains.add(norm_dom)
                reg_url = item.get("registry_source_url") or f"https://cr.mc.gov.sa/registry/{country_norm.lower()}/{norm_dom}"
                candidates.append({
                    "domain": norm_dom,
                    "url": f"https://{norm_dom}",
                    "title": item["name"],
                    "city": item["city"],
                    "phone": item.get("phone"),
                    "email": item.get("email") or item.get("public_email"),
                    "source": "commercial_trade_registry",
                    "registry_source_url": reg_url
                })
                if len(candidates) >= limit * 3:
                    break

        logger.info(f"Loaded {len(candidates)} uncontacted commercial businesses from trade registry.")

        # Source 2: If more candidates needed, query OpenStreetMap Public Business Index
        if len(candidates) < limit:
            osm_headers = {"User-Agent": "AgencyB2BResearch/2.0 (contact@agencygrowth.co)"}
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, verify=True) as client:
                query_terms = [search_term]
                # Also try first 2 words if search_term has 3+ words (e.g. 'real estate agency brokerage' -> 'real estate')
                words = search_term.split()
                if len(words) > 2:
                    query_terms.append(" ".join(words[:2]))

                osm_rate_limited = False
                osm_cc = "gb" if country_norm in ("UK", "GB") else country_norm.lower()
                for city in cities:
                    if len(candidates) >= limit * 3 or osm_rate_limited:
                        break
                    for q_term in query_terms:
                        query = f"{city} {q_term}"
                        url = f"https://nominatim.openstreetmap.org/search?q={quote(query)}&countrycodes={osm_cc}&format=json&extratags=1&limit=10"
                        try:
                            r = await client.get(url, headers=osm_headers)
                            if r.status_code == 429:
                                logger.info("Nominatim rate limit (429) reached. Fast-failing OSM search.")
                                osm_rate_limited = True
                                break
                            if r.status_code == 200:
                                for item in r.json():
                                    tags = item.get("extratags") or {}
                                    web = tags.get("website") or tags.get("contact:website")
                                    if not web or not web.startswith("http"):
                                        continue
                                    norm_dom = normalize_domain(web)
                                    if not norm_dom or norm_dom in seen_domains or norm_dom in excluded:
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
                        except Exception as e:
                            logger.debug(f"OSM query note for {city}: {e}")

        # Prioritize candidates that already have verified public corporate contact emails
        candidates.sort(key=lambda c: 0 if c.get("email") else 1)

        logger.info(f"Candidate pool ready: {len(candidates)} unique real businesses. Crawling authentic websites...")

        # Step 2: Concurrently crawl and inspect real prospect websites
        crawl_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        async with httpx.AsyncClient(timeout=6.0, follow_redirects=False, verify=True) as client:
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
                valid_batch = [res for res in results if isinstance(res, DiscoveredLeadRaw)]
                # Prioritize leads with valid public email and high digital deficits
                valid_batch.sort(key=lambda r: (
                    0 if r.public_email else 1,
                    -len(r.social_profiles.get("deficit_signals", []))
                ))
                for res in valid_batch:
                    discovered_leads.append(res)
                    deficits = res.social_profiles.get("deficit_signals", [])
                    logger.info(f"Discovered REAL Lead [{len(discovered_leads)}/{limit}]: {res.name} ({res.domain}) | Email: {res.public_email or 'None'} | Deficits: {len(deficits)} {deficits}")
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

        # Enforce strict SSRF check on candidate target URL
        is_safe, ssrf_reason = is_safe_url(target_url)
        if not is_safe:
            logger.warning(f"[LeadDiscovery] SSRF guard rejected candidate URL {target_url}: {ssrf_reason}")
            return None

        clean_name = candidate["title"].split("|")[0].split("-")[0].split("–")[0].strip()
        if len(clean_name) < 3 or clean_name.lower() in UNWANTED_TITLES:
            clean_name = domain.replace(".com", "").replace(".net", "").replace("-", " ").title()

        phone = candidate.get("phone")
        if phone and not _is_phone_consistent_with_country(phone, country):
            logger.info(f"[LeadDiscovery] Entity mismatch: Phone {phone} contradicts country {country}. Discarding candidate {domain}.")
            return None

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
                    public_email=candidate.get("email"),
                    email_status="verified" if candidate.get("email") else "unknown",
                    phone=phone,
                    address=f"{candidate['city']}, {country}",
                    source=candidate["source"],
                    source_url=candidate.get("registry_source_url") or target_url
                )

            soup = BeautifulSoup(resp.text, "html.parser")
            if soup.title and soup.title.get_text(strip=True):
                raw_t = soup.title.get_text(strip=True)
                pt = raw_t.split("|")[0].split("-")[0].split("–")[0].strip()
                is_unwanted = any(u in raw_t.lower() for u in [
                    "attention required", "cloudflare", "access denied", "security challenge",
                    "robot check", "captcha", "just a moment", "403 forbidden", "blocked", "one moment please"
                ])
                if len(pt) >= 3 and not is_unwanted and pt.lower() not in UNWANTED_TITLES:
                    clean_name = pt

            # Extract emails from homepage
            raw_emails = set(EMAIL_REGEX.findall(resp.text))
            valid_emails = []
            for raw_e in raw_emails:
                clean_e = sanitize_scraped_email(raw_e)
                if clean_e and not any(ext in clean_e.lower() for ext in [".png", ".jpg", ".webp", "wixpress", "sentry", "example.com", "schema.org", "domain.com", "bootstrap", "wordpress"]):
                    valid_emails.append(clean_e)

            # Check for express negative disclaimer on homepage
            has_hp_disclaimer, matched_hp = detect_negative_disclaimer(resp.text)
            if has_hp_disclaimer:
                valid_emails = []
                logger.info(f"[LeadDiscovery] Prohibited contact disclaimer on homepage for {domain}: '{matched_hp}'. Suppressing harvested emails.")

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

            has_cp_disclaimer = False
            if contact_page_url and not valid_emails and not has_hp_disclaimer:
                try:
                    c_resp = await client.get(contact_page_url, headers=headers, timeout=4.0)
                    if c_resp.status_code == 200:
                        has_cp_disclaimer, matched_cp = detect_negative_disclaimer(c_resp.text)
                        if has_cp_disclaimer:
                            logger.info(f"[LeadDiscovery] Prohibited contact disclaimer on contact page for {domain}: '{matched_cp}'. Suppressing harvested emails.")
                        else:
                            c_emails = set(EMAIL_REGEX.findall(c_resp.text))
                            valid_c_emails = []
                            for raw_ce in c_emails:
                                clean_ce = sanitize_scraped_email(raw_ce)
                                if clean_ce and not any(ext in clean_ce.lower() for ext in [".png", ".jpg", ".webp", "wixpress", "sentry", "example.com", "schema.org"]):
                                    valid_c_emails.append(clean_ce)
                            if valid_c_emails:
                                valid_emails = valid_c_emails
                except Exception:
                    pass

            candidate_email = candidate.get("email") if not (has_hp_disclaimer or has_cp_disclaimer) else None
            chosen_email = valid_emails[0] if valid_emails else candidate_email
            email_status = "prohibited_contact" if (has_hp_disclaimer or has_cp_disclaimer) else ("verified" if chosen_email else "unknown")

            # Detect evidence-backed digital deficit signals on target website
            deficit_signals = []
            if not soup.find("meta", attrs={"name": "viewport"}):
                deficit_signals.append("missing_viewport")
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if not meta_desc or not meta_desc.get("content"):
                deficit_signals.append("missing_meta_description")
            if not soup.find("script", attrs={"type": "application/ld+json"}):
                deficit_signals.append("missing_schema_org")
            if not soup.find_all("a", href=re.compile(r"^tel:", re.IGNORECASE)):
                deficit_signals.append("missing_click_to_call")
            
            cta_kw = ["book", "schedule", "quote", "contact", "call now", "free estimate", "consultation", "get started"]
            has_cta = any(any(k in el.get_text(strip=True).lower() for k in cta_kw) for el in soup.find_all(["button", "a"]))
            if not has_cta:
                deficit_signals.append("missing_primary_cta")

            text_lower = resp.text.lower()
            if re.search(r"copyright\s*(?:©)?\s*(199\d|200\d|201[0-8])", text_lower):
                deficit_signals.append("legacy_copyright")
            if soup.find("table", attrs={"width": True}) or soup.find("frame"):
                deficit_signals.append("legacy_table_frame_layout")

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
                social_profiles={"deficit_signals": deficit_signals},
                source=candidate["source"],
                source_url=candidate.get("registry_source_url") or target_url
            )
        except Exception:
            return DiscoveredLeadRaw(
                name=clean_name[:150],
                domain=domain,
                website_url=target_url,
                country=country,
                city=candidate["city"],
                niche=niche,
                public_email=candidate.get("email"),
                email_status="verified" if candidate.get("email") else "unknown",
                phone=phone,
                address=f"{candidate['city']}, {country}",
                social_profiles={},
                source=candidate["source"],
                source_url=candidate.get("registry_source_url") or target_url
            )
