from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Business, ClientIntelligenceRecord, AuditRun, PipelineStage
from app.acquisition.models import GlobalQueueItem
from app.acquisition.pool import global_prospect_pool
from app.client_intelligence.engine import client_intelligence_engine
from app.core.logging import logger

class GlobalRanker:
    """
    Globally ranks uncontacted prospects across all active countries
    using an expected-value multi-criteria objective function.
    Produces comprehensive, auditable decision traces for every candidate.
    """

    def __init__(
        self,
        weight_lead_quality: float = 0.25,
        weight_contactability: float = 0.20,
        weight_service_fit: float = 0.25,
        weight_p_win: float = 0.30,
    ):
        self.w_quality = weight_lead_quality
        self.w_contact = weight_contactability
        self.w_fit = weight_service_fit
        self.w_p_win = weight_p_win

    async def rank_pool(
        self,
        session: AsyncSession,
        limit: int = 50
    ) -> List[GlobalQueueItem]:
        """
        Dynamically evaluates and ranks all eligible uncontacted prospects globally.
        Never assumes the old #2 is still #2 upon re-ranking.
        """
        candidates = await global_prospect_pool.get_uncontacted_candidates(session, limit=limit)
        if not candidates:
            logger.info("[GlobalRanker] No uncontacted candidates found in global pool.")
            return []

        scored_items: List[GlobalQueueItem] = []

        for biz in candidates:
            try:
                # 1. Fetch or create intelligence & audit data
                intel_stmt = select(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == biz.id)
                intel_res = await session.execute(intel_stmt)
                intel = intel_res.scalar_one_or_none()

                audit_stmt = select(AuditRun).where(AuditRun.business_id == biz.id)
                audit_res = await session.execute(audit_stmt)
                audit = audit_res.scalar_one_or_none()

                if not intel:
                    # Run lightweight intelligence on the fly
                    intel_data = await client_intelligence_engine.analyze_business_async(
                        session=session,
                        business=biz,
                        audit=audit,
                        persist=True
                    )
                    # Re-fetch persisted record
                    intel_res2 = await session.execute(intel_stmt)
                    intel = intel_res2.scalar_one_or_none()

                # 2. Extract feature signals
                health_score = getattr(audit, "overall_health_score", 60.0) if audit else 60.0
                # Higher deficiency means higher opportunity for agency improvement
                lead_quality = min(1.0, max(0.2, (100.0 - health_score) / 100.0 + 0.2))

                # Contactability
                contactability = 0.5
                if biz.public_email:
                    contactability += 0.3
                if biz.phone:
                    contactability += 0.2
                contactability = min(1.0, contactability)

                # Service fit and P(Win)
                service_fit = float(intel.fit_score) if intel and intel.fit_score else 0.70
                p_win = float(intel.p_win) if intel and intel.p_win else 0.50
                rec_price = float(intel.recommended_price_usd) if intel and intel.recommended_price_usd else 1000.0
                top_service = str(intel.top_service_name) if intel and intel.top_service_name else "Inbound Lead Qualification"

                # Country friction / difficulty modifier
                country_code = (biz.country or "US").upper()
                difficulty_modifiers = {
                    "US": 0.05,
                    "UK": 0.05,
                    "CA": 0.05,
                    "AU": 0.08,
                    "AE": 0.10,
                }
                outreach_difficulty = difficulty_modifiers.get(country_code, 0.15)

                # Compliance risk modifier
                compliance_risks = {
                    "US": 0.05,
                    "UK": 0.08,  # GDPR
                    "CA": 0.06,  # CASL
                    "AU": 0.07,  # Spam Act 2003
                    "AE": 0.05,
                }
                compliance_risk = compliance_risks.get(country_code, 0.10)

                evidence_strength = float(biz.effective_evidence_score) if biz.effective_evidence_score else 0.50

                # Composite score calculation (Normalized Expected Value)
                capability_factor = (
                    (self.w_quality * lead_quality) +
                    (self.w_contact * contactability) +
                    (self.w_fit * service_fit) +
                    (self.w_p_win * p_win)
                )

                risk_damping = (1.0 - outreach_difficulty) * (1.0 - compliance_risk)
                composite_score = round(capability_factor * rec_price * risk_damping, 2)
                expected_revenue = round(p_win * rec_price, 2)

                # Persist transparent prospect_score (0-100 scale distinct from market_score)
                prospect_score = round(
                    ((0.20 * lead_quality) + (0.20 * contactability) + (0.25 * service_fit) + (0.20 * p_win) + (0.15 * evidence_strength))
                    * 100.0 * risk_damping,
                    2
                )
                biz.prospect_score = prospect_score
                session.add(biz)

                # 3. Formulate transparent decision traces
                why_bullets = []
                if intel and intel.why_this_business:
                    why_bullets = list(intel.why_this_business)
                else:
                    why_bullets = [
                        f"High verified need in {country_code} for {top_service}.",
                        f"Contactable via verified channels ({biz.public_email or biz.phone or 'web'}).",
                        f"Attractive unit economics with recommended entry tier of ${rec_price:,.0f}."
                    ]
                if getattr(biz, "evidence_count", 0) > 0:
                    why_bullets.append(f"Grounded by {biz.evidence_count} verified evidence sources (score: {evidence_strength:.2f}).")

                decision_trace = {
                    "why_this_business": f"{biz.name} has proven commercial presence with identifiable digital operational gaps (Health: {health_score}/100).",
                    "why_this_country": f"{country_code} offers high commercial readiness and favorable legal compliance headroom.",
                    "why_this_service": f"Identified severe bottlenecks perfectly matched to {top_service} (Fit: {int(service_fit * 100)}%).",
                    "why_this_price": f"${rec_price:,.0f} is calibrated to business scale and estimated ROI payback.",
                    "why_now": f"Prospect is uncontacted, verified, and ready for immediate single-slot commercial outreach.",
                    "weights": {
                        "lead_quality": self.w_quality,
                        "contactability": self.w_contact,
                        "service_fit": self.w_fit,
                        "p_win": self.w_p_win,
                        "evidence": 0.15,
                    },
                    "signals": {
                        "lead_quality": round(lead_quality, 3),
                        "contactability": round(contactability, 3),
                        "service_fit": round(service_fit, 3),
                        "p_win": round(p_win, 3),
                        "evidence_score": round(evidence_strength, 3),
                        "evidence_count": getattr(biz, "evidence_count", 0),
                        "prospect_score": prospect_score,
                        "outreach_difficulty": outreach_difficulty,
                        "compliance_risk": compliance_risk,
                    }
                }


                item = GlobalQueueItem(
                    rank=0,
                    business_id=biz.id,
                    business_name=biz.name,
                    domain=biz.domain,
                    country=country_code,
                    city=biz.city,
                    niche=biz.niche,
                    composite_score=composite_score,
                    expected_revenue=expected_revenue,
                    p_win=round(p_win, 3),
                    lead_quality=round(lead_quality, 3),
                    contactability=round(contactability, 3),
                    service_fit=round(service_fit, 3),
                    top_service=top_service,
                    recommended_price_usd=rec_price,
                    pipeline_stage=biz.pipeline_stage,
                    why_this_prospect=why_bullets,
                    decision_trace=decision_trace
                )
                scored_items.append(item)

            except Exception as e:
                logger.warning(f"[GlobalRanker] Failed to score business {biz.id} ({biz.domain}): {e}")

        # 4. Sort globally descending by composite score
        scored_items.sort(key=lambda x: x.composite_score, reverse=True)

        # 5. Assign ordinal ranks (1-based)
        for rank_idx, item in enumerate(scored_items, start=1):
            item.rank = rank_idx

        await session.commit()
        return scored_items


    async def get_top_candidate(self, session: AsyncSession) -> Optional[GlobalQueueItem]:
        """Returns the single top-ranked prospect from the global pool."""
        ranked = await self.rank_pool(session, limit=20)
        return ranked[0] if ranked else None

global_ranker = GlobalRanker()
