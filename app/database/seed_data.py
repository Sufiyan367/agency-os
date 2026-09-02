from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import Country, Niche
from app.core.logging import logger

COUNTRIES_DATA = [
    {
        "code": "US",
        "name": "United States",
        "gdp_per_capita": 76330.0,
        "business_density_score": 88.0,
        "digital_maturity_score": 85.0,
        "english_accessibility": 100.0,
        "currency": "USD",
        "regulatory_risk_score": 25.0
    },
    {
        "code": "GB",
        "name": "United Kingdom",
        "gdp_per_capita": 46125.0,
        "business_density_score": 82.0,
        "digital_maturity_score": 80.0,
        "english_accessibility": 100.0,
        "currency": "GBP",
        "regulatory_risk_score": 30.0
    },
    {
        "code": "CA",
        "name": "Canada",
        "gdp_per_capita": 52790.0,
        "business_density_score": 75.0,
        "digital_maturity_score": 78.0,
        "english_accessibility": 95.0,
        "currency": "CAD",
        "regulatory_risk_score": 35.0  # CASL strictness
    },
    {
        "code": "AU",
        "name": "Australia",
        "gdp_per_capita": 64960.0,
        "business_density_score": 79.0,
        "digital_maturity_score": 82.0,
        "english_accessibility": 100.0,
        "currency": "AUD",
        "regulatory_risk_score": 30.0
    },
    {
        "code": "DE",
        "name": "Germany",
        "gdp_per_capita": 48720.0,
        "business_density_score": 85.0,
        "digital_maturity_score": 72.0,
        "english_accessibility": 70.0,
        "currency": "EUR",
        "regulatory_risk_score": 45.0  # Strict GDPR / Impressum requirements
    },
    {
        "code": "NL",
        "name": "Netherlands",
        "gdp_per_capita": 57025.0,
        "business_density_score": 84.0,
        "digital_maturity_score": 86.0,
        "english_accessibility": 90.0,
        "currency": "EUR",
        "regulatory_risk_score": 32.0
    },
    {
        "code": "SG",
        "name": "Singapore",
        "gdp_per_capita": 82800.0,
        "business_density_score": 90.0,
        "digital_maturity_score": 88.0,
        "english_accessibility": 95.0,
        "currency": "SGD",
        "regulatory_risk_score": 20.0
    }
]

NICHES_DATA = [
    {
        "slug": "roofing-contractors",
        "name": "Roofing & Exterior Contractors",
        "category": "Home Services",
        "avg_deal_size": 950.0,
        "digital_weakness_factor": 75.0,  # Highly dated websites, poor mobile conversion
        "service_fit_score": 88.0,
        "commercial_intent_score": 90.0
    },
    {
        "slug": "hvac-services",
        "name": "HVAC & Climate Control",
        "category": "Home Services",
        "avg_deal_size": 850.0,
        "digital_weakness_factor": 68.0,
        "service_fit_score": 85.0,
        "commercial_intent_score": 88.0
    },
    {
        "slug": "plumbing-services",
        "name": "Commercial & Residential Plumbing",
        "category": "Home Services",
        "avg_deal_size": 750.0,
        "digital_weakness_factor": 72.0,
        "service_fit_score": 82.0,
        "commercial_intent_score": 85.0
    },
    {
        "slug": "cosmetic-clinics",
        "name": "Cosmetic & Aesthetic Clinics",
        "category": "Healthcare & Wellness",
        "avg_deal_size": 1100.0,
        "digital_weakness_factor": 55.0,  # Better visuals, but slow load times and weak local SEO
        "service_fit_score": 92.0,
        "commercial_intent_score": 95.0
    },
    {
        "slug": "dental-practices",
        "name": "Private Dental Clinics",
        "category": "Healthcare",
        "avg_deal_size": 850.0,
        "digital_weakness_factor": 60.0,
        "service_fit_score": 85.0,
        "commercial_intent_score": 82.0
    },
    {
        "slug": "accounting-firms",
        "name": "Boutique Accounting & CPA Firms",
        "category": "Professional Services",
        "avg_deal_size": 800.0,
        "digital_weakness_factor": 70.0,  # Static sites, lack of modern booking or clear CTAs
        "service_fit_score": 80.0,
        "commercial_intent_score": 78.0
    },
    {
        "slug": "commercial-lawyers",
        "name": "Boutique Commercial Law Firms",
        "category": "Legal Services",
        "avg_deal_size": 1250.0,
        "digital_weakness_factor": 58.0,
        "service_fit_score": 84.0,
        "commercial_intent_score": 86.0
    },
    {
        "slug": "commercial-electricians",
        "name": "Commercial Electrical Contractors",
        "category": "Home Services",
        "avg_deal_size": 800.0,
        "digital_weakness_factor": 74.0,
        "service_fit_score": 80.0,
        "commercial_intent_score": 80.0
    }
]

async def seed_initial_data(session: AsyncSession):
    """Inserts foundational Country and Niche benchmarks if not already present."""
    logger.info("Verifying seed data for countries and niches...")
    
    for c_data in COUNTRIES_DATA:
        result = await session.execute(select(Country).where(Country.code == c_data["code"]))
        if not result.scalar_one_or_none():
            country = Country(**c_data)
            session.add(country)
            
    for n_data in NICHES_DATA:
        result = await session.execute(select(Niche).where(Niche.slug == n_data["slug"]))
        if not result.scalar_one_or_none():
            niche = Niche(**n_data)
            session.add(niche)
            
    await session.commit()
    logger.info("Seed data check completed.")
