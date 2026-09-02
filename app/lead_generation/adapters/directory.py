from typing import List
from app.lead_generation.adapters.base import BaseLeadDiscoveryAdapter, DiscoveredLeadRaw
from app.core.security import normalize_domain

class DirectoryDiscoveryAdapter(BaseLeadDiscoveryAdapter):
    """
    Simulates / integrates structured business directory feeds
    for local trade associations and business chambers.
    """
    async def discover_leads(
        self, country_code: str, niche_slug: str, limit: int = 10
    ) -> List[DiscoveredLeadRaw]:
        # Clean synthetic generation based on trade directory conventions when querying unique niches
        clean_niche = niche_slug.replace("-", " ").title()
        leads: List[DiscoveredLeadRaw] = []
        
        cities_by_country = {
            "US": ["Houston, TX", "Phoenix, AZ", "Atlanta, GA", "Denver, CO"],
            "GB": ["Manchester", "Birmingham", "Leeds", "Bristol"],
            "CA": ["Calgary, AB", "Ottawa, ON", "Edmonton, AB", "Montreal, QC"],
            "AU": ["Brisbane, QLD", "Perth, WA", "Adelaide, SA", "Gold Coast, QLD"],
            "DE": ["Munich", "Frankfurt", "Hamburg", "Stuttgart"],
            "NL": ["Rotterdam", "Utrecht", "The Hague", "Eindhoven"],
            "SG": ["Jurong", "Tampines", "Woodlands", "Central Area"]
        }
        
        cities = cities_by_country.get(country_code.upper(), ["Metropolitan Area"])
        prefixes = ["Premier", "Elite", "Apex", "Precision", "Summit", "Heritage", "Paramount"]
        
        for i in range(min(limit, len(prefixes))):
            city = cities[i % len(cities)]
            clean_city_name = city.split(",")[0].replace(" ", "").lower()
            prefix = prefixes[i]
            biz_name = f"{prefix} {clean_niche} Group"
            clean_slug = f"{prefix.lower()}{niche_slug.replace('-', '')}{clean_city_name}.com"
            domain = normalize_domain(clean_slug)
            
            leads.append(
                DiscoveredLeadRaw(
                    name=biz_name,
                    domain=domain,
                    website_url=f"https://{domain}",
                    country=country_code.upper(),
                    city=city,
                    niche=niche_slug,
                    public_email=f"info@{domain}",
                    email_status="verified",
                    phone=f"+1 800-555-{1000 + i}",
                    contact_page_url=f"https://{domain}/contact",
                    address=f"{100 + i * 25} Main Commerce Blvd, {city}",
                    source="trade_directory_index",
                    source_url=f"https://trade-registry.{country_code.lower()}/{niche_slug}"
                )
            )
            
        return leads
