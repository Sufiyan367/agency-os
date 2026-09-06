from typing import Dict, Any, List

# Initial seed universe of 18+ globally prominent enterprise & commercial automation markets
SEED_MARKET_UNIVERSE: List[Dict[str, Any]] = [
    {"code": "US", "name": "United States", "region": "North America", "currency": "USD", "tz": "America/New_York", "langs": ["en"], "compliance_prior": "LOW"},
    {"code": "AE", "name": "United Arab Emirates", "region": "Middle East", "currency": "AED", "tz": "Asia/Dubai", "langs": ["ar", "en"], "compliance_prior": "LOW"},
    {"code": "SA", "name": "Saudi Arabia", "region": "Middle East", "currency": "SAR", "tz": "Asia/Riyadh", "langs": ["ar", "en"], "compliance_prior": "MEDIUM"},
    {"code": "SG", "name": "Singapore", "region": "Asia-Pacific", "currency": "SGD", "tz": "Asia/Singapore", "langs": ["en", "zh", "ms"], "compliance_prior": "LOW"},
    {"code": "UK", "name": "United Kingdom", "region": "Europe", "currency": "GBP", "tz": "Europe/London", "langs": ["en"], "compliance_prior": "LOW"},
    {"code": "AU", "name": "Australia", "region": "Asia-Pacific", "currency": "AUD", "tz": "Australia/Sydney", "langs": ["en"], "compliance_prior": "LOW"},
    {"code": "CA", "name": "Canada", "region": "North America", "currency": "CAD", "tz": "America/Toronto", "langs": ["en", "fr"], "compliance_prior": "LOW"},
    {"code": "NZ", "name": "New Zealand", "region": "Asia-Pacific", "currency": "NZD", "tz": "Pacific/Auckland", "langs": ["en"], "compliance_prior": "LOW"},
    {"code": "JP", "name": "Japan", "region": "Asia-Pacific", "currency": "JPY", "tz": "Asia/Tokyo", "langs": ["ja"], "compliance_prior": "MEDIUM"},
    {"code": "CN", "name": "China", "region": "Asia-Pacific", "currency": "CNY", "tz": "Asia/Shanghai", "langs": ["zh"], "compliance_prior": "HIGH"},
    {"code": "KW", "name": "Kuwait", "region": "Middle East", "currency": "KWD", "tz": "Asia/Kuwait", "langs": ["ar", "en"], "compliance_prior": "MEDIUM"},
    {"code": "QA", "name": "Qatar", "region": "Middle East", "currency": "QAR", "tz": "Asia/Qatar", "langs": ["ar", "en"], "compliance_prior": "MEDIUM"},
    {"code": "KR", "name": "South Korea", "region": "Asia-Pacific", "currency": "KRW", "tz": "Asia/Seoul", "langs": ["ko"], "compliance_prior": "MEDIUM"},
    {"code": "DE", "name": "Germany", "region": "Europe", "currency": "EUR", "tz": "Europe/Berlin", "langs": ["de"], "compliance_prior": "MEDIUM"},
    {"code": "NL", "name": "Netherlands", "region": "Europe", "currency": "EUR", "tz": "Europe/Amsterdam", "langs": ["nl", "en"], "compliance_prior": "LOW"},
    {"code": "FR", "name": "France", "region": "Europe", "currency": "EUR", "tz": "Europe/Paris", "langs": ["fr"], "compliance_prior": "MEDIUM"},
    {"code": "IL", "name": "Israel", "region": "Middle East", "currency": "ILS", "tz": "Asia/Jerusalem", "langs": ["he", "en"], "compliance_prior": "MEDIUM"},
    {"code": "IN", "name": "India", "region": "South Asia", "currency": "INR", "tz": "Asia/Kolkata", "langs": ["en", "hi"], "compliance_prior": "LOW"},
]
SEED_COUNTRIES = SEED_MARKET_UNIVERSE


# Seed Niches with commercial ticket assumptions and operational bottlenecks
SEED_NICHES: List[Dict[str, Any]] = [
    {"slug": "roofing", "name": "Roofing Contractors", "cat": "Home & Commercial Contracting", "lead_val": 3500.0, "pain": 0.85, "automation": 0.80, "atp": 0.80, "services": ["SERVICE_001", "SERVICE_003", "SERVICE_006"]},
    {"slug": "hvac", "name": "Commercial & Residential HVAC", "cat": "Contracting & Maintenance", "lead_val": 2500.0, "pain": 0.80, "automation": 0.85, "atp": 0.85, "services": ["SERVICE_001", "SERVICE_003", "SERVICE_006", "SERVICE_004"]},
    {"slug": "dental", "name": "Dental Practices & Orthodontics", "cat": "Healthcare", "lead_val": 1800.0, "pain": 0.75, "automation": 0.90, "atp": 0.85, "services": ["SERVICE_006", "SERVICE_002", "SERVICE_003"]},
    {"slug": "medical-clinics", "name": "Specialized Medical Clinics", "cat": "Healthcare", "lead_val": 2200.0, "pain": 0.70, "automation": 0.85, "atp": 0.90, "services": ["SERVICE_006", "SERVICE_002", "SERVICE_009"]},
    {"slug": "legal-services", "name": "Corporate & Commercial Legal", "cat": "Professional Services", "lead_val": 4500.0, "pain": 0.70, "automation": 0.80, "atp": 0.95, "services": ["SERVICE_001", "SERVICE_009", "SERVICE_008"]},
    {"slug": "accounting", "name": "Accounting & Tax Advisory", "cat": "Financial Services", "lead_val": 2800.0, "pain": 0.75, "automation": 0.85, "atp": 0.85, "services": ["SERVICE_005", "SERVICE_007", "SERVICE_008"]},
    {"slug": "real-estate", "name": "Commercial & Residential Real Estate", "cat": "Property", "lead_val": 5000.0, "pain": 0.90, "automation": 0.90, "atp": 0.90, "services": ["SERVICE_001", "SERVICE_002", "SERVICE_003", "SERVICE_006"]},
    {"slug": "property-management", "name": "Property Management Firms", "cat": "Property", "lead_val": 3000.0, "pain": 0.85, "automation": 0.85, "atp": 0.80, "services": ["SERVICE_002", "SERVICE_004", "SERVICE_005"]},
    {"slug": "logistics", "name": "Freight & Logistics Providers", "cat": "Supply Chain", "lead_val": 4000.0, "pain": 0.80, "automation": 0.85, "atp": 0.85, "services": ["SERVICE_005", "SERVICE_007", "SERVICE_008"]},
    {"slug": "manufacturing", "name": "Industrial Components & Manufacturing", "cat": "Industrial", "lead_val": 8000.0, "pain": 0.70, "automation": 0.75, "atp": 0.90, "services": ["SERVICE_008", "SERVICE_007", "SERVICE_004"]},
    {"slug": "hospitality", "name": "Boutique Hotels & Resorts", "cat": "Hospitality", "lead_val": 1500.0, "pain": 0.80, "automation": 0.90, "atp": 0.80, "services": ["SERVICE_002", "SERVICE_006"]},
    {"slug": "med-spas", "name": "Medical Aesthetics & Day Spas", "cat": "Wellness", "lead_val": 1200.0, "pain": 0.85, "automation": 0.90, "atp": 0.80, "services": ["SERVICE_001", "SERVICE_006", "SERVICE_003"]},
    {"slug": "plumbing", "name": "Commercial Plumbing Contractors", "cat": "Contracting", "lead_val": 2000.0, "pain": 0.80, "automation": 0.80, "atp": 0.75, "services": ["SERVICE_001", "SERVICE_003", "SERVICE_006"]},
    {"slug": "electrical-contractors", "name": "Commercial Electrical Contractors", "cat": "Contracting", "lead_val": 2500.0, "pain": 0.80, "automation": 0.80, "atp": 0.80, "services": ["SERVICE_001", "SERVICE_003", "SERVICE_006"]},
    {"slug": "insurance", "name": "Commercial Insurance Brokerages", "cat": "Financial Services", "lead_val": 3200.0, "pain": 0.75, "automation": 0.85, "atp": 0.90, "services": ["SERVICE_001", "SERVICE_004", "SERVICE_009"]},
    {"slug": "recruitment", "name": "Executive & Tech Recruitment Agencies", "cat": "Human Resources", "lead_val": 4000.0, "pain": 0.85, "automation": 0.90, "atp": 0.85, "services": ["SERVICE_001", "SERVICE_003", "SERVICE_004"]},
    {"slug": "b2b-services", "name": "B2B Professional Services", "cat": "Professional Services", "lead_val": 3500.0, "pain": 0.80, "automation": 0.85, "atp": 0.85, "services": ["SERVICE_001", "SERVICE_004", "SERVICE_008"]},
    {"slug": "ecommerce", "name": "Direct-to-Consumer & Retail Brands", "cat": "Retail", "lead_val": 800.0, "pain": 0.90, "automation": 0.95, "atp": 0.75, "services": ["SERVICE_002", "SERVICE_003", "SERVICE_007"]},
]

# Transparent scoring weights (Must sum to positive factor total)
SCORING_WEIGHTS: Dict[str, float] = {
    "ability_to_pay": 0.15,
    "service_demand": 0.15,
    "automation_potential": 0.15,
    "ai_adoption": 0.10,
    "digital_maturity": 0.10,
    "business_density": 0.10,
    "pain_probability": 0.10,
    "market_growth": 0.05,
    "contactability": 0.10,
}

# Explicit penalty multipliers
PENALTY_WEIGHTS: Dict[str, float] = {
    "competition_penalty": 0.10,
    "compliance_penalty": 0.15,
    "uncertainty_penalty": 0.15,
}

# Signal decay thresholds in days
FRESHNESS_THRESHOLDS_DAYS: Dict[str, int] = {
    "BUSINESS_DENSITY": 365,
    "SME_DENSITY": 365,
    "LABOR_COST": 365,
    "DIGITAL_MATURITY": 180,
    "AI_ADOPTION": 180,
    "AUTOMATION_ADOPTION": 180,
    "TECH_INVESTMENT": 180,
    "SERVICE_DEMAND": 90,
    "COMPETITION": 90,
    "AGENCY_SATURATION": 90,
    "ABILITY_TO_PAY": 90,
    "MARKET_GROWTH": 90,
    "CONTACTABILITY": 90,
}

# Research execution cost guard limits
BUDGET_CONFIG: Dict[str, Any] = {
    "max_requests_per_run": 50,
    "max_cost_per_run_usd": 10.0,
    "cost_per_request_usd": 0.01,
}

from dataclasses import dataclass

@dataclass
class FreshnessThresholds:
    very_recent_days: int = 30
    recent_days: int = 90
    aging_days: int = 180
    stale_days: int = 365

@dataclass
class CostGuardConfig:
    max_requests_per_run: int = 50
    max_cost_per_run_usd: float = 10.0
    cost_per_request_usd: float = 0.01

SERVICE_CATALOG_MAPPING: Dict[str, Dict[str, Any]] = {
    "roofing": {"service_id": "SERVICE_001", "service_name": "AI Lead Qualification", "min_price_usd": 1000.0, "target_price_usd": 1500.0},
    "hvac": {"service_id": "SERVICE_003", "service_name": "Instant Lead Response Engine", "min_price_usd": 1000.0, "target_price_usd": 1500.0},
    "dental": {"service_id": "SERVICE_006", "service_name": "Appointment Booking & Calendar AI", "min_price_usd": 1000.0, "target_price_usd": 1800.0},
    "medical-clinics": {"service_id": "SERVICE_006", "service_name": "Appointment Booking & Calendar AI", "min_price_usd": 1200.0, "target_price_usd": 2000.0},
    "legal-services": {"service_id": "SERVICE_001", "service_name": "AI Lead Qualification", "min_price_usd": 1500.0, "target_price_usd": 3000.0},
    "accounting": {"service_id": "SERVICE_005", "service_name": "Document & Invoice Processing", "min_price_usd": 1200.0, "target_price_usd": 2200.0},
    "real-estate": {"service_id": "SERVICE_003", "service_name": "Instant Lead Response Engine", "min_price_usd": 1500.0, "target_price_usd": 3500.0},
    "property-management": {"service_id": "SERVICE_002", "service_name": "AI Customer Support", "min_price_usd": 1000.0, "target_price_usd": 1800.0},
    "logistics": {"service_id": "SERVICE_007", "service_name": "Workflow Automation System", "min_price_usd": 2000.0, "target_price_usd": 4000.0},
    "manufacturing": {"service_id": "SERVICE_008", "service_name": "Custom Integration & API Connector", "min_price_usd": 2500.0, "target_price_usd": 5000.0},
    "hospitality": {"service_id": "SERVICE_002", "service_name": "AI Customer Support", "min_price_usd": 1000.0, "target_price_usd": 1500.0},
    "med-spas": {"service_id": "SERVICE_006", "service_name": "Appointment Booking & Calendar AI", "min_price_usd": 1000.0, "target_price_usd": 1600.0},
    "plumbing": {"service_id": "SERVICE_001", "service_name": "AI Lead Qualification", "min_price_usd": 1000.0, "target_price_usd": 1500.0},
    "electrical-contractors": {"service_id": "SERVICE_001", "service_name": "AI Lead Qualification", "min_price_usd": 1000.0, "target_price_usd": 1500.0},
    "insurance": {"service_id": "SERVICE_004", "service_name": "CRM Sync & Lead Router", "min_price_usd": 1200.0, "target_price_usd": 2500.0},
    "recruitment": {"service_id": "SERVICE_001", "service_name": "AI Lead Qualification", "min_price_usd": 1500.0, "target_price_usd": 2800.0},
    "b2b-services": {"service_id": "SERVICE_004", "service_name": "CRM Sync & Lead Router", "min_price_usd": 1200.0, "target_price_usd": 2200.0},
    "ecommerce": {"service_id": "SERVICE_002", "service_name": "AI Customer Support", "min_price_usd": 1000.0, "target_price_usd": 1800.0},
}

