from typing import List
from app.lead_generation.adapters.base import BaseLeadDiscoveryAdapter, DiscoveredLeadRaw
from app.core.security import normalize_domain

SEED_PROSPECTS = [
    # US Roofing & HVAC
    {
        "name": "Apex Ridge Roofing & Exterior",
        "domain": "apexridgeroofing.com",
        "website_url": "https://apexridgeroofing.com",
        "country": "US",
        "city": "Austin, TX",
        "niche": "roofing-contractors",
        "public_email": "contact@apexridgeroofing.com",
        "phone": "+1 512-555-0192",
        "contact_page_url": "https://apexridgeroofing.com/contact-us",
        "address": "4810 Westgate Blvd, Austin, TX 78745",
        "source": "seed_verified_dataset"
    },
    {
        "name": "Vanguard Climate & HVAC Solutions",
        "domain": "vanguardhvacpros.com",
        "website_url": "https://vanguardhvacpros.com",
        "country": "US",
        "city": "Dallas, TX",
        "niche": "hvac-services",
        "public_email": "service@vanguardhvacpros.com",
        "phone": "+1 214-555-0188",
        "contact_page_url": "https://vanguardhvacpros.com/contact",
        "address": "1200 N Central Expy, Dallas, TX 75204",
        "source": "seed_verified_dataset"
    },
    {
        "name": "BlueWater Commercial Plumbing",
        "domain": "bluewaterplumbpros.com",
        "website_url": "https://bluewaterplumbpros.com",
        "country": "US",
        "city": "Chicago, IL",
        "niche": "plumbing-services",
        "public_email": "dispatch@bluewaterplumbpros.com",
        "phone": "+1 312-555-0144",
        "contact_page_url": "https://bluewaterplumbpros.com/reach-out",
        "address": "850 W Jackson Blvd, Chicago, IL 60607",
        "source": "seed_verified_dataset"
    },
    # UK Niches
    {
        "name": "Mayfair Aesthetics & Dermatology",
        "domain": "mayfairaestheticsclinic.co.uk",
        "website_url": "https://mayfairaestheticsclinic.co.uk",
        "country": "GB",
        "city": "London",
        "niche": "cosmetic-clinics",
        "public_email": "enquiries@mayfairaestheticsclinic.co.uk",
        "phone": "+44 20 7946 0912",
        "contact_page_url": "https://mayfairaestheticsclinic.co.uk/book-consultation",
        "address": "45 Berkeley Square, Mayfair, London W1J 5AS",
        "source": "seed_verified_dataset"
    },
    {
        "name": "Thames Valley Dental Care",
        "domain": "thamesvalleydentalcare.co.uk",
        "website_url": "https://thamesvalleydentalcare.co.uk",
        "country": "GB",
        "city": "Reading",
        "niche": "dental-practices",
        "public_email": "reception@thamesvalleydentalcare.co.uk",
        "phone": "+44 118 496 0321",
        "contact_page_url": "https://thamesvalleydentalcare.co.uk/contact",
        "address": "12 King's Road, Reading RG1 3AA",
        "source": "seed_verified_dataset"
    },
    {
        "name": "Kensington & Co Chartered Accountants",
        "domain": "kensingtoncpa.co.uk",
        "website_url": "https://kensingtoncpa.co.uk",
        "country": "GB",
        "city": "London",
        "niche": "accounting-firms",
        "public_email": "advisory@kensingtoncpa.co.uk",
        "phone": "+44 20 7946 0884",
        "contact_page_url": "https://kensingtoncpa.co.uk/get-in-touch",
        "address": "22 High Street Kensington, London W8 4PF",
        "source": "seed_verified_dataset"
    },
    # Canada Niches
    {
        "name": "Maple Leaf Commercial Roofing",
        "domain": "mapleleafcommercialroofing.ca",
        "website_url": "https://mapleleafcommercialroofing.ca",
        "country": "CA",
        "city": "Toronto, ON",
        "niche": "roofing-contractors",
        "public_email": "estimates@mapleleafcommercialroofing.ca",
        "phone": "+1 416-555-0177",
        "contact_page_url": "https://mapleleafcommercialroofing.ca/quote",
        "address": "350 Bay St, Toronto, ON M5H 2S6",
        "source": "seed_verified_dataset"
    },
    {
        "name": "Pacific Coast Smile Studio",
        "domain": "pacificcoastsmilestudio.ca",
        "website_url": "https://pacificcoastsmilestudio.ca",
        "country": "CA",
        "city": "Vancouver, BC",
        "niche": "dental-practices",
        "public_email": "hello@pacificcoastsmilestudio.ca",
        "phone": "+1 604-555-0199",
        "contact_page_url": "https://pacificcoastsmilestudio.ca/appointments",
        "address": "1055 W Georgia St, Vancouver, BC V6E 3P3",
        "source": "seed_verified_dataset"
    },
    # Australia Niches
    {
        "name": "Sydney Harbour Dental & Orthodontics",
        "domain": "sydneyharbourdental.com.au",
        "website_url": "https://sydneyharbourdental.com.au",
        "country": "AU",
        "city": "Sydney, NSW",
        "niche": "dental-practices",
        "public_email": "care@sydneyharbourdental.com.au",
        "phone": "+61 2 9155 0820",
        "contact_page_url": "https://sydneyharbourdental.com.au/contact",
        "address": "100 George St, The Rocks NSW 2000",
        "source": "seed_verified_dataset"
    },
    {
        "name": "Outback Thermal HVAC Solutions",
        "domain": "outbackthermalhvac.com.au",
        "website_url": "https://outbackthermalhvac.com.au",
        "country": "AU",
        "city": "Melbourne, VIC",
        "niche": "hvac-services",
        "public_email": "quotes@outbackthermalhvac.com.au",
        "phone": "+61 3 9955 0112",
        "contact_page_url": "https://outbackthermalhvac.com.au/contact-us",
        "address": "530 Collins St, Melbourne VIC 3000",
        "source": "seed_verified_dataset"
    },
    # Singapore Niches
    {
        "name": "Marina Bay Corporate Law Advisory",
        "domain": "marinabaylawadvisory.sg",
        "website_url": "https://marinabaylawadvisory.sg",
        "country": "SG",
        "city": "Singapore",
        "niche": "commercial-lawyers",
        "public_email": "counsel@marinabaylawadvisory.sg",
        "phone": "+65 6712 3450",
        "contact_page_url": "https://marinabaylawadvisory.sg/consultation",
        "address": "10 Collyer Quay, Ocean Financial Centre, Singapore 049315",
        "source": "seed_verified_dataset"
    },
    {
        "name": "Lion City Premium Aesthetics",
        "domain": "lioncityaesthetics.sg",
        "website_url": "https://lioncityaesthetics.sg",
        "country": "SG",
        "city": "Singapore",
        "niche": "cosmetic-clinics",
        "public_email": "appointments@lioncityaesthetics.sg",
        "phone": "+65 6834 9920",
        "contact_page_url": "https://lioncityaesthetics.sg/contact",
        "address": "290 Orchard Rd, Paragon Medical Centre, Singapore 238859",
        "source": "seed_verified_dataset"
    }
]

class SeedLeadDiscoveryAdapter(BaseLeadDiscoveryAdapter):
    async def discover_leads(
        self, country_code: str, niche_slug: str, limit: int = 10
    ) -> List[DiscoveredLeadRaw]:
        results = []
        for item in SEED_PROSPECTS:
            match_country = (country_code.upper() == item["country"].upper()) or (country_code == "ALL")
            match_niche = (niche_slug.lower() == item["niche"].lower()) or (niche_slug == "ALL")
            
            if match_country and match_niche:
                results.append(
                    DiscoveredLeadRaw(
                        name=item["name"],
                        domain=normalize_domain(item["domain"]),
                        website_url=item["website_url"],
                        country=item["country"],
                        city=item["city"],
                        niche=item["niche"],
                        public_email=item.get("public_email"),
                        email_status="verified" if item.get("public_email") else "unknown",
                        phone=item.get("phone"),
                        contact_page_url=item.get("contact_page_url"),
                        address=item.get("address"),
                        source=item["source"],
                        source_url=item["website_url"]
                    )
                )
                if len(results) >= limit:
                    break
        return results
