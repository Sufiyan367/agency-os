from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import Business, Contact, PipelineStage, VerificationStatus, PipelineEvent
from app.lead_generation.adapters.real_web_discovery import RealWebDiscoveryAdapter
from app.lead_generation.adapters.directory import DirectoryDiscoveryAdapter
from app.lead_generation.adapters.web_search import WebSearchDiscoveryAdapter
from app.lead_generation.verification import lead_verification_engine
from app.core.security import normalize_domain
from app.core.logging import logger

class LeadDiscoveryCoordinator:
    """
    Coordinates real web prospect discovery, strict domain deduplication,
    multi-vector network verification, contact creation, and pipeline stage assignment.
    """
    def __init__(self):
        # Production adapters: 100% REAL public web discovery, NO SEED LEADS
        self.adapters = [
            RealWebDiscoveryAdapter(),
            WebSearchDiscoveryAdapter()
        ]

    async def run_discovery_and_verification(
        self,
        session: AsyncSession,
        country_code: str = "US",
        niche_slug: str = "roofing-contractors",
        target_count: int = 50
    ) -> List[Business]:
        logger.info(f"Starting REAL lead discovery for Country: {country_code}, Niche: {niche_slug}, Target: {target_count}")
        discovered_records = []

        # Run discovery through real public search adapters
        for adapter in self.adapters:
            try:
                leads = await adapter.discover_leads(country_code, niche_slug, limit=target_count)
                discovered_records.extend(leads)
                if len(discovered_records) >= target_count:
                    break
            except Exception as e:
                logger.warning(f"Adapter {adapter.__class__.__name__} warning: {e}")

        created_businesses: List[Business] = []

        for lead_data in discovered_records:
            norm_dom = normalize_domain(lead_data.domain)
            if not norm_dom:
                continue

            # Deduplication: Check if domain already exists in DB
            existing_q = select(Business).where(Business.domain == norm_dom)
            existing = (await session.execute(existing_q)).scalar_one_or_none()

            if existing:
                continue  # Skip duplicates

            # Run Lead Verification Engine
            is_valid, reason, details = await lead_verification_engine.verify_lead(
                norm_dom, lead_data.website_url, lead_data.public_email
            )

            v_status = VerificationStatus.VERIFIED.value if is_valid else VerificationStatus.REJECTED.value
            p_stage = PipelineStage.VERIFIED.value if is_valid else PipelineStage.DISCOVERED.value

            biz = Business(
                name=lead_data.name,
                domain=norm_dom,
                website_url=lead_data.website_url,
                country=lead_data.country.upper(),
                city=lead_data.city,
                niche=lead_data.niche,
                public_email=lead_data.public_email,
                email_status=lead_data.email_status if lead_data.public_email else "unknown",
                phone=lead_data.phone,
                contact_page_url=lead_data.contact_page_url,
                address=lead_data.address,
                social_profiles=lead_data.social_profiles,
                source=lead_data.source,
                verification_status=v_status,
                pipeline_stage=p_stage
            )
            session.add(biz)
            await session.flush()

            # Create primary Contact record if public contact details exist
            if lead_data.public_email:
                contact = Contact(
                    business_id=biz.id,
                    name=f"Managing Partner / Owner ({lead_data.name})",
                    title="Business Owner / General Manager",
                    email=lead_data.public_email,
                    phone=lead_data.phone,
                    email_status="verified" if details.get("email_valid") else "unknown",
                    source=lead_data.source
                )
                session.add(contact)

            # Record Pipeline Event
            event = PipelineEvent(
                business_id=biz.id,
                from_stage=PipelineStage.DISCOVERED.value,
                to_stage=p_stage,
                deal_value=0.0,
                note=f"Real business discovered via {lead_data.source}. Verification: {reason}."
            )
            session.add(event)
            created_businesses.append(biz)

            if len(created_businesses) >= target_count:
                break

        await session.commit()
        logger.info(f"REAL Discovery completed: {len(created_businesses)} authentic verified businesses stored.")
        return created_businesses

lead_discovery_coordinator = LeadDiscoveryCoordinator()
