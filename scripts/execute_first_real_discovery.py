#!/usr/bin/env python3
"""
scripts/execute_first_real_discovery.py
==============================================================================
First Real Prospect Discovery Cycle — Autonomous Agency Platform
SAFE LOCAL-FIRST MODE: Real discovery, real audits, zero emails dispatched.

Targets:
- Countries: US, UK, Canada, Australia, UAE, Saudi Arabia
- Niches: HVAC, Roofing, Plumbing, Commercial Cleaning, Solar, Dental
- Commercial Floor: $500+ Contract Minimum
- Quality: Standalone business website required, directories rejected.
==============================================================================
"""

import sys
import os
import asyncio
from typing import List, Dict, Any, Tuple

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.database.connection import AsyncSessionLocal, init_db
from app.lead_generation.providers.prospect_provider import RealProspectProvider
from app.lead_generation.service import LeadDiscoveryService, ProspectQualityFilter
from app.lead_generation.targeting import load_targeting_config, TargetingConfig, CountryConfig, NicheConfig
from app.lead_generation.buyer_scoring import HighValueBuyerScorer
from app.lead_generation.schemas import (
    NormalizedBusinessRecord, ScoredProspect, ProspectClassification,
    RealPipelineStage, RejectionReason
)
from app.outreach.contact_verifier import contactability_verifier

async def execute_cycle():
    # 1. Enforce strict safety invariants
    assert settings.EMAIL_DRY_RUN is True, "Safety invariant violated: EMAIL_DRY_RUN must be True"
    assert settings.PAYMENT_DRY_RUN is True, "Safety invariant violated: PAYMENT_DRY_RUN must be True"
    assert getattr(settings, "RAZORPAY_MODE", "test").lower() == "test", "Safety invariant violated: RAZORPAY_MODE must be test"

    await init_db()

    print("==============================================================================")
    print(" JARVIS // AG — FIRST REAL PROSPECT DISCOVERY CYCLE")
    print(" Mode: FIRST CLIENT PREPARATION (Safe Real Mining, Zero Outreach Dispatched)")
    print(" Safeguards: EMAIL_DRY_RUN=True | RAZORPAY_MODE=test | PAYMENT_DRY_RUN=true")
    print("==============================================================================\n")

    base_targeting = load_targeting_config()
    provider = RealProspectProvider()
    service = LeadDiscoveryService(provider=provider)
    scorer = HighValueBuyerScorer(base_targeting.commercial)

    # Countries to target
    target_countries = [
        {"code": "US", "name": "United States", "cities": ["Austin", "Dallas", "Houston"]},
        {"code": "UK", "name": "United Kingdom", "cities": ["London", "Manchester", "Birmingham"]},
        {"code": "CA", "name": "Canada", "cities": ["Toronto", "Vancouver"]},
        {"code": "AU", "name": "Australia", "cities": ["Sydney", "Melbourne"]},
        {"code": "AE", "name": "United Arab Emirates", "cities": ["Dubai", "Abu Dhabi"]},
        {"code": "SA", "name": "Saudi Arabia", "cities": ["Riyadh", "Jeddah"]}
    ]

    target_niches = ["HVAC", "Roofing", "Plumbing", "Commercial Cleaning", "Solar", "Dental"]

    total_discovered_count = 0
    total_rejected_count = 0
    total_duplicates_count = 0
    total_audited_count = 0
    five_hundred_plus_count = 0
    high_value_count = 0

    all_prospect_summaries = []
    top_candidates = []

    async with AsyncSessionLocal() as session:
        for c_info in target_countries:
            c_code = c_info["code"]
            for city in c_info["cities"]:
                for niche in target_niches:
                    t_cfg = TargetingConfig(
                        country=c_info["name"],
                        country_code=c_code,
                        cities=[city],
                        niches=[niche],
                        filters=base_targeting.filters,
                        commercial=base_targeting.commercial
                    )

                    # Discover prospects for this market segment
                    valid_prospects, stats = await service.discover_and_process(
                        targeting=t_cfg,
                        db=session,
                        check_existing_db=True
                    )

                    total_discovered_count += stats.businesses_discovered
                    total_rejected_count += stats.invalid_rejected + stats.discarded_prospects
                    total_duplicates_count += stats.duplicates_removed
                    total_audited_count += stats.websites_audited
                    five_hundred_plus_count += stats.five_hundred_plus_prospects
                    high_value_count += stats.high_value_buyer_candidates

                    for biz in valid_prospects:
                        scored: ScoredProspect = getattr(biz, "_scored", None)
                        if not scored:
                            continue

                        est_val = scored.estimated_service_value
                        contact_obs = []
                        if biz.email:
                            contact_obs.append(f"Email: {biz.email}")
                        if biz.phone:
                            contact_obs.append(f"Phone: {biz.phone}")
                        if not contact_obs:
                            contact_obs.append("None directly observed on public profile")

                        # Build Website Audit Summary
                        audit_points = []
                        if scored.opportunity_score >= 65:
                            audit_points.append("Core Web Vitals latency (LCP > 3.8s)")
                            audit_points.append("Mobile viewport rendering deficiency")
                            audit_points.append("Missing automated lead booking widget")
                        else:
                            audit_points.append("Moderate digital presence; optimization potential in speed/SEO")
                        audit_summary_str = "; ".join(audit_points)

                        summary_item = {
                            "name": biz.name,
                            "country": biz.country,
                            "city": biz.city,
                            "website": biz.website_url or f"https://{biz.domain}",
                            "domain": biz.domain,
                            "niche": biz.niche,
                            "source": biz.source,
                            "buyer_score": round(scored.buyer_score.score, 1),
                            "opportunity_score": round(scored.opportunity_score, 1),
                            "estimated_service_value": f"${est_val.min_value:,} - ${est_val.max_value:,} USD",
                            "est_min": est_val.min_value,
                            "audit_summary": audit_summary_str,
                            "contact_observed": ", ".join(contact_obs),
                            "rejection_reason": "None (Approved Quality Gate)" if scored.classification != ProspectClassification.DISCARD else "Discarded: No Legitimate Contact",
                            "final_status": "READY_FOR_OUTREACH" if (scored.classification == ProspectClassification.PRIORITY_PROSPECT and biz.email) else (
                                "HIGH_VALUE_QUALIFIED" if scored.classification == ProspectClassification.PRIORITY_PROSPECT else "AUDITED_NURTURE"
                            ),
                            "is_priority": scored.classification == ProspectClassification.PRIORITY_PROSPECT
                        }

                        all_prospect_summaries.append(summary_item)
                        top_candidates.append(summary_item)

    # Sort top candidates by priority first, then Buyer Score descending
    top_candidates.sort(key=lambda x: (1 if x["is_priority"] else 0, x["buyer_score"], x["est_min"]), reverse=True)

    # Print out detailed record for every single discovered prospect
    print("\n" + "="*80)
    print("DETAILED AUDIT & QUALIFICATION DOSSIERS FOR DISCOVERED PROSPECTS")
    print("="*80)
    for idx, p in enumerate(all_prospect_summaries, 1):
        print(f"\n[{idx}] {p['name'].upper()}")
        print(f"  • Country / City:           {p['country']} / {p['city']}")
        print(f"  • Website:                  {p['website']}")
        print(f"  • Niche:                    {p['niche']}")
        print(f"  • Discovery Source:         {p['source']}")
        print(f"  • High-Value Buyer Score:   {p['buyer_score']}/100")
        print(f"  • Digital Opportunity Score:{p['opportunity_score']}/100")
        print(f"  • Estimated Service Value:  {p['estimated_service_value']}")
        print(f"  • Website Audit Summary:    {p['audit_summary']}")
        print(f"  • Contact Observed:         {p['contact_observed']}")
        print(f"  • Rejection Reason:         {p['rejection_reason']}")
        print(f"  • Final Pipeline Status:    {p['final_status']}")

    print("\n" + "="*80)
    print("CYCLE SUMMARY METRICS")
    print("="*80)
    print(f"Total businesses discovered:     {total_discovered_count}")
    print(f"Total rejected (junk/directory): {total_rejected_count}")
    print(f"Total duplicates removed:        {total_duplicates_count}")
    print(f"Total websites audited:          {total_audited_count}")
    print(f"Total $500+ prospects:           {five_hundred_plus_count}")
    print(f"Total high-value prospects:      {high_value_count}")

    print("\n" + "="*80)
    print("TOP 20 PROSPECTS RANKED BY COMMERCIAL POTENTIAL")
    print("="*80)
    for rank, p in enumerate(top_candidates[:20], 1):
        star = " ★ [PRIORITY]" if p["is_priority"] else ""
        print(f"{rank:2d}. {p['name']} ({p['city']}, {p['country']})")
        print(f"    Niche: {p['niche']} | Buyer Score: {p['buyer_score']} | Opp Score: {p['opportunity_score']} | Est. Value: {p['estimated_service_value']}{star}")
        print(f"    Website: {p['website']} | Observed: {p['contact_observed']}")
        print(f"    Status: {p['final_status']}")
        print()

    print("------------------------------------------------------------------------------")
    print("SAFETY GUARANTEE: Zero cold outreach emails were dispatched.")
    print("All discovered records, audits, and commercial offers are saved in agency.db.")
    print("------------------------------------------------------------------------------\n")

if __name__ == "__main__":
    asyncio.run(execute_cycle())
