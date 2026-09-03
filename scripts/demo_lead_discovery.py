"""
Standalone Demo Script: Real Lead Discovery Engine with High-Value Client Filter.
Demonstrates:
1. Loading targeting and commercial configuration from YAML
2. Discovering candidates via MockLeadDiscoveryProvider
3. Normalizing business records
4. Multi-vector deduplication (domain, phone, name)
5. Calculating High-Value Buyer Score (0-100) and Opportunity Score (0-100)
6. Applying strict commercial threshold gating:
   - High-Value Buyer >= 75
   - Opportunity Score >= 65
   - Legitimate Contact Path
7. Classifying prospects: DISCARD, LOW_VALUE, NURTURE, PRIORITY_PROSPECT
8. Persisting prospects to database with full audit trail
9. Printing a comprehensive Commercial Discovery Report
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
from app.models.entities import LocalBusiness

async def run_discovery_demo():
    print("\n" + "#"*75)
    print("  LOCAL-FIRST REAL LEAD DISCOVERY ENGINE WITH HIGH-VALUE CLIENT FILTER")
    print("  Commercial Target: US Local Businesses with $1,000+ Purchasing Capacity")
    print("#"*75 + "\n")

    # Step 1: Load targeting configuration
    config_path = "config/targeting.yaml"
    print(f"STEP 1: Loading targeting & commercial configuration from '{config_path}'...")
    targeting = load_targeting_config(config_path)
    print(f"✓ Target Country:           {targeting.country} ({targeting.country_code})")
    print(f"✓ Target Regions:           {', '.join(targeting.regions)}")
    print(f"✓ Target Cities:            {', '.join(targeting.cities)}")
    print(f"✓ Target Niches:            {', '.join(targeting.niches)}")
    print(f"✓ Min Target Service Value: ${targeting.commercial.minimum_target_service_value_usd:,} USD")
    print(f"✓ High-Value Buyer Gate:    Score >= {targeting.commercial.high_value_buyer_threshold:.0f}/100")
    print(f"✓ Opportunity Score Gate:   Score >= {targeting.commercial.opportunity_score_threshold:.0f}/100")

    # Step 2: Initialize Database
    print("\nSTEP 2: Initializing database storage & schema...")
    await init_db()
    print("✓ Database ready.")

    # Step 3: Run Discovery Service with Mock Provider
    print("\nSTEP 3: Initiating discovery with observable scale & opportunity signals...")
    provider = MockLeadDiscoveryProvider()
    service = LeadDiscoveryService(provider=provider)

    async with AsyncSessionLocal() as db:
        # Cleanly reset any previous mock discovery records for deterministic repeatable demonstration
        from sqlalchemy import delete
        await db.execute(delete(LocalBusiness).where(LocalBusiness.source == "mock_directory"))
        await db.commit()

        # Run discovery
        prospects, stats = await service.discover_and_process(targeting, db, check_existing_db=True)

        print("\n" + "="*75)
        print("                 COMMERCIAL DISCOVERY REPORT                 ")
        print("="*75)
        print(f"Businesses discovered:         {stats.businesses_discovered}")
        print(f"Valid businesses:              {stats.valid_businesses}")
        print(f"Duplicates removed:            {stats.duplicates_removed}")
        print(f"High-value buyer candidates:   {stats.high_value_buyer_candidates}")
        print(f"High-opportunity candidates:   {stats.high_opportunity_candidates}")
        print(f"Priority prospects:            {stats.priority_prospects}")
        print(f"Discarded prospects:           {stats.discarded_prospects}")
        print(f"Average buyer score:           {stats.average_buyer_score:.1f}/100")
        print(f"Average opportunity score:     {stats.average_opportunity_score:.1f}/100")
        print(f"With websites:                 {stats.with_websites}")
        print(f"With phone numbers:            {stats.with_phone_numbers}")
        print(f"Cities covered:                {', '.join(stats.cities_covered)}")
        print("="*75)

        print("\nSAMPLE PRIORITY PROSPECTS ($1,000+ COMMERCIAL TARGETS):")
        print("-" * 75)
        priority_list = [p for p in prospects if getattr(p, "_scored", None) and p._scored.classification.value == "PRIORITY_PROSPECT"]
        for i, p in enumerate(priority_list[:5]):
            sc = p._scored
            print(f"\n[{i+1}] {p.name} ({p.city}, TX) - Rating: {p.rating}★ ({p.review_count} rev)")
            print(f"    • High-Value Buyer Score:  {sc.buyer_score.score:.1f}/100 (Tier: {sc.buyer_score.tier.value})")
            print(f"    • Opportunity Score:       {sc.opportunity_score:.1f}/100")
            print(f"    • Estimated Budget Range:  {sc.buyer_score.estimated_service_budget}")
            print(f"    • Observable Scale:        {', '.join(sc.buyer_score.buying_capacity_signals[:2])}")
            print(f"    • Digital Bottlenecks:     {', '.join(sc.buyer_score.opportunity_signals[:2])}")
            print(f"    • Classification:          {sc.classification.value}")
        print("-" * 75)

        print("\nSAMPLE NURTURE PROSPECT (HIGH CAPACITY, LOW IMMEDIATE BOTTLENECK):")
        nurture_list = [p for p in prospects if getattr(p, "_scored", None) and p._scored.classification.value == "NURTURE"]
        if nurture_list:
            np = nurture_list[0]
            print(f"  • {np.name} ({np.city}): Buyer Score: {np._scored.buyer_score.score:.1f}, Opp Score: {np._scored.opportunity_score:.1f}")
            print(f"    Rationale: {np._scored.classification_rationale}")

        print("\nSAMPLE LOW VALUE PROSPECT (SMALL SCALE SOLO TECHNICIAN):")
        low_list = [p for p in prospects if getattr(p, "_scored", None) and p._scored.classification.value == "LOW_VALUE"]
        if low_list:
            lp = low_list[0]
            print(f"  • {lp.name} ({lp.city}): Buyer Score: {lp._scored.buyer_score.score:.1f}, Opp Score: {lp._scored.opportunity_score:.1f}")
            print(f"    Rationale: {lp._scored.classification_rationale}")

    print("\n" + "#"*75)
    print("  ✓ HIGH-VALUE CLIENT DISCOVERY ENGINE DEMONSTRATION COMPLETE")
    print("#"*75 + "\n")

if __name__ == "__main__":
    asyncio.run(run_discovery_demo())
