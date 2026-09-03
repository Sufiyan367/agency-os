"""
Standalone Demo Script: Real Lead Discovery Engine.
Loads targeting configuration, discovers prospects via provider abstraction,
deduplicates across domain/phone/name, validates, persists to database,
and prints a discovery report.
"""

import sys
import os
import asyncio

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import AsyncSessionLocal, init_db
from app.lead_generation.targeting import load_targeting_config
from app.lead_generation.providers.mock import MockLeadDiscoveryProvider
from app.lead_generation.service import LeadDiscoveryService

async def run_discovery_demo():
    print("\n" + "#"*75)
    print("  LOCAL-FIRST REAL LEAD DISCOVERY ENGINE DEMO")
    print("  Targeting: US Local Small Businesses • Provider Abstraction")
    print("#"*75 + "\n")

    # Step 1: Load targeting configuration
    config_path = "config/targeting.yaml"
    print(f"STEP 1: Loading targeting configuration from '{config_path}'...")
    targeting = load_targeting_config(config_path)
    print(f"✓ Target Country: {targeting.country} ({targeting.country_code})")
    print(f"✓ Target Regions: {', '.join(targeting.regions)}")
    print(f"✓ Target Cities:  {', '.join(targeting.cities)}")
    print(f"✓ Target Niches:  {', '.join(targeting.niches)}")
    print(f"✓ Filters: Min Rating: {targeting.filters.min_rating} | Min Reviews: {targeting.filters.min_reviews} | Require Web: {targeting.filters.require_website}")

    # Step 2: Initialize Database
    print("\nSTEP 2: Initializing database storage...")
    await init_db()
    print("✓ Database ready.")

    # Step 3: Run Discovery Service with Mock Provider
    print("\nSTEP 3: Initiating discovery through MockLeadDiscoveryProvider...")
    provider = MockLeadDiscoveryProvider()
    service = LeadDiscoveryService(provider=provider)

    async with AsyncSessionLocal() as db:
        prospects, stats = await service.discover_and_process(targeting, db)

        print("\n" + "="*75)
        print("                 DISCOVERY REPORT                 ")
        print("="*75)
        print(f"Businesses discovered: {stats.businesses_discovered}")
        print(f"Valid businesses:      {stats.valid_businesses}")
        print(f"Duplicates removed:    {stats.duplicates_removed}")
        print(f"With websites:         {stats.with_websites}")
        print(f"With phone numbers:    {stats.with_phone_numbers}")
        print(f"Cities covered:        {', '.join(stats.cities_covered)}")
        print("="*75)

        print("\nSAMPLE DISCOVERED PROSPECTS PERSISTED TO DATABASE:")
        print("-" * 75)
        for i, p in enumerate(prospects[:6]):
            print(f"{i+1}. {p.name:<38} | {p.city:<8} | Rating: {p.rating}★ ({p.review_count} rev) | {p.domain}")
        if len(prospects) > 6:
            print(f"... and {len(prospects) - 6} more valid prospects stored in database.")
        print("-" * 75)

    print("\n" + "#"*75)
    print("  ✓ LEAD DISCOVERY ENGINE DEMONSTRATION COMPLETE")
    print("#"*75 + "\n")

if __name__ == "__main__":
    asyncio.run(run_discovery_demo())
