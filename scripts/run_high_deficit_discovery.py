import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, AuditFinding, LeadScore, Offer,
    PipelineStage, PipelineEvent, Country, Niche
)
from app.market_intelligence.autonomous_market_engine import autonomous_market_engine
from app.lead_generation.discovery import lead_discovery_coordinator
from app.auditing.engine import website_audit_engine
from app.scoring.engine import lead_scoring_engine
from app.offers.generator import offer_engine
from app.outreach.personalization import outreach_personalizer
from app.outreach.compliance import compliance_guard

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('high_deficit_discovery')

COMMERCIAL_PRICE_FLOOR = 500.0
QUALIFICATION_SCORE_FLOOR = 55.0
HARD_EXCLUSIONS = {'IN', 'PK', 'IL'}

async def run_cycle():
    async with AsyncSessionLocal() as session:
        logger.info('Querying dynamic active market portfolio from autonomous_market_engine...')
        portfolio_data = await autonomous_market_engine.get_autonomous_target_queue(session)
        target_queue = portfolio_data.get('active_portfolio', [])
        logger.info(f'Autonomous engine returned {len(target_queue)} targets in active portfolio.')
        
        # Filter out hard exclusions
        valid_targets = [t for t in target_queue if t['country_code'].upper() not in HARD_EXCLUSIONS]
        logger.info(f'{len(valid_targets)} targets eligible after country compliance filters.')

        # Pick diverse targets across different countries/regions
        seen_countries = set()
        chosen_targets = []
        for t in valid_targets:
            if t['country_code'] not in seen_countries or len(seen_countries) < 3:
                chosen_targets.append(t)
                seen_countries.add(t['country_code'])
            if len(chosen_targets) >= 4:
                break

        if not chosen_targets:
            chosen_targets = valid_targets[:3]

        logger.info(f'Selected {len(chosen_targets)} dynamic targets for high-deficit exploration:')
        for ct in chosen_targets:
            logger.info(f'  Target: {ct["country_code"]} | {ct["city"]} | {ct["niche_id"]} ({ct.get("type")}) - Cap: {ct.get("allocated_daily_capacity")}')

        all_candidate_records = []
        total_discovered = 0
        total_verified = 0
        total_audited = 0
        reachable_count = 0
        valid_contacts_count = 0

        for target_item in chosen_targets:
            c_code = target_item['country_code'].upper()
            n_slug = target_item['niche_id']
            logger.info(f'=== Starting discovery for {c_code} - {n_slug} ===')
            
            # Step 1: Discover & Verify
            discovered_bizs = await lead_discovery_coordinator.run_discovery_and_verification(
                session=session,
                country_code=c_code,
                niche_slug=n_slug,
                target_count=4
            )
            logger.info(f'Discovery coordinator returned {len(discovered_bizs)} leads for {c_code} - {n_slug}.')
            total_discovered += len(discovered_bizs)

            for biz in discovered_bizs:
                if biz.country in HARD_EXCLUSIONS:
                    logger.error(f'CRITICAL: Hard-excluded country lead discovered: {biz.country} #{biz.id}')
                    biz.pipeline_stage = PipelineStage.REJECTED.value
                    await session.commit()
                    continue

                if biz.verification_status == 'VERIFIED':
                    total_verified += 1
                else:
                    logger.info(f'Lead #{biz.id} ({biz.domain}) failed verification. Stage: {biz.pipeline_stage}')
                    all_candidate_records.append({
                        'id': biz.id,
                        'name': biz.name,
                        'domain': biz.domain,
                        'country': biz.country,
                        'city': biz.city,
                        'niche': biz.niche,
                        'score': 0.0,
                        'health_score': 0.0,
                        'contact_email': biz.public_email,
                        'contact_phone': biz.phone,
                        'reachable': False,
                        'audit_findings_count': 0,
                        'exact_findings': [],
                        'decision': PipelineStage.REJECTED.value,
                        'rejection_reason': 'Verification failed at intake'
                    })
                    continue

                # Step 2: Audit
                logger.info(f'Auditing verified business #{biz.id}: {biz.name} ({biz.website_url})...')
                audit_run = await website_audit_engine.audit_business(session, biz)
                total_audited += 1

                is_reachable = audit_run.overall_health_score > 0.0 and 'RESEARCH_INSUFFICIENT' not in (audit_run.summary or '')
                if is_reachable:
                    reachable_count += 1

                if biz.public_email:
                    valid_contacts_count += 1

                findings_summary = []
                q_findings = select(AuditFinding).where(AuditFinding.audit_id == audit_run.id)
                findings = (await session.execute(q_findings)).scalars().all()
                for f in findings:
                    findings_summary.append({
                        'category': f.category,
                        'finding': f.finding,
                        'severity': f.severity,
                        'evidence': f.evidence
                    })

                # Step 3: Score & Offer
                if not is_reachable:
                    score_val = 0.0
                    biz.pipeline_stage = PipelineStage.REJECTED.value
                    decision = PipelineStage.REJECTED.value
                    rejection_reason = f'Website unreachable or blocked ({audit_run.summary})'
                    logger.info(f'Business #{biz.id} ({biz.domain}) unreachable -> REJECTED')
                else:
                    lead_score = await lead_scoring_engine.score_business(session, biz)
                    score_val = lead_score.total_score
                    offer = await offer_engine.generate_offer_for_business(session, biz)
                    offer_price = float(getattr(offer, 'recommended_price', 0.0) or 0.0)

                    # Step 4: Strict Dual Gate Invariant
                    # lead_score >= 55.0 AND offer_price >= 500 AND verification passed AND audit completed AND compliance passed
                    if score_val >= QUALIFICATION_SCORE_FLOOR and offer_price >= COMMERCIAL_PRICE_FLOOR:
                        biz.pipeline_stage = PipelineStage.QUALIFIED.value
                        decision = PipelineStage.QUALIFIED.value
                        rejection_reason = None
                        logger.info(f'QUALIFIED LEAD #{biz.id}: {biz.name} | Score: {score_val} | Price: ${offer_price:.0f}')

                        # CEO Approval Gate Staging
                        if biz.public_email:
                            comp = compliance_guard.check_outreach_compliance(
                                recipient_email=biz.public_email,
                                country_code=biz.country,
                                domain=biz.domain
                            )
                            if comp.get("allowed", True):
                                try:
                                    staged_msg = await outreach_personalizer.prepare_outreach_for_business(
                                        session=session,
                                        business=biz,
                                        auto_approve=False  # STRICT CEO APPROVAL GATE
                                    )
                                    logger.info(f'STAGED FOR CEO REVIEW: OutreachMessage #{staged_msg.id} for {biz.name} ({biz.public_email})')
                                except Exception as ex:
                                    logger.error(f'Failed staging outreach for #{biz.id}: {ex}')
                            else:
                                logger.info(f'Compliance check blocked #{biz.id}: {comp.get("reason")}')
                        else:
                            logger.info(f'Lead #{biz.id} has no email; cannot stage for email outreach.')
                    else:
                        biz.pipeline_stage = PipelineStage.REJECTED.value
                        decision = PipelineStage.REJECTED.value
                        reasons = []
                        if score_val < QUALIFICATION_SCORE_FLOOR:
                            reasons.append(f'Score {score_val:.1f} < {QUALIFICATION_SCORE_FLOOR}')
                        if offer_price < COMMERCIAL_PRICE_FLOOR:
                            reasons.append(f'Price ${offer_price:.0f} < ${COMMERCIAL_PRICE_FLOOR:.0f}')
                        rejection_reason = '; '.join(reasons)
                        logger.info(f'REJECTED LEAD #{biz.id}: {biz.name} | Score: {score_val} | Reason: {rejection_reason}')

                await session.commit()

                all_candidate_records.append({
                    'id': biz.id,
                    'name': biz.name,
                    'domain': biz.domain,
                    'country': biz.country,
                    'city': biz.city,
                    'niche': biz.niche,
                    'score': score_val,
                    'health_score': audit_run.overall_health_score,
                    'contact_email': biz.public_email,
                    'contact_phone': biz.phone,
                    'reachable': is_reachable,
                    'audit_findings_count': len(findings_summary),
                    'exact_findings': findings_summary,
                    'decision': decision,
                    'rejection_reason': rejection_reason
                })

        # Compile distribution
        score_ge_55 = [r for r in all_candidate_records if r['score'] >= 55.0]
        score_50_54_9 = [r for r in all_candidate_records if 50.0 <= r['score'] < 55.0]
        score_lt_50 = [r for r in all_candidate_records if r['score'] < 50.0]

        all_candidate_records.sort(key=lambda r: r['score'], reverse=True)

        summary_output = {
            'total_discovered': total_discovered,
            'total_verified': total_verified,
            'total_audited': total_audited,
            'reachable': reachable_count,
            'valid_contacts': valid_contacts_count,
            'score_distribution': {
                'ge_55': len(score_ge_55),
                'between_50_and_54_9': len(score_50_54_9),
                'lt_50': len(score_lt_50)
            },
            'top_candidates': all_candidate_records[:10]
        }

        with open('high_deficit_discovery_results.json', 'w', encoding='utf-8') as f:
            json.dump(summary_output, f, indent=2, ensure_ascii=False)

        print('\n' + '='*70)
        print('HIGH-DEFICIT DISCOVERY EXECUTION COMPLETED')
        print(f'Total Discovered: {total_discovered}')
        print(f'Total Verified:   {total_verified}')
        print(f'Total Audited:    {total_audited}')
        print(f'Reachable Sites:  {reachable_count}')
        print(f'Valid Contacts:   {valid_contacts_count}')
        print(f'Score >= 55.0:    {len(score_ge_55)}')
        print(f'Score 50 - 54.9:  {len(score_50_54_9)}')
        print(f'Score < 50.0:     {len(score_lt_50)}')
        print('='*70)

if __name__ == '__main__':
    asyncio.run(run_cycle())
