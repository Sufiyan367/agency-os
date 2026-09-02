import pytest
from app.lead_generation.discovery import lead_discovery_coordinator
from app.lead_generation.verification import lead_verification_engine
from app.database.models import Business, VerificationStatus
from sqlalchemy import select, func

@pytest.mark.asyncio
async def test_lead_discovery_and_deduplication(db_session):
    # Discovery run
    leads1 = await lead_discovery_coordinator.run_discovery_and_verification(
        db_session, country_code="US", niche_slug="roofing-contractors", target_count=2
    )
    assert len(leads1) == 2
    first_domain = leads1[0].domain

    # Attempt to discover again; the existing domain must never be duplicated
    leads2 = await lead_discovery_coordinator.run_discovery_and_verification(
        db_session, country_code="US", niche_slug="roofing-contractors", target_count=2
    )
    
    # Check that in the database, the domain count is strictly 1 (no duplicate record was added)
    count_q = select(func.count(Business.id)).where(Business.domain == first_domain)
    domain_count = (await db_session.execute(count_q)).scalar()
    assert domain_count == 1, f"Domain {first_domain} was duplicated in DB!"

@pytest.mark.asyncio
async def test_lead_verification_checks():
    is_valid, reason, details = await lead_verification_engine.verify_lead(
        "example.com", "https://example.com", "contact@example.com"
    )
    assert is_valid is True
    assert details["email_valid"] is True
    assert details["email_domain_match"] is True
