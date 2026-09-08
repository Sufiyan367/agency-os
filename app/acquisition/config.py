from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database.models import CountryConfig
from app.acquisition.models import CountryConfigDTO
from app.core.logging import logger

DEFAULT_COUNTRY_PROFILES: Dict[str, Dict[str, Any]] = {
    "US": {
        "country_code": "US",
        "country_name": "United States",
        "enabled": True,
        "language": "en",
        "currency": "USD",
        "timezone": "America/New_York",
        "target_cities": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Dallas", "Miami", "Atlanta"],
        "target_niches": ["roofing-contractors", "commercial-hvac", "dental-clinics", "legal-practices", "plumbing-services"],
        "discovery_query_templates": [
            "{niche} in {city}, {country_name}",
            "best {niche} {city}",
            "{city} top rated {niche} companies",
            "{niche} services near {city}"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 5000.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 25,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 17,
        },
        "compliance_settings": {
            "can_spam_compliant": True,
            "mandatory_physical_address": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 30.0
        },
        "max_daily_discovery": 50,
        "concurrency_limit": 3
    },
    "UK": {
        "country_code": "UK",
        "country_name": "United Kingdom",
        "enabled": True,
        "language": "en",
        "currency": "GBP",
        "timezone": "Europe/London",
        "target_cities": ["London", "Manchester", "Birmingham", "Leeds", "Glasgow", "Bristol", "Liverpool"],
        "target_niches": ["commercial-cleaning", "accountancy-firms", "roofing-contractors", "estate-agents", "it-support"],
        "discovery_query_templates": [
            "{niche} in {city}, UK",
            "leading {niche} {city}",
            "{city} professional {niche} services"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 4500.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 20,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 17,
        },
        "compliance_settings": {
            "gdpr_compliant": True,
            "legitimate_interest_assessment": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 25.0
        },
        "max_daily_discovery": 40,
        "concurrency_limit": 3
    },
    "AU": {
        "country_code": "AU",
        "country_name": "Australia",
        "enabled": True,
        "language": "en",
        "currency": "AUD",
        "timezone": "Australia/Sydney",
        "target_cities": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Gold Coast"],
        "target_niches": ["solar-installers", "commercial-electrical", "plumbing-services", "physiotherapy-clinics", "builders"],
        "discovery_query_templates": [
            "{niche} in {city}, Australia",
            "{city} verified {niche} contractors",
            "top {niche} {city} NSW VIC QLD"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 4000.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 20,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 17,
        },
        "compliance_settings": {
            "spam_act_2003_compliant": True,
            "accurate_sender_info": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 25.0
        },
        "max_daily_discovery": 35,
        "concurrency_limit": 2
    },
    "CA": {
        "country_code": "CA",
        "country_name": "Canada",
        "enabled": True,
        "language": "en",
        "currency": "CAD",
        "timezone": "America/Toronto",
        "target_cities": ["Toronto", "Vancouver", "Montreal", "Calgary", "Ottawa", "Edmonton"],
        "target_niches": ["home-renovation", "commercial-hvac", "veterinary-clinics", "accounting-services"],
        "discovery_query_templates": [
            "{niche} in {city}, Canada",
            "{city} certified {niche} specialists",
            "best {niche} {city} ON BC AB"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 4000.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 20,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 17,
        },
        "compliance_settings": {
            "casl_compliant": True,
            "implied_consent_verified": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 20.0
        },
        "max_daily_discovery": 35,
        "concurrency_limit": 2
    },
    "AE": {
        "country_code": "AE",
        "country_name": "United Arab Emirates",
        "enabled": True,
        "language": "en",
        "currency": "AED",
        "timezone": "Asia/Dubai",
        "target_cities": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah"],
        "target_niches": ["restaurants-cafes", "dental-medical-clinics", "real-estate", "salons-barbers", "automotive", "hvac-home-services", "hotels", "fitness", "professional-services", "local-retail"],
        "discovery_query_templates": [
            "{niche} in {city}, UAE",
            "{city} commercial {niche} firms",
            "leading {niche} companies {city}"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 6000.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 10,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 18,
        },
        "compliance_settings": {
            "uae_data_protection_compliant": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 25.0
        },
        "max_daily_discovery": 30,
        "concurrency_limit": 2
    },
    "SA": {
        "country_code": "SA",
        "country_name": "Saudi Arabia",
        "enabled": True,
        "language": "en",
        "currency": "SAR",
        "timezone": "Asia/Riyadh",
        "target_cities": ["Riyadh", "Jeddah", "Dammam", "Khobar", "Mecca", "Medina"],
        "target_niches": ["restaurants-cafes", "dental-medical-clinics", "real-estate", "salons-barbers", "automotive", "hvac-home-services", "hotels", "fitness", "professional-services", "local-retail"],
        "discovery_query_templates": [
            "{niche} in {city}, Saudi Arabia",
            "{city} verified {niche} companies",
            "top {niche} {city}"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 5000.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 10,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 18,
        },
        "compliance_settings": {
            "saudi_pdpl_compliant": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 25.0
        },
        "max_daily_discovery": 30,
        "concurrency_limit": 2
    },
    "QA": {
        "country_code": "QA",
        "country_name": "Qatar",
        "enabled": True,
        "language": "en",
        "currency": "QAR",
        "timezone": "Asia/Qatar",
        "target_cities": ["Doha", "Al Rayyan", "Al Wakrah", "Lusail"],
        "target_niches": ["restaurants-cafes", "dental-medical-clinics", "real-estate", "salons-barbers", "automotive", "hvac-home-services", "hotels", "fitness", "professional-services", "local-retail"],
        "discovery_query_templates": [
            "{niche} in {city}, Qatar",
            "{city} top {niche} firms",
            "best {niche} {city}"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 5500.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 10,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 18,
        },
        "compliance_settings": {
            "qatar_pdp_compliant": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 25.0
        },
        "max_daily_discovery": 30,
        "concurrency_limit": 2
    },
    "KW": {
        "country_code": "KW",
        "country_name": "Kuwait",
        "enabled": True,
        "language": "en",
        "currency": "KWD",
        "timezone": "Asia/Kuwait",
        "target_cities": ["Kuwait City", "Hawalli", "Salmiya", "Al Ahmadi"],
        "target_niches": ["restaurants-cafes", "dental-medical-clinics", "real-estate", "salons-barbers", "automotive", "hvac-home-services", "hotels", "fitness", "professional-services", "local-retail"],
        "discovery_query_templates": [
            "{niche} in {city}, Kuwait",
            "{city} leading {niche} businesses",
            "top {niche} {city}"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 5000.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 10,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 18,
        },
        "compliance_settings": {
            "citra_compliant": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 25.0
        },
        "max_daily_discovery": 30,
        "concurrency_limit": 2
    },
    "OM": {
        "country_code": "OM",
        "country_name": "Oman",
        "enabled": True,
        "language": "en",
        "currency": "OMR",
        "timezone": "Asia/Muscat",
        "target_cities": ["Muscat", "Salalah", "Sohar", "Seeb", "Nizwa"],
        "target_niches": ["restaurants-cafes", "dental-medical-clinics", "real-estate", "salons-barbers", "automotive", "hvac-home-services", "hotels", "fitness", "professional-services", "local-retail"],
        "discovery_query_templates": [
            "{niche} in {city}, Oman",
            "{city} commercial {niche} services",
            "best {niche} {city}"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 4500.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 10,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 18,
        },
        "compliance_settings": {
            "oman_pdpl_compliant": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 25.0
        },
        "max_daily_discovery": 30,
        "concurrency_limit": 2
    },
    "BH": {
        "country_code": "BH",
        "country_name": "Bahrain",
        "enabled": True,
        "language": "en",
        "currency": "BHD",
        "timezone": "Asia/Bahrain",
        "target_cities": ["Manama", "Riffa", "Muharraq", "Hamad Town"],
        "target_niches": ["restaurants-cafes", "dental-medical-clinics", "real-estate", "salons-barbers", "automotive", "hvac-home-services", "hotels", "fitness", "professional-services", "local-retail"],
        "discovery_query_templates": [
            "{niche} in {city}, Bahrain",
            "{city} top rated {niche} providers",
            "leading {niche} {city}"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 4500.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 10,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 18,
        },
        "compliance_settings": {
            "bahrain_pdpl_compliant": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 25.0
        },
        "max_daily_discovery": 30,
        "concurrency_limit": 2
    },
    "JO": {
        "country_code": "JO",
        "country_name": "Jordan",
        "enabled": True,
        "language": "en",
        "currency": "JOD",
        "timezone": "Asia/Amman",
        "target_cities": ["Amman", "Zarqa", "Irbid", "Aqaba", "Salt"],
        "target_niches": ["restaurants-cafes", "dental-medical-clinics", "real-estate", "salons-barbers", "automotive", "hvac-home-services", "hotels", "fitness", "professional-services", "local-retail"],
        "discovery_query_templates": [
            "{niche} in {city}, Jordan",
            "{city} professional {niche} firms",
            "best {niche} {city}"
        ],
        "qualification_rules": {
            "min_website_age_years": 1,
            "require_ssl": True,
            "require_phone_or_email": True,
            "max_initial_deal_size_usd": 4000.0,
        },
        "outreach_rules": {
            "max_messages_per_day": 10,
            "preferred_contact_channel": "email",
            "working_hours_start": 9,
            "working_hours_end": 18,
        },
        "compliance_settings": {
            "jordan_pdpl_compliant": True,
            "opt_out_link_mandatory": True,
            "risk_score_limit": 25.0
        },
        "max_daily_discovery": 30,
        "concurrency_limit": 2
    }
}

class CountryConfigManager:
    """Manages multi-country pipeline configurations and synchronizes with persistent database state."""

    async def ensure_defaults(self, session: AsyncSession) -> None:
        """Seeds default multi-country profiles if not present in database."""
        for code, profile in DEFAULT_COUNTRY_PROFILES.items():
            stmt = select(CountryConfig).where(CountryConfig.country_code == code.upper())
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                cfg = CountryConfig(
                    country_code=profile["country_code"].upper(),
                    country_name=profile["country_name"],
                    enabled=profile["enabled"],
                    language=profile["language"],
                    currency=profile["currency"],
                    timezone=profile["timezone"],
                    target_cities=profile["target_cities"],
                    target_niches=profile["target_niches"],
                    discovery_query_templates=profile["discovery_query_templates"],
                    qualification_rules=profile["qualification_rules"],
                    outreach_rules=profile["outreach_rules"],
                    compliance_settings=profile["compliance_settings"],
                    max_daily_discovery=profile["max_daily_discovery"],
                    concurrency_limit=profile["concurrency_limit"]
                )
                session.add(cfg)
                logger.info(f"[CountryConfig] Initialized default configuration for {code}")
        await session.commit()

    async def list_countries(self, session: AsyncSession, enabled_only: bool = False) -> List[CountryConfigDTO]:
        """Returns all configured country profiles."""
        await self.ensure_defaults(session)
        stmt = select(CountryConfig)
        if enabled_only:
            stmt = stmt.where(CountryConfig.enabled.is_(True))
        stmt = stmt.order_by(CountryConfig.country_code.asc())
        rows = (await session.execute(stmt)).scalars().all()

        return [
            CountryConfigDTO(
                country_code=r.country_code,
                country_name=r.country_name,
                enabled=r.enabled,
                language=r.language,
                currency=r.currency,
                timezone=r.timezone,
                target_cities=r.target_cities or [],
                target_niches=r.target_niches or [],
                discovery_query_templates=r.discovery_query_templates or [],
                qualification_rules=r.qualification_rules or {},
                outreach_rules=r.outreach_rules or {},
                compliance_settings=r.compliance_settings or {},
                max_daily_discovery=r.max_daily_discovery,
                concurrency_limit=r.concurrency_limit
            )
            for r in rows
        ]

    async def get_country(self, session: AsyncSession, country_code: str) -> Optional[CountryConfigDTO]:
        """Retrieves country configuration by ISO code."""
        code = country_code.upper().strip()
        stmt = select(CountryConfig).where(CountryConfig.country_code == code)
        cfg = (await session.execute(stmt)).scalar_one_or_none()
        if not cfg:
            await self.ensure_defaults(session)
            cfg = (await session.execute(stmt)).scalar_one_or_none()
        if not cfg:
            return None

        return CountryConfigDTO(
            country_code=cfg.country_code,
            country_name=cfg.country_name,
            enabled=cfg.enabled,
            language=cfg.language,
            currency=cfg.currency,
            timezone=cfg.timezone,
            target_cities=cfg.target_cities or [],
            target_niches=cfg.target_niches or [],
            discovery_query_templates=cfg.discovery_query_templates or [],
            qualification_rules=cfg.qualification_rules or {},
            outreach_rules=cfg.outreach_rules or {},
            compliance_settings=cfg.compliance_settings or {},
            max_daily_discovery=cfg.max_daily_discovery,
            concurrency_limit=cfg.concurrency_limit
        )

    async def set_enabled(self, session: AsyncSession, country_code: str, enabled: bool) -> CountryConfigDTO:
        """Enables or disables a specific country pipeline dynamically."""
        code = country_code.upper().strip()
        stmt = select(CountryConfig).where(CountryConfig.country_code == code)
        cfg = (await session.execute(stmt)).scalar_one_or_none()
        if not cfg:
            await self.ensure_defaults(session)
            cfg = (await session.execute(stmt)).scalar_one_or_none()
        if not cfg:
            raise ValueError(f"Country with code '{country_code}' not found in configuration.")

        cfg.enabled = enabled
        cfg.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(cfg)
        logger.info(f"[CountryConfig] Country '{code}' enabled state set to: {enabled}")

        return CountryConfigDTO(
            country_code=cfg.country_code,
            country_name=cfg.country_name,
            enabled=cfg.enabled,
            language=cfg.language,
            currency=cfg.currency,
            timezone=cfg.timezone,
            target_cities=cfg.target_cities or [],
            target_niches=cfg.target_niches or [],
            discovery_query_templates=cfg.discovery_query_templates or [],
            qualification_rules=cfg.qualification_rules or {},
            outreach_rules=cfg.outreach_rules or {},
            compliance_settings=cfg.compliance_settings or {},
            max_daily_discovery=cfg.max_daily_discovery,
            concurrency_limit=cfg.concurrency_limit
        )

    async def update_config(self, session: AsyncSession, country_code: str, updates: Dict[str, Any]) -> CountryConfigDTO:
        """Updates settings for a country configuration."""
        code = country_code.upper().strip()
        stmt = select(CountryConfig).where(CountryConfig.country_code == code)
        cfg = (await session.execute(stmt)).scalar_one_or_none()
        if not cfg:
            raise ValueError(f"Country code '{country_code}' not found.")

        for k, v in updates.items():
            if hasattr(cfg, k) and k not in ("id", "country_code", "created_at"):
                setattr(cfg, k, v)
        cfg.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(cfg)
        logger.info(f"[CountryConfig] Updated settings for {code}")
        return await self.get_country(session, code)

country_config_manager = CountryConfigManager()
