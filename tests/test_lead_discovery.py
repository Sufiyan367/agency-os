import pytest
from app.lead_generation.targeting import TargetingConfig, TargetingFilters, load_targeting_config
from app.lead_generation.schemas import NormalizedBusinessRecord, DiscoveryStats
from app.lead_generation.providers.base import BaseLeadDiscoveryProvider
from app.lead_generation.providers.mock import MockLeadDiscoveryProvider
from app.lead_generation.service import LeadDiscoveryService
from app.database.connection import AsyncSessionLocal, init_db
from app.models.entities import LocalBusiness, LocalLead, LocalLeadEvent
from sqlalchemy import select

def test_targeting_config_loading():
    config = load_targeting_config("config/targeting.yaml")
    assert config.country == "United States"
    assert config.country_code == "US"
    assert "Texas" in config.regions
    assert "Austin" in config.cities
    assert "HVAC" in config.niches
    assert config.filters.min_rating >= 3.0
    assert config.filters.require_website is True

def test_normalization_utilities():
    # Domain normalization
    assert LeadDiscoveryService.normalize_domain("https://www.lonestarhvac.com/contact?id=1") == "lonestarhvac.com"
    assert LeadDiscoveryService.normalize_domain("http://LONESTARHVAC.COM/") == "lonestarhvac.com"
    assert LeadDiscoveryService.normalize_domain("sub.domain.co.uk/path") == "sub.domain.co.uk"
    assert LeadDiscoveryService.normalize_domain("") is None

    # Phone normalization
    assert LeadDiscoveryService.normalize_phone("+1 (512) 555-0199") == "5125550199"
    assert LeadDiscoveryService.normalize_phone("512-555-0199") == "5125550199"
    assert LeadDiscoveryService.normalize_phone("15125550199") == "5125550199"
    assert LeadDiscoveryService.normalize_phone(None) is None

    # Name normalization
    assert LeadDiscoveryService.normalize_name("Apex Comfort, LLC!") == "apex comfort llc"
    assert LeadDiscoveryService.normalize_name("Apex   Comfort   Heating & Air") == "apex comfort heating air"

@pytest.mark.asyncio
async def test_lead_discovery_provider_abstraction():
    provider = MockLeadDiscoveryProvider()
    assert provider.provider_name == "mock_directory"

    targeting = TargetingConfig(
        country="United States",
        country_code="US",
        regions=["Texas"],
        cities=["Austin"],
        niches=["HVAC"]
    )
    raw = await provider.discover_businesses(targeting)
    assert len(raw) >= 17
    assert all(isinstance(r, NormalizedBusinessRecord) for r in raw)
    assert any(r.city == "Austin" for r in raw)

@pytest.mark.asyncio
async def test_lead_discovery_deduplication_and_filtering():
    import time
    ts = int(time.time() * 1000)

    class TestDuplicateProvider(BaseLeadDiscoveryProvider):
        @property
        def provider_name(self) -> str:
            return "test_dup"

        async def discover_businesses(self, targeting):
            return [
                NormalizedBusinessRecord(
                    business_name="Austin Prime HVAC",
                    category="HVAC",
                    city="Austin",
                    region="Texas",
                    website=f"https://austinprime-{ts}.com",
                    phone=f"(512) 555-{ts % 10000:04d}",
                    rating=4.8,
                    review_count=50
                ),
                # Duplicate by website (different protocol / www)
                NormalizedBusinessRecord(
                    business_name="Austin Prime Alt Name",
                    category="HVAC",
                    city="Austin",
                    region="Texas",
                    website=f"http://www.austinprime-{ts}.com/about",
                    phone="(512) 555-2222",
                    rating=4.5,
                    review_count=30
                ),
                # Duplicate by phone number
                NormalizedBusinessRecord(
                    business_name="Different Name HVAC",
                    category="HVAC",
                    city="Austin",
                    region="Texas",
                    website=f"https://differentair-{ts}.com",
                    phone=f"+1 512-555-{ts % 10000:04d}", # Same phone as first
                    rating=4.7,
                    review_count=40
                ),
                # Duplicate by name in same city
                NormalizedBusinessRecord(
                    business_name="Austin Prime HVAC", # Same name
                    category="HVAC",
                    city="Austin",
                    region="Texas",
                    website=f"https://brandnewdomain-{ts}.com",
                    phone="(512) 555-3333",
                    rating=4.6,
                    review_count=20
                ),
                # Filtered out: low rating
                NormalizedBusinessRecord(
                    business_name="Low Rated Air",
                    category="HVAC",
                    city="Austin",
                    region="Texas",
                    website=f"https://lowratedair-{ts}.com",
                    phone="(512) 555-4444",
                    rating=2.1, # Below min_rating 3.5
                    review_count=100
                ),
                # Filtered out: missing website when required
                NormalizedBusinessRecord(
                    business_name="No Web HVAC",
                    category="HVAC",
                    city="Austin",
                    region="Texas",
                    website=None,
                    phone="(512) 555-5555",
                    rating=4.5,
                    review_count=20
                ),
                # Valid unique record
                NormalizedBusinessRecord(
                    business_name="Texas Star Cooling",
                    category="HVAC",
                    city="Austin",
                    region="Texas",
                    website=f"https://texasstarcooling-{ts}.com",
                    phone="(512) 555-7777",
                    rating=4.9,
                    review_count=120
                )
            ]

    await init_db()
    service = LeadDiscoveryService(provider=TestDuplicateProvider())
    targeting = TargetingConfig(
        filters=TargetingFilters(min_rating=3.5, require_website=True)
    )

    async with AsyncSessionLocal() as db:
        prospects, stats = await service.discover_and_process(targeting, db, check_existing_db=False)

        assert stats.businesses_discovered == 7
        assert stats.valid_businesses == 2 # "Austin Prime HVAC" and "Texas Star Cooling"
        assert stats.duplicates_removed == 3 # Web, phone, and name duplicates caught
        assert len(prospects) == 2

@pytest.mark.asyncio
async def test_lead_discovery_database_persistence():
    await init_db()
    import time
    ts = int(time.time() * 1000)

    class UniqueTestProvider(BaseLeadDiscoveryProvider):
        @property
        def provider_name(self):
            return "unique_test"

        async def discover_businesses(self, targeting):
            return [
                NormalizedBusinessRecord(
                    business_name=f"Unique Austin Cooling {ts}",
                    category="HVAC Contractor",
                    address="1000 Congress Ave, Austin, TX",
                    city="Austin",
                    region="Texas",
                    website=f"https://unique-cooling-{ts}.com",
                    phone=f"(512) 555-{ts % 10000:04d}",
                    rating=4.9,
                    review_count=77
                )
            ]

    service = LeadDiscoveryService(provider=UniqueTestProvider())
    targeting = load_targeting_config("config/targeting.yaml")

    async with AsyncSessionLocal() as db:
        prospects, stats = await service.discover_and_process(targeting, db)
        assert stats.valid_businesses == 1
        assert len(prospects) == 1

        # Verify records exist in database
        sample = prospects[0]
        res = await db.execute(select(LocalBusiness).where(LocalBusiness.id == sample.id))
        persisted_biz = res.scalar_one_or_none()
        assert persisted_biz is not None
        assert persisted_biz.name == sample.name
        assert persisted_biz.domain == f"unique-cooling-{ts}.com"
        assert persisted_biz.rating == 4.9

        # Verify associated LocalLead was created
        lead_res = await db.execute(select(LocalLead).where(LocalLead.business_id == sample.id))
        persisted_lead = lead_res.scalar_one_or_none()
        assert persisted_lead is not None
        assert persisted_lead.status == "NEW"

        # Verify LocalLeadEvent was logged
        event_res = await db.execute(select(LocalLeadEvent).where(LocalLeadEvent.lead_id == persisted_lead.id))
        event = event_res.scalar_one_or_none()
        assert event is not None
        assert event.event_type == "LEAD_DISCOVERED"
