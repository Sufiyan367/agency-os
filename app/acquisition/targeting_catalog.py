"""
Global Targeting Catalog & Normalization Module
Autonomous B2B Lead-Gen & Revenue Operations Platform

Defines:
- 41 canonical supported countries with administrative region types
- Practical regional clusters and major cities
- Canonical niche catalog with alias normalization
- Country -> Niche matrix based on commercial relevance
"""

from typing import Dict, List, Optional, Any, Set
from pydantic import BaseModel, Field

# ==============================================================================
# 1. CANONICAL NICHE DEFINITIONS & ALIAS NORMALIZATION
# ==============================================================================

class CanonicalNiche(BaseModel):
    id: str  # Canonical uppercase ID, e.g., "HVAC"
    name: str  # Display name, e.g., "HVAC"
    category: str
    min_estimated_service_value: int = 500
    typical_range: List[int] = Field(default_factory=lambda: [500, 3500])
    keywords: List[str] = Field(default_factory=list)

# 32 Canonical Niches
NICHE_CATALOG: Dict[str, CanonicalNiche] = {
    "HVAC": CanonicalNiche(
        id="HVAC",
        name="HVAC",
        category="Heating & Air Conditioning",
        min_estimated_service_value=1500,
        typical_range=[1500, 4500],
        keywords=["hvac", "heating", "air conditioning", "cooling", "furnace", "heat pump"]
    ),
    "PLUMBING": CanonicalNiche(
        id="PLUMBING",
        name="Plumbing",
        category="Plumbing & Mechanical",
        min_estimated_service_value=1200,
        typical_range=[1200, 3500],
        keywords=["plumbing", "plumber", "pipe repair", "drain cleaning", "water heater"]
    ),
    "ROOFING": CanonicalNiche(
        id="ROOFING",
        name="Roofing",
        category="Exterior Contracting",
        min_estimated_service_value=2000,
        typical_range=[2000, 6000],
        keywords=["roofing", "roof repair", "commercial roofing", "gutters"]
    ),
    "ELECTRICAL": CanonicalNiche(
        id="ELECTRICAL",
        name="Electrical",
        category="Electrical Contracting",
        min_estimated_service_value=1200,
        typical_range=[1200, 4000],
        keywords=["electrical", "electrician", "rewiring", "commercial electrical", "lighting"]
    ),
    "DENTAL": CanonicalNiche(
        id="DENTAL",
        name="Dental",
        category="Healthcare & Dental",
        min_estimated_service_value=2000,
        typical_range=[2000, 6500],
        keywords=["dental", "dentist", "orthodontics", "cosmetic dentistry", "teeth whitening"]
    ),
    "MEDICAL_CLINICS": CanonicalNiche(
        id="MEDICAL_CLINICS",
        name="Medical Clinics",
        category="Healthcare",
        min_estimated_service_value=2500,
        typical_range=[2500, 8000],
        keywords=["medical clinic", "healthcare center", "doctor clinic", "physician office", "pediatrics"]
    ),
    "MED_SPA": CanonicalNiche(
        id="MED_SPA",
        name="Med Spa",
        category="Aesthetic & Wellness",
        min_estimated_service_value=2000,
        typical_range=[2000, 6000],
        keywords=["med spa", "medical aesthetics", "botox", "laser treatment", "skin rejuvenation"]
    ),
    "REAL_ESTATE": CanonicalNiche(
        id="REAL_ESTATE",
        name="Real Estate",
        category="Real Estate & Brokerage",
        min_estimated_service_value=2500,
        typical_range=[2500, 8500],
        keywords=["real estate", "realtor", "brokerage", "estate agents", "property sales"]
    ),
    "PROPERTY_MANAGEMENT": CanonicalNiche(
        id="PROPERTY_MANAGEMENT",
        name="Property Management",
        category="Real Estate Management",
        min_estimated_service_value=1800,
        typical_range=[1800, 5000],
        keywords=["property management", "strata management", "leasing", "facility management", "landlord services"]
    ),
    "CONSTRUCTION": CanonicalNiche(
        id="CONSTRUCTION",
        name="Construction",
        category="General Contracting & Building",
        min_estimated_service_value=3000,
        typical_range=[3000, 10000],
        keywords=["general contractor", "construction", "commercial builder", "structural framing"]
    ),
    "REMODELING": CanonicalNiche(
        id="REMODELING",
        name="Remodeling",
        category="Home & Commercial Renovation",
        min_estimated_service_value=2500,
        typical_range=[2500, 7500],
        keywords=["remodeling", "renovation", "kitchen remodeling", "bathroom remodeling", "basement"]
    ),
    "AUTOMOTIVE": CanonicalNiche(
        id="AUTOMOTIVE",
        name="Automotive",
        category="Auto Repair & Dealerships",
        min_estimated_service_value=1000,
        typical_range=[1000, 3500],
        keywords=["auto repair", "mechanic", "collision repair", "body shop", "car dealership"]
    ),
    "LANDSCAPING": CanonicalNiche(
        id="LANDSCAPING",
        name="Landscaping",
        category="Outdoor & Lawn Care",
        min_estimated_service_value=1000,
        typical_range=[1000, 3500],
        keywords=["landscaping", "lawn care", "tree removal", "hardscaping", "irrigation"]
    ),
    "PEST_CONTROL": CanonicalNiche(
        id="PEST_CONTROL",
        name="Pest Control",
        category="Extermination & Pest Management",
        min_estimated_service_value=1000,
        typical_range=[1000, 3000],
        keywords=["pest control", "exterminator", "termite treatment", "bed bug removal"]
    ),
    "CLEANING_SERVICES": CanonicalNiche(
        id="CLEANING_SERVICES",
        name="Cleaning Services",
        category="Commercial & Janitorial",
        min_estimated_service_value=800,
        typical_range=[800, 3000],
        keywords=["commercial cleaning", "office cleaning", "janitorial", "pressure washing", "maid services"]
    ),
    "HOME_SERVICES": CanonicalNiche(
        id="HOME_SERVICES",
        name="Home Services",
        category="Residential Maintenance",
        min_estimated_service_value=800,
        typical_range=[800, 2500],
        keywords=["home maintenance", "handyman", "garage door", "locksmith", "window cleaning"]
    ),
    "SOLAR": CanonicalNiche(
        id="SOLAR",
        name="Solar",
        category="Renewable Energy",
        min_estimated_service_value=2500,
        typical_range=[2500, 8000],
        keywords=["solar energy", "solar installation", "photovoltaic", "clean energy"]
    ),
    "HOSPITALITY": CanonicalNiche(
        id="HOSPITALITY",
        name="Hospitality",
        category="Hotels & Tourism",
        min_estimated_service_value=2000,
        typical_range=[2000, 7000],
        keywords=["hospitality", "resort", "hotel", "lodging", "tourism"]
    ),
    "HOTELS": CanonicalNiche(
        id="HOTELS",
        name="Hotels",
        category="Accommodation & Lodging",
        min_estimated_service_value=2500,
        typical_range=[2500, 9000],
        keywords=["boutique hotel", "luxury suites", "inn", "hotel chain"]
    ),
    "RESTAURANTS": CanonicalNiche(
        id="RESTAURANTS",
        name="Restaurants",
        category="Food & Beverage",
        min_estimated_service_value=1200,
        typical_range=[1200, 4000],
        keywords=["restaurant", "fine dining", "bistro", "catering", "café"]
    ),
    "PROFESSIONAL_SERVICES": CanonicalNiche(
        id="PROFESSIONAL_SERVICES",
        name="Professional Services",
        category="Business Consulting",
        min_estimated_service_value=2000,
        typical_range=[2000, 7500],
        keywords=["consulting", "management advisory", "b2b services", "agency"]
    ),
    "ACCOUNTING": CanonicalNiche(
        id="ACCOUNTING",
        name="Accounting",
        category="Finance & CPA",
        min_estimated_service_value=1500,
        typical_range=[1500, 5000],
        keywords=["accounting firm", "cpa", "tax consultant", "bookkeeping", "auditing"]
    ),
    "LEGAL_SERVICES": CanonicalNiche(
        id="LEGAL_SERVICES",
        name="Legal Services",
        category="Law Firms & Attorneys",
        min_estimated_service_value=2500,
        typical_range=[2500, 9000],
        keywords=["law firm", "attorney", "solicitor", "barrister", "legal counsel"]
    ),
    "RECRUITMENT": CanonicalNiche(
        id="RECRUITMENT",
        name="Recruitment",
        category="Staffing & HR",
        min_estimated_service_value=1800,
        typical_range=[1800, 6000],
        keywords=["recruitment", "staffing agency", "executive search", "headhunters"]
    ),
    "LOGISTICS": CanonicalNiche(
        id="LOGISTICS",
        name="Logistics",
        category="Freight & Supply Chain",
        min_estimated_service_value=2000,
        typical_range=[2000, 7500],
        keywords=["logistics", "freight forwarding", "warehousing", "trucking", "shipping"]
    ),
    "EDUCATION": CanonicalNiche(
        id="EDUCATION",
        name="Education",
        category="Academies & EdTech",
        min_estimated_service_value=1500,
        typical_range=[1500, 5000],
        keywords=["education", "private school", "tutoring", "training academy", "higher education"]
    ),
    "COACHING": CanonicalNiche(
        id="COACHING",
        name="Coaching",
        category="Executive & Life Mentorship",
        min_estimated_service_value=1200,
        typical_range=[1200, 4500],
        keywords=["executive coaching", "business coach", "performance mentor"]
    ),
    "FITNESS": CanonicalNiche(
        id="FITNESS",
        name="Fitness",
        category="Gyms & Athletic Studios",
        min_estimated_service_value=1000,
        typical_range=[1000, 3500],
        keywords=["fitness studio", "gym", "crossfit", "personal training", "pilates"]
    ),
    "BEAUTY": CanonicalNiche(
        id="BEAUTY",
        name="Beauty",
        category="Salons & Cosmetology",
        min_estimated_service_value=1000,
        typical_range=[1000, 3500],
        keywords=["hair salon", "cosmetics", "beauty clinic", "nail salon", "spa"]
    ),
    "VETERINARY": CanonicalNiche(
        id="VETERINARY",
        name="Veterinary",
        category="Animal Care & Pet Clinics",
        min_estimated_service_value=1500,
        typical_range=[1500, 5000],
        keywords=["veterinary hospital", "animal clinic", "vet", "pet healthcare"]
    ),
    "HOME_SECURITY": CanonicalNiche(
        id="HOME_SECURITY",
        name="Home Security",
        category="Surveillance & Access Control",
        min_estimated_service_value=1500,
        typical_range=[1500, 4500],
        keywords=["home security", "cctv", "alarm systems", "access control"]
    ),
    "FACILITY_MANAGEMENT": CanonicalNiche(
        id="FACILITY_MANAGEMENT",
        name="Facility Management",
        category="Commercial Maintenance",
        min_estimated_service_value=2000,
        typical_range=[2000, 7500],
        keywords=["facility management", "commercial operations", "integrated facilities", "building maintenance"]
    )
}

# Aliases mapped to Canonical Niche IDs
NICHE_ALIASES: Dict[str, str] = {
    # HVAC aliases
    "air conditioning": "HVAC",
    "ac repair": "HVAC",
    "heating & cooling": "HVAC",
    "heating and cooling": "HVAC",
    "hvac services": "HVAC",
    "commercial hvac": "HVAC",
    "heating": "HVAC",
    "cooling": "HVAC",
    "ventilation": "HVAC",
    # Real Estate aliases
    "realty": "REAL_ESTATE",
    "estate agency": "REAL_ESTATE",
    "estate agents": "REAL_ESTATE",
    "realtor": "REAL_ESTATE",
    "real estate agency": "REAL_ESTATE",
    "commercial real estate": "REAL_ESTATE",
    # Medical Clinics aliases
    "doctor clinic": "MEDICAL_CLINICS",
    "medical center": "MEDICAL_CLINICS",
    "healthcare clinic": "MEDICAL_CLINICS",
    "health clinic": "MEDICAL_CLINICS",
    "physicians": "MEDICAL_CLINICS",
    "polyclinic": "MEDICAL_CLINICS",
    # Dental aliases
    "dentist": "DENTAL",
    "dental clinic": "DENTAL",
    "dentistry": "DENTAL",
    "orthodontics": "DENTAL",
    # Plumbing aliases
    "plumber": "PLUMBING",
    "plumbing services": "PLUMBING",
    "emergency plumbing": "PLUMBING",
    # Roofing aliases
    "roof repair": "ROOFING",
    "roofing contractor": "ROOFING",
    "roofers": "ROOFING",
    # Electrical aliases
    "electrician": "ELECTRICAL",
    "electrical contractor": "ELECTRICAL",
    # Cleaning Services aliases
    "commercial cleaning": "CLEANING_SERVICES",
    "office cleaning": "CLEANING_SERVICES",
    "janitorial services": "CLEANING_SERVICES",
    "cleaning": "CLEANING_SERVICES",
    # Accounting aliases
    "accountancy": "ACCOUNTING",
    "cpa": "ACCOUNTING",
    "tax consultant": "ACCOUNTING",
    "accounting firm": "ACCOUNTING",
    # Legal aliases
    "law firm": "LEGAL_SERVICES",
    "lawyer": "LEGAL_SERVICES",
    "attorney": "LEGAL_SERVICES",
    "solicitor": "LEGAL_SERVICES",
    # Construction aliases
    "builder": "CONSTRUCTION",
    "builders": "CONSTRUCTION",
    "general contractor": "CONSTRUCTION",
    # Property Management aliases
    "strata": "PROPERTY_MANAGEMENT",
    "property manager": "PROPERTY_MANAGEMENT",
    # Solar aliases
    "solar installers": "SOLAR",
    "solar panels": "SOLAR",
    # Med Spa aliases
    "medical spa": "MED_SPA",
    "aesthetic clinic": "MED_SPA",
    # Automotive aliases
    "auto repair shop": "AUTOMOTIVE",
    "car mechanic": "AUTOMOTIVE",
    # Landscaping aliases
    "lawn care": "LANDSCAPING",
    "tree care": "LANDSCAPING"
}

def normalize_niche_id(query: str) -> Optional[str]:
    """Normalizes any niche string or alias into its canonical Niche ID."""
    if not query:
        return None
    raw = query.strip()
    upper = raw.upper().replace("-", "_").replace(" ", "_")
    if upper in NICHE_CATALOG:
        return upper
    lower = raw.lower().replace("-", " ")
    if lower in NICHE_ALIASES:
        return NICHE_ALIASES[lower]
    # Fuzzy match keywords
    for nid, item in NICHE_CATALOG.items():
        if lower == item.name.lower() or lower in [kw.lower() for kw in item.keywords]:
            return nid
    return None

normalize_niche = normalize_niche_id

# ==============================================================================
# 2. GLOBAL COUNTRY CATALOG & ADMINISTRATIVE REGIONS
# ==============================================================================

class AdministrativeRegion(BaseModel):
    name: str
    cities: List[str]

class CountryDefinition(BaseModel):
    code: str
    name: str
    currency: str
    region_type: str  # "State", "Province", "Emirate", "Prefecture", "Canton", etc.
    regions: Dict[str, List[str]]  # region_name -> [cities]
    default_priority: str = "P1"
    market_class: str = "PRIMARY"  # "PRIMARY", "SECONDARY", "DISABLED"
    country_priority: str = "P1"   # "P1", "P2", "P3", "DISABLED"
    acquisition_enabled: bool = True

DISABLED_MARKETS: Set[str] = {"IL", "IN", "PK"}

P1_COUNTRIES: Set[str] = {"US", "CA", "UK", "AU", "AE", "SA", "SG"}

P2_COUNTRIES: Set[str] = {
    "NZ", "IE", "DE", "NL", "CH", "FR", "QA", "KW", "BH", "OM",
    "JP", "KR", "TW", "AT", "BE", "DK", "SE", "NO", "FI", "LU",
    "IS", "PL", "PT", "HK", "ES", "IT", "CZ"
}

P3_COUNTRIES: Set[str] = {
    "BR", "MX", "CL", "CO", "MY", "TH", "ID", "ZA", "TR", "PH"
}

# Supported Countries Directory
GLOBAL_COUNTRIES: Dict[str, CountryDefinition] = {
    "US": CountryDefinition(
        code="US",
        name="United States",
        currency="USD",
        region_type="State",
        regions={
            "Texas": ["Houston", "Dallas", "Austin", "San Antonio"],
            "Florida": ["Miami", "Orlando", "Tampa", "Jacksonville"],
            "California": ["Los Angeles", "San Diego", "San Jose", "Sacramento"],
            "New York": ["New York City", "Buffalo", "Rochester"],
            "Arizona": ["Phoenix", "Scottsdale", "Mesa"],
            "Georgia": ["Atlanta", "Savannah"],
            "North Carolina": ["Charlotte", "Raleigh", "Durham"],
            "Colorado": ["Denver", "Colorado Springs", "Fort Collins"],
            "New Jersey": ["Newark", "Jersey City", "Paterson"],
            "Virginia": ["Virginia Beach", "Norfolk", "Richmond"],
            "Washington": ["Seattle", "Spokane", "Tacoma"],
            "Tennessee": ["Nashville", "Memphis", "Knoxville"],
            "Ohio": ["Columbus", "Cleveland", "Cincinnati"],
            "Pennsylvania": ["Philadelphia", "Pittsburgh", "Allentown"],
            "Michigan": ["Detroit", "Grand Rapids", "Ann Arbor"],
            "Massachusetts": ["Boston", "Worcester", "Cambridge"],
            "Illinois": ["Chicago", "Aurora", "Naperville"],
            "Nevada": ["Las Vegas", "Henderson", "Reno"],
            "Utah": ["Salt Lake City", "West Valley City", "Provo"],
            "Oregon": ["Portland", "Salem", "Eugene"]
        }
    ),
    "CA": CountryDefinition(
        code="CA",
        name="Canada",
        currency="CAD",
        region_type="Province",
        regions={
            "Ontario": ["Toronto", "Ottawa", "Mississauga", "Hamilton"],
            "British Columbia": ["Vancouver", "Surrey", "Victoria"],
            "Alberta": ["Calgary", "Edmonton"],
            "Quebec": ["Montreal", "Quebec City"],
            "Manitoba": ["Winnipeg"],
            "Saskatchewan": ["Saskatoon", "Regina"],
            "Nova Scotia": ["Halifax"],
            "New Brunswick": ["Moncton", "Saint John"]
        }
    ),
    "UK": CountryDefinition(
        code="UK",
        name="United Kingdom",
        currency="GBP",
        region_type="Region / Nation",
        regions={
            "Greater London": ["London"],
            "North West": ["Manchester", "Liverpool"],
            "West Midlands": ["Birmingham"],
            "Yorkshire and the Humber": ["Leeds", "Sheffield"],
            "South West": ["Bristol"],
            "South East": ["Reading", "Brighton", "Southampton"],
            "Scotland": ["Edinburgh", "Glasgow"],
            "Wales": ["Cardiff"],
            "Northern Ireland": ["Belfast"],
            "East of England": ["Cambridge", "Norwich"],
            "East Midlands": ["Nottingham", "Leicester"],
            "North East": ["Newcastle upon Tyne"]
        }
    ),
    "AU": CountryDefinition(
        code="AU",
        name="Australia",
        currency="AUD",
        region_type="State / Territory",
        regions={
            "New South Wales": ["Sydney", "Newcastle", "Wollongong"],
            "Victoria": ["Melbourne", "Geelong"],
            "Queensland": ["Brisbane", "Gold Coast", "Sunshine Coast"],
            "Western Australia": ["Perth"],
            "South Australia": ["Adelaide"],
            "Australian Capital Territory": ["Canberra"],
            "Tasmania": ["Hobart"]
        }
    ),
    "NZ": CountryDefinition(
        code="NZ",
        name="New Zealand",
        currency="NZD",
        region_type="Region",
        regions={
            "Auckland": ["Auckland"],
            "Canterbury": ["Christchurch"],
            "Wellington": ["Wellington"],
            "Waikato": ["Hamilton"],
            "Bay of Plenty": ["Tauranga"],
            "Otago": ["Dunedin", "Queenstown"]
        }
    ),
    "AE": CountryDefinition(
        code="AE",
        name="United Arab Emirates",
        currency="AED",
        region_type="Emirate",
        regions={
            "Dubai": ["Dubai"],
            "Abu Dhabi": ["Abu Dhabi", "Al Ain"],
            "Sharjah": ["Sharjah"],
            "Ajman": ["Ajman"],
            "Ras Al Khaimah": ["Ras Al Khaimah"],
            "Fujairah": ["Fujairah"],
            "Umm Al Quwain": ["Umm Al Quwain"]
        }
    ),
    "SA": CountryDefinition(
        code="SA",
        name="Saudi Arabia",
        currency="SAR",
        region_type="Region",
        regions={
            "Riyadh Region": ["Riyadh"],
            "Makkah Region": ["Jeddah", "Makkah", "Taif"],
            "Eastern Province": ["Dammam", "Khobar", "Dhahran", "Jubail"],
            "Madinah Region": ["Madinah"],
            "Asir Region": ["Abha", "Khamis Mushait"],
            "Qassim": ["Buraydah"],
            "Tabuk": ["Tabuk"],
            "Jazan": ["Jazan"],
            "Hail": ["Hail"]
        }
    ),
    "QA": CountryDefinition(
        code="QA",
        name="Qatar",
        currency="QAR",
        region_type="Municipality",
        regions={
            "Doha": ["Doha"],
            "Al Rayyan": ["Al Rayyan"],
            "Al Wakrah": ["Al Wakrah"],
            "Al Daayen": ["Lusail"]
        }
    ),
    "KW": CountryDefinition(
        code="KW",
        name="Kuwait",
        currency="KWD",
        region_type="Governorate",
        regions={
            "Al Asimah": ["Kuwait City"],
            "Hawalli": ["Hawalli", "Salmiya"],
            "Al Farwaniyah": ["Farwaniya"],
            "Al Ahmadi": ["Ahmadi", "Fahaheel"]
        }
    ),
    "BH": CountryDefinition(
        code="BH",
        name="Bahrain",
        currency="BHD",
        region_type="Governorate",
        regions={
            "Capital Governorate": ["Manama"],
            "Muharraq": ["Muharraq"],
            "Northern Governorate": ["Budaiya", "Saar"],
            "Southern Governorate": ["Riffa"]
        }
    ),
    "OM": CountryDefinition(
        code="OM",
        name="Oman",
        currency="OMR",
        region_type="Governorate",
        regions={
            "Muscat": ["Muscat", "Seeb", "Bawshar"],
            "Dhofar": ["Salalah"],
            "Al Batinah North": ["Sohar"],
            "Al Dakhiliyah": ["Nizwa"]
        }
    ),
    "SG": CountryDefinition(
        code="SG",
        name="Singapore",
        currency="SGD",
        region_type="District / Sector",
        regions={
            "Central Region": ["Downtown Core", "Orchard", "Marina South"],
            "East Region": ["Changi", "Bedok", "Tampines"],
            "West Region": ["Jurong", "Clementi"],
            "North Region": ["Woodlands", "Yishun"]
        }
    ),
    "HK": CountryDefinition(
        code="HK",
        name="Hong Kong",
        currency="HKD",
        region_type="District",
        regions={
            "Hong Kong Island": ["Central", "Wan Chai", "Causeway Bay"],
            "Kowloon": ["Tsim Sha Tsui", "Mong Kok", "Kwun Tong"],
            "New Territories": ["Sha Tin", "Tsuen Wan", "Yuen Long"]
        }
    ),
    "IE": CountryDefinition(
        code="IE",
        name="Ireland",
        currency="EUR",
        region_type="County / Province",
        regions={
            "Leinster": ["Dublin", "Dún Laoghaire", "Drogheda"],
            "Munster": ["Cork", "Limerick", "Waterford"],
            "Connacht": ["Galway", "Sligo"]
        }
    ),
    "NL": CountryDefinition(
        code="NL",
        name="Netherlands",
        currency="EUR",
        region_type="Province",
        regions={
            "North Holland": ["Amsterdam", "Haarlem"],
            "South Holland": ["Rotterdam", "The Hague"],
            "Utrecht": ["Utrecht", "Amersfoort"],
            "North Brabant": ["Eindhoven", "Tilburg", "Breda"]
        }
    ),
    "DE": CountryDefinition(
        code="DE",
        name="Germany",
        currency="EUR",
        region_type="Bundesland",
        regions={
            "North Rhine-Westphalia": ["Cologne", "Düsseldorf", "Dortmund", "Essen"],
            "Bavaria": ["Munich", "Nuremberg", "Augsburg"],
            "Baden-Württemberg": ["Stuttgart", "Karlsruhe", "Mannheim"],
            "Hesse": ["Frankfurt", "Wiesbaden", "Kassel"],
            "Berlin": ["Berlin"],
            "Hamburg": ["Hamburg"]
        }
    ),
    "FR": CountryDefinition(
        code="FR",
        name="France",
        currency="EUR",
        region_type="Région",
        regions={
            "Île-de-France": ["Paris", "Boulogne-Billancourt", "Saint-Denis"],
            "Auvergne-Rhône-Alpes": ["Lyon", "Grenoble", "Saint-Étienne"],
            "Provence-Alpes-Côte d'Azur": ["Marseille", "Nice", "Toulon"],
            "Nouvelle-Aquitaine": ["Bordeaux", "Limoges"],
            "Occitanie": ["Toulouse", "Montpellier"]
        }
    ),
    "ES": CountryDefinition(
        code="ES",
        name="Spain",
        currency="EUR",
        region_type="Autonomous Community",
        regions={
            "Community of Madrid": ["Madrid"],
            "Catalonia": ["Barcelona", "L'Hospitalet"],
            "Andalusia": ["Seville", "Málaga"],
            "Valencian Community": ["Valencia", "Alicante"],
            "Basque Country": ["Bilbao", "San Sebastián"]
        }
    ),
    "IT": CountryDefinition(
        code="IT",
        name="Italy",
        currency="EUR",
        region_type="Regione",
        regions={
            "Lombardy": ["Milan", "Brescia", "Monza"],
            "Lazio": ["Rome", "Latina"],
            "Campania": ["Naples", "Salerno"],
            "Veneto": ["Venice", "Verona", "Padua"],
            "Piedmont": ["Turin", "Novara"],
            "Emilia-Romagna": ["Bologna", "Modena", "Parma"]
        }
    ),
    "SE": CountryDefinition(
        code="SE",
        name="Sweden",
        currency="SEK",
        region_type="Län",
        regions={
            "Stockholm": ["Stockholm", "Solna"],
            "Västra Götaland": ["Gothenburg", "Borås"],
            "Skåne": ["Malmö", "Helsingborg", "Lund"]
        }
    ),
    "NO": CountryDefinition(
        code="NO",
        name="Norway",
        currency="NOK",
        region_type="Fylke",
        regions={
            "Oslo": ["Oslo"],
            "Vestland": ["Bergen"],
            "Rogaland": ["Stavanger"],
            "Trøndelag": ["Trondheim"]
        }
    ),
    "DK": CountryDefinition(
        code="DK",
        name="Denmark",
        currency="DKK",
        region_type="Region",
        regions={
            "Capital Region": ["Copenhagen", "Frederiksberg"],
            "Central Denmark": ["Aarhus"],
            "Region of Southern Denmark": ["Odense", "Esbjerg"],
            "North Denmark": ["Aalborg"]
        }
    ),
    "FI": CountryDefinition(
        code="FI",
        name="Finland",
        currency="EUR",
        region_type="Maakunta",
        regions={
            "Uusimaa": ["Helsinki", "Espoo", "Vantaa"],
            "Pirkanmaa": ["Tampere"],
            "Southwest Finland": ["Turku"],
            "North Ostrobothnia": ["Oulu"]
        }
    ),
    "CH": CountryDefinition(
        code="CH",
        name="Switzerland",
        currency="CHF",
        region_type="Canton",
        regions={
            "Zürich": ["Zürich", "Winterthur"],
            "Geneva": ["Geneva"],
            "Vaud": ["Lausanne"],
            "Zug": ["Zug"],
            "Basel-Stadt": ["Basel"]
        }
    ),
    "AT": CountryDefinition(
        code="AT",
        name="Austria",
        currency="EUR",
        region_type="Bundesland",
        regions={
            "Vienna": ["Vienna"],
            "Styria": ["Graz"],
            "Upper Austria": ["Linz"],
            "Salzburg": ["Salzburg"],
            "Tyrol": ["Innsbruck"]
        }
    ),
    "BE": CountryDefinition(
        code="BE",
        name="Belgium",
        currency="EUR",
        region_type="Region / Province",
        regions={
            "Brussels-Capital": ["Brussels"],
            "Antwerp": ["Antwerp", "Mechelen"],
            "East Flanders": ["Ghent"],
            "Liège": ["Liège"]
        }
    ),
    "PL": CountryDefinition(
        code="PL",
        name="Poland",
        currency="PLN",
        region_type="Voivodeship",
        regions={
            "Masovian": ["Warsaw", "Radom"],
            "Lesser Poland": ["Kraków"],
            "Lower Silesian": ["Wrocław"],
            "Silesian": ["Katowice", "Gliwice"],
            "Greater Poland": ["Poznań"]
        }
    ),
    "CZ": CountryDefinition(
        code="CZ",
        name="Czechia",
        currency="CZK",
        region_type="Kraj",
        regions={
            "Prague": ["Prague"],
            "South Moravian": ["Brno"],
            "Moravian-Silesian": ["Ostrava"],
            "Plzeň": ["Plzeň"]
        }
    ),
    "PT": CountryDefinition(
        code="PT",
        name="Portugal",
        currency="EUR",
        region_type="District",
        regions={
            "Lisbon": ["Lisbon", "Cascais", "Sintra"],
            "Porto": ["Porto", "Vila Nova de Gaia"],
            "Braga": ["Braga"],
            "Faro": ["Faro", "Albufeira"]
        }
    ),
    "ZA": CountryDefinition(
        code="ZA",
        name="South Africa",
        currency="ZAR",
        region_type="Province",
        regions={
            "Gauteng": ["Johannesburg", "Pretoria"],
            "Western Cape": ["Cape Town", "Stellenbosch"],
            "KwaZulu-Natal": ["Durban", "Pietermaritzburg"]
        }
    ),
    "MX": CountryDefinition(
        code="MX",
        name="Mexico",
        currency="MXN",
        region_type="State",
        regions={
            "Jalisco": ["Guadalajara", "Zapopan"],
            "Nuevo León": ["Monterrey", "San Pedro Garza García"],
            "Mexico City": ["Mexico City"],
            "Quintana Roo": ["Cancún", "Playa del Carmen"],
            "Estado de México": ["Toluca", "Naucalpan"],
            "Puebla": ["Puebla"]
        }
    ),
    "BR": CountryDefinition(
        code="BR",
        name="Brazil",
        currency="BRL",
        region_type="State",
        regions={
            "São Paulo": ["São Paulo", "Campinas", "Santos"],
            "Rio de Janeiro": ["Rio de Janeiro", "Niterói"],
            "Minas Gerais": ["Belo Horizonte", "Uberlândia"],
            "Paraná": ["Curitiba", "Londrina"],
            "Santa Catarina": ["Florianópolis", "Joinville"]
        }
    ),
    "CL": CountryDefinition(
        code="CL",
        name="Chile",
        currency="CLP",
        region_type="Región",
        regions={
            "Santiago Metropolitan": ["Santiago", "Providencia", "Las Condes"],
            "Valparaíso": ["Valparaíso", "Viña del Mar"],
            "Biobío": ["Concepción"]
        }
    ),
    "CO": CountryDefinition(
        code="CO",
        name="Colombia",
        currency="COP",
        region_type="Department",
        regions={
            "Bogotá D.C.": ["Bogotá"],
            "Antioquia": ["Medellín", "Envigado"],
            "Valle del Cauca": ["Cali"],
            "Atlántico": ["Barranquilla"]
        }
    ),
    "JP": CountryDefinition(
        code="JP",
        name="Japan",
        currency="JPY",
        region_type="Prefecture",
        regions={
            "Tokyo": ["Tokyo"],
            "Osaka": ["Osaka"],
            "Kanagawa": ["Yokohama", "Kawasaki"],
            "Aichi": ["Nagoya"],
            "Fukuoka": ["Fukuoka"],
            "Saitama": ["Saitama"],
            "Chiba": ["Chiba"]
        }
    ),
    "KR": CountryDefinition(
        code="KR",
        name="South Korea",
        currency="KRW",
        region_type="Province / Special City",
        regions={
            "Seoul": ["Seoul", "Gangnam", "Mapo"],
            "Gyeonggi": ["Suwon", "Seongnam", "Yongin"],
            "Busan": ["Busan"],
            "Incheon": ["Incheon"],
            "Daegu": ["Daegu"]
        }
    ),
    "MY": CountryDefinition(
        code="MY",
        name="Malaysia",
        currency="MYR",
        region_type="State / Federal Territory",
        regions={
            "Selangor": ["Petaling Jaya", "Shah Alam", "Subang Jaya"],
            "Kuala Lumpur": ["Kuala Lumpur"],
            "Penang": ["George Town", "Bayan Lepas"],
            "Johor": ["Johor Bahru", "Iskandar Puteri"],
            "Sabah": ["Kota Kinabalu"]
        }
    ),
    "TH": CountryDefinition(
        code="TH",
        name="Thailand",
        currency="THB",
        region_type="Province",
        regions={
            "Bangkok": ["Bangkok"],
            "Chiang Mai": ["Chiang Mai"],
            "Phuket": ["Phuket"],
            "Chonburi": ["Pattaya"]
        }
    ),
    "ID": CountryDefinition(
        code="ID",
        name="Indonesia",
        currency="IDR",
        region_type="Province",
        regions={
            "DKI Jakarta": ["Jakarta"],
            "West Java": ["Bandung", "Bekasi"],
            "East Java": ["Surabaya"],
            "Bali": ["Denpasar", "Badung"]
        }
    ),
    "PH": CountryDefinition(
        code="PH",
        name="Philippines",
        currency="PHP",
        region_type="Region / Province",
        regions={
            "Metro Manila": ["Manila", "Makati", "Quezon City", "Taguig"],
            "Cebu": ["Cebu City", "Mandaue"],
            "Davao": ["Davao City"]
        }
    ),
    "IN": CountryDefinition(
        code="IN",
        name="India",
        currency="INR",
        region_type="State",
        regions={
            "Maharashtra": ["Mumbai", "Pune", "Nagpur"],
            "Karnataka": ["Bengaluru", "Mysuru"],
            "Telangana": ["Hyderabad"],
            "Tamil Nadu": ["Chennai", "Coimbatore"],
            "Delhi": ["New Delhi"],
            "Gujarat": ["Ahmedabad", "Surat", "Vadodara"],
            "Haryana": ["Gurugram", "Faridabad"],
            "Uttar Pradesh": ["Noida", "Lucknow"],
            "West Bengal": ["Kolkata"],
            "Kerala": ["Kochi", "Thiruvananthapuram"]
        }
    ),
    "TW": CountryDefinition(
        code="TW",
        name="Taiwan",
        currency="TWD",
        region_type="Special Municipality / County",
        regions={
            "Taipei": ["Taipei"],
            "New Taipei": ["New Taipei"],
            "Taichung": ["Taichung"],
            "Kaohsiung": ["Kaohsiung"],
            "Tainan": ["Tainan"],
            "Taoyuan": ["Taoyuan"]
        }
    ),
    "LU": CountryDefinition(
        code="LU",
        name="Luxembourg",
        currency="EUR",
        region_type="Canton",
        regions={
            "Luxembourg": ["Luxembourg City"],
            "Esch-sur-Alzette": ["Esch-sur-Alzette", "Differdange", "Dudelange"]
        }
    ),
    "IS": CountryDefinition(
        code="IS",
        name="Iceland",
        currency="ISK",
        region_type="Region",
        regions={
            "Capital Region": ["Reykjavik", "Kopavogur", "Hafnarfjordur"],
            "Southern Peninsula": ["Keflavik", "Njardvik"],
            "Northeastern Region": ["Akureyri"]
        }
    ),
    "TR": CountryDefinition(
        code="TR",
        name="Türkiye",
        currency="TRY",
        region_type="Province",
        regions={
            "Istanbul": ["Istanbul"],
            "Ankara": ["Ankara"],
            "Izmir": ["Izmir"],
            "Bursa": ["Bursa"],
            "Antalya": ["Antalya"]
        }
    ),
    "PK": CountryDefinition(
        code="PK",
        name="Pakistan",
        currency="PKR",
        region_type="Province",
        regions={
            "Punjab": ["Lahore", "Faisalabad", "Rawalpindi"],
            "Sindh": ["Karachi"],
            "Islamabad Capital Territory": ["Islamabad"]
        }
    ),
    "IL": CountryDefinition(
        code="IL",
        name="Israel",
        currency="ILS",
        region_type="District",
        regions={
            "Tel Aviv District": ["Tel Aviv"],
            "Central District": ["Rishon LeZion", "Petah Tikva"],
            "Haifa District": ["Haifa"],
            "Jerusalem District": ["Jerusalem"]
        }
    )
}

# Apply Canonical Market Classification & Acquisition Permissions
for c_code, c_def in GLOBAL_COUNTRIES.items():
    if c_code in DISABLED_MARKETS:
        c_def.market_class = "DISABLED"
        c_def.country_priority = "DISABLED"
        c_def.default_priority = "DISABLED"
        c_def.acquisition_enabled = False
    elif c_code in P1_COUNTRIES:
        c_def.market_class = "PRIMARY"
        c_def.country_priority = "P1"
        c_def.default_priority = "P1"
        c_def.acquisition_enabled = True
    elif c_code in P2_COUNTRIES:
        c_def.market_class = "PRIMARY"
        c_def.country_priority = "P2"
        c_def.default_priority = "P2"
        c_def.acquisition_enabled = True
    elif c_code in P3_COUNTRIES:
        c_def.market_class = "SECONDARY"
        c_def.country_priority = "P3"
        c_def.default_priority = "P3"
        c_def.acquisition_enabled = True

# ==============================================================================
# 3. COUNTRY -> NICHE RELEVANCE MATRIX
# ==============================================================================

COUNTRY_NICHE_MAP: Dict[str, List[str]] = {
    "US": [
        "HVAC", "ROOFING", "PLUMBING", "ELECTRICAL", "DENTAL", "MED_SPA",
        "REAL_ESTATE", "LANDSCAPING", "REMODELING", "PEST_CONTROL", "SOLAR", "AUTOMOTIVE"
    ],
    "CA": [
        "HVAC", "ROOFING", "PLUMBING", "DENTAL", "REAL_ESTATE", "CONSTRUCTION",
        "ELECTRICAL", "LANDSCAPING", "SOLAR"
    ],
    "UK": [
        "REAL_ESTATE", "DENTAL", "PLUMBING", "ROOFING", "HVAC", "CONSTRUCTION",
        "ACCOUNTING", "LEGAL_SERVICES", "PROPERTY_MANAGEMENT", "HOME_SERVICES"
    ],
    "AU": [
        "HVAC", "PLUMBING", "ELECTRICAL", "ROOFING", "DENTAL", "SOLAR",
        "REAL_ESTATE", "LANDSCAPING", "CONSTRUCTION", "AUTOMOTIVE"
    ],
    "NZ": [
        "PLUMBING", "HVAC", "ELECTRICAL", "ROOFING", "DENTAL", "CONSTRUCTION",
        "REAL_ESTATE", "PROPERTY_MANAGEMENT", "LANDSCAPING"
    ],
    "AE": [
        "REAL_ESTATE", "PROPERTY_MANAGEMENT", "DENTAL", "MEDICAL_CLINICS", "HOME_SERVICES",
        "CONSTRUCTION", "AUTOMOTIVE", "HOSPITALITY", "FACILITY_MANAGEMENT", "RECRUITMENT"
    ],
    "SA": [
        "REAL_ESTATE", "HVAC", "CONSTRUCTION", "DENTAL", "MEDICAL_CLINICS",
        "FACILITY_MANAGEMENT", "AUTOMOTIVE", "HOSPITALITY", "PROPERTY_MANAGEMENT",
        "CLEANING_SERVICES", "LOGISTICS"
    ],
    "QA": [
        "REAL_ESTATE", "CONSTRUCTION", "HVAC", "MEDICAL_CLINICS", "FACILITY_MANAGEMENT",
        "HOSPITALITY", "AUTOMOTIVE"
    ],
    "KW": [
        "REAL_ESTATE", "HVAC", "AUTOMOTIVE", "MEDICAL_CLINICS", "CONSTRUCTION",
        "FACILITY_MANAGEMENT", "DENTAL"
    ],
    "BH": [
        "REAL_ESTATE", "MEDICAL_CLINICS", "HVAC", "AUTOMOTIVE", "HOSPITALITY", "CONSTRUCTION"
    ],
    "OM": [
        "HVAC", "REAL_ESTATE", "CONSTRUCTION", "AUTOMOTIVE", "MEDICAL_CLINICS",
        "HOSPITALITY", "PROPERTY_MANAGEMENT"
    ],
    "SG": [
        "MEDICAL_CLINICS", "DENTAL", "REAL_ESTATE", "PROPERTY_MANAGEMENT",
        "PROFESSIONAL_SERVICES", "EDUCATION", "RECRUITMENT"
    ],
    "HK": [
        "REAL_ESTATE", "PROPERTY_MANAGEMENT", "PROFESSIONAL_SERVICES", "LEGAL_SERVICES",
        "ACCOUNTING", "RECRUITMENT", "MEDICAL_CLINICS"
    ],
    "IE": [
        "ROOFING", "PLUMBING", "DENTAL", "REAL_ESTATE", "CONSTRUCTION",
        "ACCOUNTING", "HVAC", "HOME_SERVICES"
    ],
    "NL": [
        "REAL_ESTATE", "DENTAL", "CONSTRUCTION", "HVAC", "LOGISTICS", "SOLAR", "PROPERTY_MANAGEMENT"
    ],
    "DE": [
        "HVAC", "ELECTRICAL", "DENTAL", "CONSTRUCTION", "REAL_ESTATE",
        "SOLAR", "PROFESSIONAL_SERVICES", "AUTOMOTIVE"
    ],
    "FR": [
        "REAL_ESTATE", "DENTAL", "MEDICAL_CLINICS", "CONSTRUCTION", "HOSPITALITY",
        "AUTOMOTIVE", "PROPERTY_MANAGEMENT"
    ],
    "ES": [
        "REAL_ESTATE", "PROPERTY_MANAGEMENT", "DENTAL", "HOSPITALITY",
        "CONSTRUCTION", "SOLAR", "HOME_SERVICES"
    ],
    "IT": [
        "REAL_ESTATE", "DENTAL", "HOSPITALITY", "CONSTRUCTION", "AUTOMOTIVE", "HOME_SERVICES"
    ],
    "SE": [
        "CONSTRUCTION", "REAL_ESTATE", "PROFESSIONAL_SERVICES", "DENTAL", "HVAC",
        "LOGISTICS", "HOME_SERVICES"
    ],
    "NO": [
        "CONSTRUCTION", "REAL_ESTATE", "PROFESSIONAL_SERVICES", "DENTAL", "HVAC",
        "LOGISTICS", "HOME_SERVICES"
    ],
    "DK": [
        "CONSTRUCTION", "REAL_ESTATE", "PROFESSIONAL_SERVICES", "DENTAL", "HVAC",
        "LOGISTICS", "HOME_SERVICES"
    ],
    "FI": [
        "CONSTRUCTION", "REAL_ESTATE", "PROFESSIONAL_SERVICES", "DENTAL", "HVAC",
        "LOGISTICS", "HOME_SERVICES"
    ],
    "CH": [
        "DENTAL", "MEDICAL_CLINICS", "REAL_ESTATE", "PROFESSIONAL_SERVICES",
        "HOSPITALITY", "PROPERTY_MANAGEMENT"
    ],
    "AT": [
        "HVAC", "DENTAL", "CONSTRUCTION", "REAL_ESTATE", "HOSPITALITY", "PROFESSIONAL_SERVICES"
    ],
    "BE": [
        "REAL_ESTATE", "DENTAL", "CONSTRUCTION", "LOGISTICS", "PROFESSIONAL_SERVICES", "HOME_SERVICES"
    ],
    "PL": [
        "CONSTRUCTION", "LOGISTICS", "AUTOMOTIVE", "DENTAL", "HVAC", "REAL_ESTATE"
    ],
    "CZ": [
        "AUTOMOTIVE", "CONSTRUCTION", "LOGISTICS", "DENTAL", "REAL_ESTATE", "HOSPITALITY"
    ],
    "PT": [
        "REAL_ESTATE", "HOSPITALITY", "CONSTRUCTION", "DENTAL", "PROPERTY_MANAGEMENT", "SOLAR"
    ],
    "ZA": [
        "REAL_ESTATE", "DENTAL", "HVAC", "SOLAR", "CONSTRUCTION", "HOME_SERVICES",
        "AUTOMOTIVE", "HOME_SECURITY"
    ],
    "MX": [
        "REAL_ESTATE", "DENTAL", "AUTOMOTIVE", "HOME_SERVICES", "MEDICAL_CLINICS",
        "CONSTRUCTION", "HOSPITALITY"
    ],
    "BR": [
        "DENTAL", "MEDICAL_CLINICS", "REAL_ESTATE", "HOME_SERVICES", "AUTOMOTIVE",
        "CONSTRUCTION", "EDUCATION", "HOSPITALITY"
    ],
    "CL": [
        "REAL_ESTATE", "DENTAL", "CONSTRUCTION", "AUTOMOTIVE", "HOME_SERVICES", "LOGISTICS"
    ],
    "CO": [
        "DENTAL", "REAL_ESTATE", "MEDICAL_CLINICS", "HOME_SERVICES", "AUTOMOTIVE", "HOSPITALITY"
    ],
    "JP": [
        "REAL_ESTATE", "MEDICAL_CLINICS", "HOSPITALITY", "PROFESSIONAL_SERVICES",
        "PROPERTY_MANAGEMENT", "AUTOMOTIVE"
    ],
    "KR": [
        "MEDICAL_CLINICS", "REAL_ESTATE", "EDUCATION", "BEAUTY", "HOSPITALITY", "PROFESSIONAL_SERVICES"
    ],
    "MY": [
        "REAL_ESTATE", "DENTAL", "EDUCATION", "HOME_SERVICES", "AUTOMOTIVE",
        "HOSPITALITY", "MEDICAL_CLINICS"
    ],
    "TH": [
        "HOSPITALITY", "REAL_ESTATE", "DENTAL", "MEDICAL_CLINICS", "AUTOMOTIVE",
        "HOTELS", "PROPERTY_MANAGEMENT"
    ],
    "ID": [
        "REAL_ESTATE", "MEDICAL_CLINICS", "AUTOMOTIVE", "EDUCATION", "HOSPITALITY",
        "PROPERTY_MANAGEMENT", "HOME_SERVICES"
    ],
    "PH": [
        "REAL_ESTATE", "DENTAL", "MEDICAL_CLINICS", "HOME_SERVICES", "EDUCATION",
        "HOSPITALITY", "AUTOMOTIVE", "PROFESSIONAL_SERVICES"
    ],
    "IN": [
        "DENTAL", "MEDICAL_CLINICS", "REAL_ESTATE", "EDUCATION", "HOME_SERVICES",
        "AUTOMOTIVE", "RECRUITMENT", "PROFESSIONAL_SERVICES"
    ],
    "TW": [
        "MEDICAL_CLINICS", "DENTAL", "REAL_ESTATE", "EDUCATION", "PROFESSIONAL_SERVICES",
        "AUTOMOTIVE", "HOSPITALITY"
    ],
    "LU": [
        "REAL_ESTATE", "PROPERTY_MANAGEMENT", "ACCOUNTING", "LEGAL_SERVICES", "PROFESSIONAL_SERVICES",
        "DENTAL"
    ],
    "IS": [
        "HOSPITALITY", "CONSTRUCTION", "REAL_ESTATE", "HVAC", "AUTOMOTIVE", "DENTAL"
    ],
    "TR": [
        "REAL_ESTATE", "DENTAL", "MEDICAL_CLINICS", "CONSTRUCTION", "AUTOMOTIVE",
        "HOSPITALITY", "LOGISTICS"
    ],
    "PK": [
        "REAL_ESTATE", "DENTAL", "EDUCATION", "HOME_SERVICES", "AUTOMOTIVE", "RECRUITMENT"
    ],
    "IL": [
        "REAL_ESTATE", "MEDICAL_CLINICS", "DENTAL", "PROFESSIONAL_SERVICES", "EDUCATION"
    ]
}

# ==============================================================================
# 4. QUERY & ACCESS HELPER FUNCTIONS
# ==============================================================================

def get_country(country_code: str) -> Optional[CountryDefinition]:
    """Retrieves country definition by 2-letter uppercase ISO code, dynamically supporting any valid ISO country."""
    if not country_code:
        return None
    code = country_code.upper().strip()
    if code in GLOBAL_COUNTRIES:
        return GLOBAL_COUNTRIES[code]

    # Known invalid / test codes should not be dynamically created
    if code in {"XX", "ZZ", "TEST", "MOCK", "NULL", "NONE", "NA", "AA"}:
        return None

    # Dynamic expansion for any valid 2-letter ISO country code
    if len(code) == 2 and code.isalpha():
        if code in DISABLED_MARKETS:
            c = CountryDefinition(
                code=code,
                name=code,
                currency="USD",
                region_type="Region",
                regions={},
                default_priority="DISABLED",
                market_class="DISABLED",
                country_priority="DISABLED",
                acquisition_enabled=False
            )
            GLOBAL_COUNTRIES[code] = c
            return c
        else:
            # Dynamically supported non-disabled country
            c = CountryDefinition(
                code=code,
                name=code,
                currency="USD",
                region_type="Region",
                regions={},
                default_priority="P3",
                market_class="SECONDARY",
                country_priority="P3",
                acquisition_enabled=True
            )
            GLOBAL_COUNTRIES[code] = c
            return c
    return None

def list_countries() -> List[Dict[str, Any]]:
    """Lists all supported countries with key metadata including market classification."""
    res = []
    for code, c in GLOBAL_COUNTRIES.items():
        res.append({
            "country_code": c.code,
            "country_name": c.name,
            "currency": c.currency,
            "region_type": c.region_type,
            "market_class": c.market_class,
            "country_priority": c.country_priority,
            "acquisition_enabled": c.acquisition_enabled,
            "total_regions": len(c.regions),
            "total_cities": sum(len(cities) for cities in c.regions.values())
        })
    return sorted(res, key=lambda x: x["country_name"])

def get_regions_for_country(country_code: str) -> List[str]:
    """Returns the list of administrative region names for a given country."""
    c = get_country(country_code)
    if not c:
        return []
    return list(c.regions.keys())

def get_cities_for_region(country_code: str, region_name: str) -> List[str]:
    """Returns the list of cities for an administrative region."""
    c = get_country(country_code)
    if not c:
        return []
    # Case-insensitive lookup for region name
    for r_name, cities in c.regions.items():
        if r_name.lower().strip() == region_name.lower().strip():
            return cities
    return []

def get_niches_for_country(country_code: str) -> List[Dict[str, Any]]:
    """Returns the list of canonical niches supported for a country."""
    c_code = (country_code or "").upper().strip()
    niche_ids = COUNTRY_NICHE_MAP.get(c_code)
    if not niche_ids:
        # Fallback to general high-ticket niches
        niche_ids = ["HVAC", "PLUMBING", "ROOFING", "DENTAL", "REAL_ESTATE"]

    out = []
    for nid in niche_ids:
        n = NICHE_CATALOG.get(nid)
        if n:
            out.append({
                "niche_id": n.id,
                "name": n.name,
                "category": n.category,
                "min_estimated_service_value": n.min_estimated_service_value
            })
    return out

def validate_target_combination(
    country_code: str,
    region: str,
    city: str,
    niche_id: str
) -> Dict[str, Any]:
    """
    Validates that a Country -> Region -> City -> Niche hierarchy is valid.
    Returns {"valid": True, "country": ..., "region_type": ..., "niche": ...}
    or raises ValueError with specific mismatch reason.
    Strictly rejects disabled markets (e.g. Israel, India, Pakistan).
    """
    c = get_country(country_code)
    if not c:
        raise ValueError(f"Unknown or unsupported country code: '{country_code}'")

    if c.code in DISABLED_MARKETS or c.market_class == "DISABLED" or not c.acquisition_enabled:
        raise ValueError(
            f"Market '{c.name}' ({c.code}) is DISABLED for acquisition. Discovery, outreach, and targeting are strictly BLOCKED."
        )

    matched_region = None
    for r in c.regions.keys():
        if r.lower().strip() == region.lower().strip():
            matched_region = r
            break
    if not matched_region:
        if not c.regions and region and region.strip():
            matched_region = region.strip()
            c.regions[matched_region] = []
        else:
            raise ValueError(
                f"Region '{region}' does not exist in {c.name}. Available {c.region_type}s: {list(c.regions.keys())[:5]}..."
            )

    cities = c.regions.get(matched_region, [])
    matched_city = None
    for ct in cities:
        if ct.lower().strip() == city.lower().strip():
            matched_city = ct
            break
    if not matched_city:
        if not cities and city and city.strip():
            matched_city = city.strip()
            c.regions[matched_region].append(matched_city)
        else:
            raise ValueError(
                f"City '{city}' not recognized in {c.region_type} '{matched_region}'. Supported cities: {cities}"
            )

    norm_niche = normalize_niche_id(niche_id)
    if not norm_niche:
        raise ValueError(f"Unknown or unrecognized niche '{niche_id}'.")

    canonical_niche = NICHE_CATALOG[norm_niche]

    return {
        "valid": True,
        "country_code": c.code,
        "country_name": c.name,
        "region": matched_region,
        "region_type": c.region_type,
        "city": matched_city,
        "niche_id": canonical_niche.id,
        "niche_name": canonical_niche.name,
        "currency": c.currency
    }
