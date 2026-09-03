#!/usr/bin/env python3
"""
scripts/run_prospecting_cycle.py
==============================================================================
Real Local-First B2B Prospecting & Commercial Qualification Cycle
Operates safely in local DRY-RUN mode (NO automated emails dispatched).
Executes:
  Discovery -> Normalization -> Deduplication -> Quality Filtering ->
  Website Auditing -> Buyer Scoring -> Opportunity Scoring ->
  $500+ Commercial Qualification -> Database Persistence -> Output Report
==============================================================================
"""

import sys
import os
import asyncio
import argparse
from typing import List, Dict, Any

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.connection import AsyncSessionLocal
from app.lead_generation.targeting import load_targeting_config, TargetingConfig
from app.lead_generation.providers.prospect_provider import RealProspectProvider, MockProspectProvider
from app.lead_generation.service import LeadDiscoveryService
from app.lead_generation.schemas import ScoredProspect, ProspectClassification, RealPipelineStage
from app.core.logging import logger

async def run_prospecting_cycle(
    provider_type: str = "real",
    country: str = None,
    city: str = None,
    niche: str = None,
    limit: int = None
):
    print("==================================================")
    print("JARVIS // AG — AUTONOMOUS PROSPECTING CYCLE")
    print("Mode: LOCAL DRY-RUN (Real Discovery, Zero Emails)")
    print("==================================================")

    # 1. Load Configuration
    targeting = load_targeting_config()

    # Apply overrides if provided
    if country:
        targeting.country_code = country.upper()
        targeting.country = country
    if city:
        targeting.cities = [city]
    if niche:
        targeting.niches = [niche]
    if limit:
        targeting.filters.target_results_per_city = limit

    # Select Provider
    if provider_type.lower() == "mock":
        provider = MockProspectProvider()
        provider_name = "MockProspectProvider (Deterministic Test Registry)"
    else:
        provider = RealProspectProvider()
        provider_name = "RealProspectProvider (OpenStreetMap & Public Registries)"

    print(f"\nProvider: {provider_name}")
    print(f"Targeting: {targeting.country_code} | Cities: {', '.join(targeting.cities)} | Niches: {', '.join(targeting.niches)}")
    print(f"Commercial Threshold: ${targeting.commercial.minimum_target_service_value_usd}+ Contract Value")
    print("--------------------------------------------------\n")

    service = LeadDiscoveryService(provider=provider)

    async with AsyncSessionLocal() as session:
        # 2-9. Run Discovery, Normalization, Deduplication, Auditing, and Scoring
        valid_businesses, stats = await service.discover_and_process(
            targeting=targeting,
            db=session,
            check_existing_db=True
        )

    # Compile Top Prospects
    top_prospects = []
    high_value_count = 0
    qualified_count = 0
    five_hundred_plus_count = 0

    for biz in valid_businesses:
        scored: ScoredProspect = getattr(biz, "_scored", None)
        if not scored:
            continue

        est_val = scored.estimated_service_value
        b_score = scored.buyer_score.score
        opp_score = scored.opportunity_score

        if est_val.min_value >= targeting.commercial.minimum_target_service_value_usd:
            five_hundred_plus_count += 1
        if b_score >= targeting.commercial.high_value_buyer_threshold:
            high_value_count += 1
        if opp_score >= targeting.commercial.opportunity_score_threshold:
            qualified_count += 1

        top_prospects.append({
            "name": biz.name,
            "country": biz.country,
            "niche": biz.niche,
            "buyer_score": b_score,
            "opportunity_score": opp_score,
            "est_value": f"${est_val.min_value:,} - ${est_val.max_value:,}",
            "classification": scored.classification.value,
            "priority": scored.classification == ProspectClassification.PRIORITY_PROSPECT
        })

    # Sort: Priority prospects first, then by buyer score descending
    top_prospects.sort(key=lambda p: (1 if p["priority"] else 0, p["buyer_score"]), reverse=True)

    # 11. Print Required Output Report Format
    print("\nPROSPECTING CYCLE")
    print("-----------------")
    print(f"Markets searched: {stats.markets_searched}")
    print(f"Businesses discovered: {stats.businesses_discovered}")
    print(f"Duplicates rejected: {stats.duplicates_removed}")
    print(f"Invalid businesses rejected: {stats.invalid_rejected}")
    print(f"Websites audited: {stats.websites_audited}")
    print("")
    print("HIGH-VALUE:")
    print(f"{high_value_count}")
    print("")
    print("QUALIFIED:")
    print(f"{qualified_count}")
    print("")
    print("$500+ prospects:")
    print(f"{five_hundred_plus_count}")
    print("")
    print("TOP PROSPECTS:")
    if top_prospects:
        for idx, p in enumerate(top_prospects[:10], 1):
            star = " ★" if p["priority"] else ""
            print(f"{idx}. {p['name']} — {p['country']} — {p['niche']} — Buyer Score: {p['buyer_score']} — Opportunity: {p['opportunity_score']} — Est. Value: {p['est_value']}{star}")
    else:
        print("No new qualifying prospects discovered in this cycle.")

    if stats.rejection_reasons:
        print("\nREJECTION AUDIT BREAKDOWN:")
        for reason, count in stats.rejection_reasons.items():
            print(f"  • {reason}: {count}")

    print("\n[SAFETY GUARD ACTIVE] Real outreach is DISABLED. Discovered prospects stored in database pending operator review.")
    return stats

def main():
    parser = argparse.ArgumentParser(description="Run autonomous prospect discovery cycle in dry-run mode.")
    parser.add_argument("--provider", choices=["real", "mock"], default="real", help="Discovery provider (default: real)")
    parser.add_argument("--country", type=str, default=None, help="Target country code (e.g. US, UK, CA, AU)")
    parser.add_argument("--city", type=str, default=None, help="Target city (e.g. Austin, London, Toronto)")
    parser.add_argument("--niche", type=str, default=None, help="Target niche (e.g. HVAC, Roofing, Plumbing)")
    parser.add_argument("--limit", type=int, default=15, help="Max results per city (default: 15)")

    args = parser.parse_args()

    asyncio.run(run_prospecting_cycle(
        provider_type=args.provider,
        country=args.country,
        city=args.city,
        niche=args.niche,
        limit=args.limit
    ))

if __name__ == "__main__":
    main()
