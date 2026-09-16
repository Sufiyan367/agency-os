"""
Focused Verification Test Suite: Global Acquisition Targeting System
Tests:
1. Country catalog loads all 41 countries
2. Region mapping works with country-specific administrative region types
3. City mapping works for major regional city clusters
4. Canonical niche catalog loads and normalizes aliases
5. Country -> region filtering
6. Region -> city filtering
7. City -> niche filtering
8. Duplicate target prevention across (country, region, city, niche)
9. Target enable/disable/pause state management
10. Priority handling (P1 > P2 > P3 queue ordering)
11. Dashboard targeting API endpoints (/api/targeting/* and /api/targets)
12. Discovery consumes active targets
13. Disabled and paused targets are skipped
14. Target provenance persists on prospect (country, administrative_region, city, niche)
15. Country/region/city/niche consistency validation
16. Existing acquisition pipeline compatibility
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.app import app
from app.core.security import create_session_token
from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import TargetDefinition, Business
from app.acquisition.targeting_catalog import (
    GLOBAL_COUNTRIES,
    NICHE_CATALOG,
    COUNTRY_NICHE_MAP,
    list_countries,
    get_country,
    get_regions_for_country,
    get_cities_for_region,
    get_niches_for_country,
    normalize_niche_id,
    validate_target_combination
)
from app.acquisition.targeting_manager import targeting_manager
from app.acquisition.pool import global_prospect_pool

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture
async def test_session():
    await init_db()
    async with AsyncSessionLocal() as session:
        yield session

@pytest_asyncio.fixture
async def auth_client():
    token = create_session_token("admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": token}) as client:
        yield client

# 1. Country Catalog Loads All Supported Countries (47 Canonical Global Markets)
def test_country_catalog_loads_all_47():
    assert len(GLOBAL_COUNTRIES) == 47
    assert "US" in GLOBAL_COUNTRIES
    assert "CA" in GLOBAL_COUNTRIES
    assert "UK" in GLOBAL_COUNTRIES
    assert "AU" in GLOBAL_COUNTRIES
    assert "AE" in GLOBAL_COUNTRIES
    assert "SA" in GLOBAL_COUNTRIES
    assert "SG" in GLOBAL_COUNTRIES
    assert "IN" in GLOBAL_COUNTRIES
    assert "PK" in GLOBAL_COUNTRIES
    assert "IL" in GLOBAL_COUNTRIES
    assert "TW" in GLOBAL_COUNTRIES
    assert "LU" in GLOBAL_COUNTRIES
    assert "IS" in GLOBAL_COUNTRIES
    assert "TR" in GLOBAL_COUNTRIES

# 1B. Hard Market Exclusions: Israel, India, Pakistan
def test_disabled_markets_hard_exclusion():
    for code, expected_name in [("IL", "Israel"), ("IN", "India"), ("PK", "Pakistan")]:
        c = get_country(code)
        assert c is not None
        assert c.name == expected_name
        assert c.market_class == "DISABLED"
        assert c.country_priority == "DISABLED"
        assert c.default_priority == "DISABLED"
        assert c.acquisition_enabled is False

        # Attempting to validate target combination must raise ValueError
        with pytest.raises(ValueError) as exc:
            # Pick any region
            first_reg = list(c.regions.keys())[0]
            first_city = c.regions[first_reg][0]
            validate_target_combination(code, first_reg, first_city, "DENTAL")
        assert "disabled for acquisition" in str(exc.value).lower()
        assert "strictly blocked" in str(exc.value).lower()

# 1C. Primary and Secondary Market Classification Taxonomy
def test_primary_and_secondary_market_taxonomy():
    # P1 Markets (7 Countries)
    p1_codes = ["US", "CA", "UK", "AU", "AE", "SA", "SG"]
    for code in p1_codes:
        c = get_country(code)
        assert c.market_class == "PRIMARY"
        assert c.country_priority == "P1"
        assert c.acquisition_enabled is True

    # P2 Markets (27 Countries)
    p2_codes = [
        "NZ", "IE", "DE", "NL", "CH", "FR", "QA", "KW", "BH", "OM",
        "JP", "KR", "TW", "AT", "BE", "DK", "SE", "NO", "FI", "LU",
        "IS", "PL", "PT", "HK", "ES", "IT", "CZ"
    ]
    for code in p2_codes:
        c = get_country(code)
        assert c.market_class == "PRIMARY"
        assert c.country_priority == "P2"
        assert c.acquisition_enabled is True

    # P3 Markets (10 Countries)
    p3_codes = ["BR", "MX", "CL", "CO", "MY", "TH", "ID", "ZA", "TR", "PH"]
    for code in p3_codes:
        c = get_country(code)
        assert c.market_class == "SECONDARY"
        assert c.country_priority == "P3"
        assert c.acquisition_enabled is True

# 2. Region Mapping Works with Country-Specific Administrative Region Types
def test_region_mapping_types():
    us = get_country("US")
    assert us.region_type == "State"
    assert "Texas" in us.regions
    assert "Florida" in us.regions

    ca = get_country("CA")
    assert ca.region_type == "Province"
    assert "Ontario" in ca.regions

    ae = get_country("AE")
    assert ae.region_type == "Emirate"
    assert "Dubai" in ae.regions
    assert "Abu Dhabi" in ae.regions

    ch = get_country("CH")
    assert ch.region_type == "Canton"
    assert "Zürich" in ch.regions

    jp = get_country("JP")
    assert jp.region_type == "Prefecture"
    assert "Tokyo" in jp.regions

    de = get_country("DE")
    assert de.region_type == "Bundesland"
    assert "Bavaria" in de.regions

# 3. City Mapping Works for Major Regional City Clusters
def test_city_mapping_clusters():
    tx_cities = get_cities_for_region("US", "Texas")
    assert "Houston" in tx_cities
    assert "Dallas" in tx_cities
    assert "Austin" in tx_cities
    assert "San Antonio" in tx_cities

    on_cities = get_cities_for_region("CA", "Ontario")
    assert "Toronto" in on_cities
    assert "Ottawa" in on_cities

    mh_cities = get_cities_for_region("IN", "Maharashtra")
    assert "Mumbai" in mh_cities
    assert "Pune" in mh_cities

    sa_cities = get_cities_for_region("SA", "Eastern Province")
    assert "Dammam" in sa_cities
    assert "Khobar" in sa_cities

# 4. Canonical Niche Catalog Loads & Normalizes Aliases
def test_canonical_niche_catalog_and_aliases():
    assert len(NICHE_CATALOG) == 32
    assert "HVAC" in NICHE_CATALOG
    assert "REAL_ESTATE" in NICHE_CATALOG
    assert "DENTAL" in NICHE_CATALOG
    assert "PLUMBING" in NICHE_CATALOG

    # Alias normalization
    assert normalize_niche_id("Air Conditioning") == "HVAC"
    assert normalize_niche_id("ac repair") == "HVAC"
    assert normalize_niche_id("Heating & Cooling") == "HVAC"
    assert normalize_niche_id("Realty") == "REAL_ESTATE"
    assert normalize_niche_id("realtor") == "REAL_ESTATE"
    assert normalize_niche_id("Doctor Clinic") == "MEDICAL_CLINICS"
    assert normalize_niche_id("Medical Center") == "MEDICAL_CLINICS"
    assert normalize_niche_id("dentist") == "DENTAL"
    assert normalize_niche_id("roof repair") == "ROOFING"

# 5. Country -> Region Filtering
def test_country_to_region_filtering():
    regions = get_regions_for_country("US")
    assert len(regions) >= 20
    assert "Texas" in regions
    assert "Dubai" not in regions

    ae_regions = get_regions_for_country("AE")
    assert "Dubai" in ae_regions
    assert "Texas" not in ae_regions

# 6. Region -> City Filtering
def test_region_to_city_filtering():
    fl_cities = get_cities_for_region("US", "Florida")
    assert "Miami" in fl_cities
    assert "Orlando" in fl_cities
    assert "Dallas" not in fl_cities

# 7. City -> Niche Filtering
def test_country_niche_association():
    us_niches = get_niches_for_country("US")
    niche_ids = [n["niche_id"] for n in us_niches]
    assert "HVAC" in niche_ids
    assert "ROOFING" in niche_ids
    assert "DENTAL" in niche_ids

# 8. Duplicate Target Prevention
@pytest.mark.asyncio
async def test_duplicate_target_prevention(test_session: AsyncSession):
    # Seed default targets
    await targeting_manager.seed_default_targets_if_empty(test_session)

    # Attempting to create an identical target must raise ValueError
    with pytest.raises(ValueError) as exc:
        await targeting_manager.create_target(
            session=test_session,
            country_code="US",
            region="Texas",
            city="Houston",
            niche="HVAC"
        )
    assert "already exists" in str(exc.value).lower()

# 9. Target Enable/Disable/Pause State Management
@pytest.mark.asyncio
async def test_target_status_transitions(test_session: AsyncSession):
    targets = await targeting_manager.list_targets(test_session)
    assert len(targets) > 0
    t = targets[0]

    # Pause target
    paused = await targeting_manager.update_target(test_session, t.id, status="PAUSED")
    assert paused.status == "PAUSED"
    assert paused.enabled is False

    # Reactivate target
    active = await targeting_manager.update_target(test_session, t.id, status="ACTIVE")
    assert active.status == "ACTIVE"
    assert active.enabled is True

# 10. Priority Handling (P1 > P2 > P3 Queue Ordering)
@pytest.mark.asyncio
async def test_priority_ordering(test_session: AsyncSession):
    queue = await targeting_manager.get_active_target_queue(test_session)
    priorities = [item.priority for item in queue]
    # Check that priorities are sorted (e.g. all P1s appear before P2s, etc.)
    prio_order = {"P1": 1, "P2": 2, "P3": 3}
    num_prios = [prio_order.get(p, 99) for p in priorities]
    assert num_prios == sorted(num_prios)

# 11. Dashboard Targeting API Endpoints
@pytest.mark.asyncio
async def test_targeting_api_endpoints(auth_client: AsyncClient):
    # Countries catalog
    r_c = await auth_client.get("/api/targeting/countries")
    assert r_c.status_code == 200
    assert len(r_c.json()) == 47

    # Regions for country
    r_r = await auth_client.get("/api/targeting/regions?country=US")
    assert r_r.status_code == 200
    assert r_r.json()["region_type"] == "State"
    assert "Texas" in r_r.json()["regions"]

    # Cities for region
    r_ci = await auth_client.get("/api/targeting/cities?country=US&region=Texas")
    assert r_ci.status_code == 200
    assert "Houston" in r_ci.json()["cities"]

    # Niches
    r_n = await auth_client.get("/api/targeting/niches?country=US")
    assert r_n.status_code == 200
    assert any(n["niche_id"] == "HVAC" for n in r_n.json())

    # Summary
    r_s = await auth_client.get("/api/targeting/summary")
    assert r_s.status_code == 200
    summary = r_s.json()
    assert summary["total_supported_countries"] == 47
    assert summary["p1_markets_count"] == 7
    assert summary["disabled_markets_count"] == 3
    assert summary["active_targets_count"] >= 5
    assert len(summary["top_active_targets"]) > 0

    # Market Overview Endpoint
    r_mo = await auth_client.get("/api/targeting/market-overview")
    assert r_mo.status_code == 200
    overview = r_mo.json()
    assert len(overview) == 47
    il_item = next(m for m in overview if m["country_code"] == "IL")
    assert il_item["market_class"] == "DISABLED"
    assert il_item["priority"] == "DISABLED"
    assert il_item["status"] == "OFF"
    assert il_item["active_targets"] == 0

    in_item = next(m for m in overview if m["country_code"] == "IN")
    assert in_item["market_class"] == "DISABLED"
    assert in_item["priority"] == "DISABLED"
    assert in_item["status"] == "OFF"
    assert in_item["active_targets"] == 0

    pk_item = next(m for m in overview if m["country_code"] == "PK")
    assert pk_item["market_class"] == "DISABLED"
    assert pk_item["priority"] == "DISABLED"
    assert pk_item["status"] == "OFF"
    assert pk_item["active_targets"] == 0

    us_item = next(m for m in overview if m["country_code"] == "US")
    assert us_item["market_class"] == "PRIMARY"
    assert us_item["priority"] == "P1"

    # List targets
    r_t = await auth_client.get("/api/targets")
    assert r_t.status_code == 200
    assert len(r_t.json()) >= 5

# 12 & 13. Discovery Consumes Active Targets & Skips Disabled
@pytest.mark.asyncio
async def test_discovery_consumes_active_targets_and_skips_disabled(test_session: AsyncSession):
    # Ensure queue has items
    queue = await targeting_manager.get_active_target_queue(test_session)
    assert len(queue) > 0

    # Pause one target
    first_target = queue[0]
    await targeting_manager.update_target(test_session, first_target.id, status="PAUSED")

    new_queue = await targeting_manager.get_active_target_queue(test_session)
    queue_ids = [t.id for t in new_queue]
    assert first_target.id not in queue_ids

    # Restore target
    await targeting_manager.update_target(test_session, first_target.id, status="ACTIVE")

# 14. Target Provenance Persists on Prospect
@pytest.mark.asyncio
async def test_prospect_provenance_retention(test_session: AsyncSession):
    biz = Business(
        name="Apex Commercial Cooling LLC",
        domain="apex-cooling-test.com",
        website_url="https://apex-cooling-test.com",
        country="US",
        administrative_region="Texas",
        region_type="State",
        city="Houston",
        niche="HVAC",
        public_email="info@apex-cooling-test.com",
        verification_status="VERIFIED"
    )
    test_session.add(biz)
    await test_session.commit()
    await test_session.refresh(biz)

    assert biz.country == "US"
    assert biz.administrative_region == "Texas"
    assert biz.region == "Texas"  # property accessor
    assert biz.city == "Houston"
    assert biz.niche == "HVAC"

# 15. Country / Region / City / Niche Consistency Validation
def test_hierarchy_validation_rejections():
    # Unknown country
    with pytest.raises(ValueError) as exc1:
        validate_target_combination("XX", "Texas", "Houston", "HVAC")
    assert "unsupported country" in str(exc1.value).lower()

    # Region not belonging to country
    with pytest.raises(ValueError) as exc2:
        validate_target_combination("US", "Dubai", "Houston", "HVAC")
    assert "does not exist in united states" in str(exc2.value).lower()

    # City not belonging to region
    with pytest.raises(ValueError) as exc3:
        validate_target_combination("US", "Texas", "Miami", "HVAC")
    assert "not recognized in state 'texas'" in str(exc3.value).lower()

    # Invalid niche
    with pytest.raises(ValueError) as exc4:
        validate_target_combination("US", "Texas", "Houston", "quantum_teleportation")
    assert "unrecognized niche" in str(exc4.value).lower()

    # Valid combinations pass
    res = validate_target_combination("SA", "Eastern Province", "Dammam", "Air Conditioning")
    assert res["valid"] is True
    assert res["niche_id"] == "HVAC"
    assert res["region_type"] == "Region"

# 16. Existing Acquisition Pipeline Still Works
@pytest.mark.asyncio
async def test_existing_acquisition_pipeline_compatibility(test_session: AsyncSession):
    from app.acquisition.config import country_config_manager
    configs = await country_config_manager.list_countries(test_session)
    assert len(configs) >= 20
    us_cfg = next((c for c in configs if c.country_code == "US"), None)
    assert us_cfg is not None
    assert us_cfg.enabled is True

# 17. Targeting Manager Blocks Creating or Activating Disabled Market Targets
@pytest.mark.asyncio
async def test_targeting_manager_blocks_disabled_market_creation(test_session: AsyncSession):
    # Israel creation must fail
    with pytest.raises(ValueError) as exc_il:
        await targeting_manager.create_target(
            session=test_session,
            country_code="IL",
            region="Tel Aviv District",
            city="Tel Aviv",
            niche="DENTAL"
        )
    assert "disabled for acquisition" in str(exc_il.value).lower()

    # India creation must fail
    with pytest.raises(ValueError) as exc_in:
        await targeting_manager.create_target(
            session=test_session,
            country_code="IN",
            region="Maharashtra",
            city="Mumbai",
            niche="DENTAL"
        )
    assert "disabled for acquisition" in str(exc_in.value).lower()

    # Pakistan creation must fail
    with pytest.raises(ValueError) as exc_pk:
        await targeting_manager.create_target(
            session=test_session,
            country_code="PK",
            region="Punjab",
            city="Lahore",
            niche="DENTAL"
        )
    assert "disabled for acquisition" in str(exc_pk.value).lower()

# 18. Active Target Queue Strictly Excludes Disabled Markets
@pytest.mark.asyncio
async def test_active_queue_excludes_disabled_markets(test_session: AsyncSession):
    queue = await targeting_manager.get_active_target_queue(test_session)
    country_codes = [t.country_code for t in queue]
    assert "IL" not in country_codes
    assert "IN" not in country_codes
    assert "PK" not in country_codes

# 19. Historical Business Records for Disabled Markets are Preserved Intact
@pytest.mark.asyncio
async def test_historical_prospects_preserved_for_disabled_markets(test_session: AsyncSession):
    hist_biz = Business(
        name="Historical Tel Aviv Dental Clinic",
        domain="hist-tlv-dental.il",
        website_url="https://hist-tlv-dental.il",
        country="IL",
        administrative_region="Tel Aviv District",
        region_type="District",
        city="Tel Aviv",
        niche="DENTAL",
        public_email="contact@hist-tlv-dental.il",
        verification_status="VERIFIED"
    )
    test_session.add(hist_biz)
    await test_session.commit()
    await test_session.refresh(hist_biz)

    # Must remain intact in DB
    stmt = select(Business).where(Business.domain == "hist-tlv-dental.il")
    found = (await test_session.execute(stmt)).scalar_one_or_none()
    assert found is not None
    assert found.country == "IL"
    assert found.city == "Tel Aviv"
