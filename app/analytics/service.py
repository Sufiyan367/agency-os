"""
Analytics Service Layer for JARVIS // AG Decision Dashboard.
Phase 14 Production Implementation.

Strictly operates on REAL persisted database records.
Enforces zero division-by-zero errors (returns None / 'Insufficient data').
Maintains strict separation between:
  - [ACTUAL] Cash collected / real verified counts
  - [PIPELINE] Active deal/opportunity pipeline (NOT revenue)
  - [ESTIMATED] Recoverable customer value (requires mandatory disclosure)
  - [MODEL OUTPUT] P(Win), Fit Scores, Selection Scores (INTERNAL ONLY)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_, distinct, case

from app.database.models import (
    Business, AuditRun, ClientIntelligenceRecord, OutreachMessage,
    Payment, Deal, Proposal, Reply, Meeting, Customer,
    ProspectEvidence, ActiveOutreachLock, PipelineStage,
    AcquisitionRun, DiscoveryRun, Offer
)
from app.core.logging import logger

CATALOG_SERVICES = [
    {"id": "SERVICE_001", "name": "AI Receptionist & Lead Capture"},
    {"id": "SERVICE_002", "name": "Speed-to-Lead Instant Response"},
    {"id": "SERVICE_003", "name": "Review Acceleration & Reputation"},
    {"id": "SERVICE_004", "name": "Reactivation Engine"},
    {"id": "SERVICE_005", "name": "Local SEO & Visibility System"},
    {"id": "SERVICE_006", "name": "Website Performance Turnaround"},
    {"id": "SERVICE_007", "name": "Automated Booking System"},
    {"id": "SERVICE_008", "name": "Quote & Proposal Pipeline"},
    {"id": "SERVICE_009", "name": "WhatsApp & SMS Automation"},
    {"id": "SERVICE_010", "name": "VIP Customer Retention Engine"},
]


def get_cutoff_date(time_filter: Optional[str]) -> Optional[datetime]:
    """Resolves standard time filters into UTC cutoff datetime."""
    if not time_filter or time_filter.lower() in ("all", "all_time", ""):
        return None
    tf = time_filter.lower().strip()
    now = datetime.utcnow()
    if tf == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif tf in ("7d", "7_days", "7days"):
        return now - timedelta(days=7)
    elif tf in ("30d", "30_days", "30days"):
        return now - timedelta(days=30)
    elif tf in ("90d", "90_days", "90days"):
        return now - timedelta(days=90)
    return None


def safe_div(num: float, den: float, multiply_100: bool = False) -> Optional[float]:
    """Safely divides two numbers, returning None when denominator <= 0."""
    if not den or den <= 0:
        return None
    val = (float(num) / float(den)) * (100.0 if multiply_100 else 1.0)
    return round(val, 2)


class AnalyticsService:
    """Production decision analytics engine querying exclusively persisted application data."""

    async def get_executive_overview(self, session: AsyncSession, time_filter: str = "all") -> Dict[str, Any]:
        """
        Returns high-level CEO/operator telemetry.
        Actual revenue is derived exclusively from completed payments / won contracts.
        """
        cutoff = get_cutoff_date(time_filter)

        # 1. Actual Revenue Collected [ACTUAL]
        # Payments completed/paid
        pay_stmt = select(func.sum(Payment.amount)).where(
            Payment.status.in_(["PAID", "COMPLETED"])
        )
        if cutoff:
            pay_stmt = pay_stmt.where(or_(Payment.paid_at >= cutoff, Payment.created_at >= cutoff))
        paid_res = (await session.execute(pay_stmt)).scalar() or 0.0

        # Fallback/additive to customer contract amounts for closed won businesses
        cust_stmt = select(func.sum(Customer.contract_amount)).join(Business).where(
            Business.pipeline_stage == PipelineStage.WON.value
        )
        if cutoff:
            cust_stmt = cust_stmt.where(Customer.created_at >= cutoff)
        cust_res = (await session.execute(cust_stmt)).scalar() or 0.0

        actual_revenue_collected = float(max(paid_res, cust_res))

        # 2. Active Prospect Slot [ACTUAL]
        lock_stmt = select(ActiveOutreachLock).where(ActiveOutreachLock.slot_id == 1)
        lock_res = (await session.execute(lock_stmt)).scalar_one_or_none()
        active_prospect = None
        if lock_res and lock_res.business_id and lock_res.status in ("ACTIVE", "WAITING_FOR_REPLY", "NEGOTIATING"):
            biz = (await session.execute(select(Business).where(Business.id == lock_res.business_id))).scalar_one_or_none()
            if biz:
                active_prospect = {
                    "business_id": biz.id,
                    "name": biz.name,
                    "domain": biz.domain,
                    "country": biz.country,
                    "niche": biz.niche,
                    "pipeline_stage": biz.pipeline_stage,
                    "slot_status": lock_res.status,
                    "locked_at": lock_res.locked_at.isoformat() if lock_res.locked_at else None,
                    "badge": "ACTUAL"
                }

        # 3. Verified Prospects [ACTUAL]
        ver_stmt = select(func.count(Business.id)).where(Business.verification_status == "VERIFIED")
        if cutoff:
            ver_stmt = ver_stmt.where(Business.created_at >= cutoff)
        verified_count = (await session.execute(ver_stmt)).scalar() or 0

        # 4. Audited Prospects [ACTUAL]
        aud_stmt = select(func.count(distinct(AuditRun.business_id)))
        if cutoff:
            aud_stmt = aud_stmt.where(AuditRun.audited_at >= cutoff)
        audited_count = (await session.execute(aud_stmt)).scalar() or 0

        # 5. Qualified Prospects [ACTUAL]
        qual_stages = [
            PipelineStage.QUALIFIED.value,
            PipelineStage.OUTREACH_READY.value,
            PipelineStage.APPROVAL.value,
            PipelineStage.CONTACTED.value,
            PipelineStage.REPLIED.value,
            PipelineStage.QUALIFIED_REPLY.value,
            PipelineStage.CALL.value,
            PipelineStage.MEETING.value,
            PipelineStage.PROPOSAL.value,
            PipelineStage.WON.value
        ]
        qual_stmt = select(func.count(Business.id)).where(Business.pipeline_stage.in_(qual_stages))
        if cutoff:
            qual_stmt = qual_stmt.where(Business.created_at >= cutoff)
        qualified_count = (await session.execute(qual_stmt)).scalar() or 0

        # 6. Contactable Prospects [ACTUAL]
        cont_stmt = select(func.count(Business.id)).where(
            or_(
                and_(Business.public_email.isnot(None), Business.public_email != ""),
                and_(Business.phone.isnot(None), Business.phone != "")
            )
        )
        if cutoff:
            cont_stmt = cont_stmt.where(Business.created_at >= cutoff)
        contactable_count = (await session.execute(cont_stmt)).scalar() or 0

        # 7. Won Deals [ACTUAL]
        won_stmt = select(func.count(Deal.id)).where(Deal.status.in_(["WON", "PAID", "COMPLETED"]))
        if cutoff:
            won_stmt = won_stmt.where(Deal.created_at >= cutoff)
        won_deals = (await session.execute(won_stmt)).scalar() or 0

        if won_deals == 0:
            won_biz_stmt = select(func.count(Business.id)).where(Business.pipeline_stage == PipelineStage.WON.value)
            if cutoff:
                won_biz_stmt = won_biz_stmt.where(Business.created_at >= cutoff)
            won_deals = (await session.execute(won_biz_stmt)).scalar() or 0

        # 8. Pipeline Value [PIPELINE - NOT REVENUE]
        open_deal_stmt = select(func.sum(Deal.total_value)).where(
            Deal.status.notin_(["WON", "LOST", "REFUNDED", "CANCELLED"])
        )
        if cutoff:
            open_deal_stmt = open_deal_stmt.where(Deal.created_at >= cutoff)
        open_deals_val = (await session.execute(open_deal_stmt)).scalar() or 0.0

        open_offer_stmt = select(func.sum(Offer.recommended_price)).join(Business).where(
            Business.pipeline_stage.in_(qual_stages)
        )
        if cutoff:
            open_offer_stmt = open_offer_stmt.where(Offer.created_at >= cutoff)
        open_offers_val = (await session.execute(open_offer_stmt)).scalar() or 0.0

        pipeline_value = float(max(open_deals_val, open_offers_val))

        # 9. Average Deal Size [ACTUAL]
        avg_deal_size = safe_div(actual_revenue_collected, won_deals)

        return {
            "time_filter": time_filter,
            "actual_revenue_collected": {
                "value": actual_revenue_collected,
                "badge": "ACTUAL",
                "label": "Actual Revenue Collected (USD)"
            },
            "active_prospect": active_prospect,
            "verified_prospects": {
                "value": verified_count,
                "badge": "ACTUAL"
            },
            "audited_prospects": {
                "value": audited_count,
                "badge": "ACTUAL"
            },
            "qualified_prospects": {
                "value": qualified_count,
                "badge": "ACTUAL"
            },
            "contactable_prospects": {
                "value": contactable_count,
                "badge": "ACTUAL"
            },
            "won_deals": {
                "value": won_deals,
                "badge": "ACTUAL"
            },
            "pipeline_value": {
                "value": pipeline_value,
                "badge": "PIPELINE - NOT REVENUE",
                "notice": "Pipeline value reflects active in-flight deal potential and is never added to actual revenue."
            },
            "average_deal_size": {
                "value": avg_deal_size,
                "display": f"${avg_deal_size:,.2f}" if avg_deal_size is not None else "Insufficient data",
                "badge": "ACTUAL"
            }
        }

    async def get_acquisition_funnel(self, session: AsyncSession, time_filter: str = "all") -> Dict[str, Any]:
        """
        Computes real drop-off and conversion % across funnel stages:
        DISCOVERED -> VERIFIED -> RESEARCHED -> AUDITED -> QUALIFIED -> CONTACTABLE -> WON
        """
        cutoff = get_cutoff_date(time_filter)

        d_stmt = select(func.count(Business.id))
        if cutoff:
            d_stmt = d_stmt.where(Business.created_at >= cutoff)
        discovered_count = (await session.execute(d_stmt)).scalar() or 0

        v_stmt = select(func.count(Business.id)).where(Business.verification_status == "VERIFIED")
        if cutoff:
            v_stmt = v_stmt.where(Business.created_at >= cutoff)
        verified_count = (await session.execute(v_stmt)).scalar() or 0

        r_stmt = select(func.count(Business.id)).where(
            or_(
                Business.research_status == "COMPLETED",
                Business.effective_evidence_score > 0
            )
        )
        if cutoff:
            r_stmt = r_stmt.where(Business.created_at >= cutoff)
        researched_count = (await session.execute(r_stmt)).scalar() or 0

        aud_stages = [
            PipelineStage.AUDITED.value, PipelineStage.QUALIFIED.value,
            PipelineStage.OUTREACH_READY.value, PipelineStage.APPROVAL.value,
            PipelineStage.CONTACTED.value, PipelineStage.REPLIED.value,
            PipelineStage.QUALIFIED_REPLY.value, PipelineStage.CALL.value,
            PipelineStage.MEETING.value, PipelineStage.PROPOSAL.value,
            PipelineStage.WON.value
        ]
        a_stmt = select(func.count(distinct(Business.id))).outerjoin(AuditRun).where(
            or_(AuditRun.id.isnot(None), Business.pipeline_stage.in_(aud_stages))
        )
        if cutoff:
            a_stmt = a_stmt.where(Business.created_at >= cutoff)
        audited_count = (await session.execute(a_stmt)).scalar() or 0

        qual_stages = aud_stages[1:]
        q_stmt = select(func.count(Business.id)).where(Business.pipeline_stage.in_(qual_stages))
        if cutoff:
            q_stmt = q_stmt.where(Business.created_at >= cutoff)
        qualified_count = (await session.execute(q_stmt)).scalar() or 0

        c_stmt = select(func.count(Business.id)).where(
            Business.pipeline_stage.in_(qual_stages),
            or_(
                and_(Business.public_email.isnot(None), Business.public_email != ""),
                and_(Business.phone.isnot(None), Business.phone != "")
            )
        )
        if cutoff:
            c_stmt = c_stmt.where(Business.created_at >= cutoff)
        contactable_count = (await session.execute(c_stmt)).scalar() or 0

        w_stmt = select(func.count(Business.id)).where(Business.pipeline_stage == PipelineStage.WON.value)
        if cutoff:
            w_stmt = w_stmt.where(Business.created_at >= cutoff)
        won_count = (await session.execute(w_stmt)).scalar() or 0

        raw_stages = [
            ("DISCOVERED", discovered_count),
            ("VERIFIED", verified_count),
            ("RESEARCHED", researched_count),
            ("AUDITED", audited_count),
            ("QUALIFIED", qualified_count),
            ("CONTACTABLE", contactable_count),
            ("WON", won_count)
        ]

        funnel_steps = []
        top_count = discovered_count

        for idx, (stage_name, count) in enumerate(raw_stages):
            prev_count = raw_stages[idx - 1][1] if idx > 0 else count
            conv_prev = safe_div(count, prev_count, multiply_100=True) if idx > 0 else 100.0
            conv_top = safe_div(count, top_count, multiply_100=True)

            dropoff_count = max(0, prev_count - count) if idx > 0 else 0
            dropoff_pct = safe_div(dropoff_count, prev_count, multiply_100=True) if idx > 0 else 0.0

            funnel_steps.append({
                "stage": stage_name,
                "count": count,
                "conversion_from_previous": conv_prev,
                "conversion_from_top": conv_top,
                "dropoff_count": dropoff_count,
                "dropoff_rate": dropoff_pct,
                "badge": "ACTUAL"
            })

        return {
            "time_filter": time_filter,
            "total_top_funnel": top_count,
            "steps": funnel_steps
        }

    async def get_market_radar(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Aggregates market opportunity and verified density by country and niche.
        Explicitly demarcates evidence-backed vs model-derived scores.
        """
        # 1. By Country
        country_stmt = select(
            Business.country,
            func.count(Business.id).label("total_businesses"),
            func.sum(case((Business.verification_status == "VERIFIED", 1), else_=0)).label("verified_count"),
            func.sum(case((Business.pipeline_stage == PipelineStage.WON.value, 1), else_=0)).label("won_count"),
            func.avg(Business.prospect_score).label("avg_prospect_score")
        ).group_by(Business.country).order_by(desc("total_businesses"))

        country_rows = (await session.execute(country_stmt)).all()
        by_country = []
        for r in country_rows:
            c_name = r[0] or "Unknown"
            by_country.append({
                "country": c_name,
                "total_businesses": int(r[1] or 0),
                "verified_prospects": int(r[2] or 0),
                "won_deals": int(r[3] or 0),
                "avg_prospect_score": round(float(r[4] or 0.0), 3) if r[4] is not None else None,
                "evidence_status": "EVIDENCE_BACKED" if (r[2] or 0) > 0 else "DISCOVERED_ONLY"
            })

        # 2. By Niche
        niche_stmt = select(
            Business.niche,
            func.count(Business.id).label("total_businesses"),
            func.sum(case((Business.verification_status == "VERIFIED", 1), else_=0)).label("verified_count"),
            func.sum(case((Business.pipeline_stage == PipelineStage.WON.value, 1), else_=0)).label("won_count"),
            func.avg(Business.effective_evidence_score).label("avg_evidence_score")
        ).group_by(Business.niche).order_by(desc("total_businesses"))

        niche_rows = (await session.execute(niche_stmt)).all()
        by_niche = []
        for r in niche_rows:
            n_name = r[0] or "Unknown"
            by_niche.append({
                "niche": n_name,
                "total_businesses": int(r[1] or 0),
                "verified_prospects": int(r[2] or 0),
                "won_deals": int(r[3] or 0),
                "avg_evidence_score": round(float(r[4] or 0.0), 3) if r[4] is not None else None,
                "evidence_status": "EVIDENCE_BACKED" if (r[2] or 0) > 0 else "DISCOVERED_ONLY"
            })

        return {
            "by_country": by_country,
            "by_niche": by_niche,
            "legend": {
                "evidence_backed_metrics": ["total_businesses", "verified_prospects", "won_deals"],
                "model_derived_metrics": ["avg_prospect_score", "avg_evidence_score"],
                "model_output_badge": "MODEL OUTPUT / INTERNAL ONLY"
            }
        }

    async def get_prospect_quality_distribution(self, session: AsyncSession, time_filter: str = "all") -> Dict[str, Any]:
        """
        Computes distribution histograms for Prospect Score, Evidence Score, and Website Health Score.
        """
        cutoff = get_cutoff_date(time_filter)

        b_stmt = select(Business.prospect_score, Business.effective_evidence_score)
        if cutoff:
            b_stmt = b_stmt.where(Business.created_at >= cutoff)
        b_rows = (await session.execute(b_stmt)).all()

        ps_buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        es_buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}

        ps_vals = []
        es_vals = []
        for r in b_rows:
            ps = float(r[0] or 0.0)
            es = float(r[1] or 0.0)
            ps_vals.append(ps)
            es_vals.append(es)

            if ps <= 0.2: ps_buckets["0.0-0.2"] += 1
            elif ps <= 0.4: ps_buckets["0.2-0.4"] += 1
            elif ps <= 0.6: ps_buckets["0.4-0.6"] += 1
            elif ps <= 0.8: ps_buckets["0.6-0.8"] += 1
            else: ps_buckets["0.8-1.0"] += 1

            if es <= 0.2: es_buckets["0.0-0.2"] += 1
            elif es <= 0.4: es_buckets["0.2-0.4"] += 1
            elif es <= 0.6: es_buckets["0.4-0.6"] += 1
            elif es <= 0.8: es_buckets["0.6-0.8"] += 1
            else: es_buckets["0.8-1.0"] += 1

        aud_stmt = select(AuditRun.overall_health_score)
        if cutoff:
            aud_stmt = aud_stmt.where(AuditRun.audited_at >= cutoff)
        aud_rows = (await session.execute(aud_stmt)).all()

        health_buckets = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
        health_vals = []
        for r in aud_rows:
            h = float(r[0] or 0.0)
            health_vals.append(h)
            if h <= 20.0: health_buckets["0-20"] += 1
            elif h <= 40.0: health_buckets["20-40"] += 1
            elif h <= 60.0: health_buckets["40-60"] += 1
            elif h <= 80.0: health_buckets["60-80"] += 1
            else: health_buckets["80-100"] += 1

        return {
            "time_filter": time_filter,
            "prospect_scores": {
                "distribution": ps_buckets,
                "count": len(ps_vals),
                "avg": round(sum(ps_vals) / len(ps_vals), 3) if ps_vals else None,
                "min": min(ps_vals) if ps_vals else None,
                "max": max(ps_vals) if ps_vals else None,
                "badge": "MODEL OUTPUT / HEURISTIC"
            },
            "evidence_scores": {
                "distribution": es_buckets,
                "count": len(es_vals),
                "avg": round(sum(es_vals) / len(es_vals), 3) if es_vals else None,
                "min": min(es_vals) if es_vals else None,
                "max": max(es_vals) if es_vals else None,
                "badge": "ACTUAL"
            },
            "website_health_scores": {
                "distribution": health_buckets,
                "count": len(health_vals),
                "avg": round(sum(health_vals) / len(health_vals), 1) if health_vals else None,
                "min": min(health_vals) if health_vals else None,
                "max": max(health_vals) if health_vals else None,
                "badge": "ACTUAL MEASUREMENT"
            }
        }

    async def get_service_demand_distribution(self, session: AsyncSession, time_filter: str = "all") -> Dict[str, Any]:
        """
        Returns real service match distribution across the 10 catalog services.
        Aggregates matched prospect count, average fit score, and pipeline value.
        """
        cutoff = get_cutoff_date(time_filter)

        intel_stmt = select(
            ClientIntelligenceRecord.top_service_id,
            ClientIntelligenceRecord.top_service_name,
            func.count(ClientIntelligenceRecord.id).label("match_count"),
            func.avg(ClientIntelligenceRecord.fit_score).label("avg_fit"),
            func.avg(ClientIntelligenceRecord.p_win).label("avg_p_win"),
            func.sum(ClientIntelligenceRecord.recommended_price_usd).label("pipeline_val"),
            func.avg(ClientIntelligenceRecord.recommended_price_usd).label("avg_price")
        ).group_by(
            ClientIntelligenceRecord.top_service_id,
            ClientIntelligenceRecord.top_service_name
        )
        if cutoff:
            intel_stmt = intel_stmt.where(ClientIntelligenceRecord.created_at >= cutoff)

        rows = (await session.execute(intel_stmt)).all()
        data_by_id = {}
        for r in rows:
            sid = r[0]
            data_by_id[sid] = {
                "service_id": sid,
                "service_name": r[1],
                "match_count": int(r[2] or 0),
                "avg_fit_score": round(float(r[3]), 3) if r[3] is not None else None,
                "avg_p_win": round(float(r[4]), 3) if r[4] is not None else None,
                "pipeline_value": float(r[5] or 0.0),
                "avg_recommended_price": round(float(r[6]), 2) if r[6] is not None else None,
            }

        full_catalog_demand = []
        for cat in CATALOG_SERVICES:
            cid = cat["id"]
            if cid in data_by_id:
                full_catalog_demand.append({
                    **data_by_id[cid],
                    "badge_fit": "MODEL OUTPUT",
                    "badge_p_win": "MODEL OUTPUT",
                    "badge_pipeline": "PIPELINE - NOT REVENUE"
                })
            else:
                full_catalog_demand.append({
                    "service_id": cid,
                    "service_name": cat["name"],
                    "match_count": 0,
                    "avg_fit_score": None,
                    "avg_p_win": None,
                    "pipeline_value": 0.0,
                    "avg_recommended_price": None,
                    "badge_fit": "MODEL OUTPUT",
                    "badge_p_win": "MODEL OUTPUT",
                    "badge_pipeline": "PIPELINE - NOT REVENUE"
                })

        return {
            "time_filter": time_filter,
            "services": full_catalog_demand,
            "total_matches": sum(s["match_count"] for s in full_catalog_demand)
        }

    async def get_sales_analytics(self, session: AsyncSession, time_filter: str = "all") -> Dict[str, Any]:
        """
        Computes response rates, meeting rates, win rates, and average deal size.
        Guarantees safe division by zero, returning None/'Insufficient data' when appropriate.
        """
        cutoff = get_cutoff_date(time_filter)

        m_stmt = select(func.count(OutreachMessage.id)).where(OutreachMessage.status == "SENT")
        if cutoff:
            m_stmt = m_stmt.where(OutreachMessage.sent_at >= cutoff)
        contacted_count = (await session.execute(m_stmt)).scalar() or 0

        rep_stmt = select(func.count(Reply.id))
        if cutoff:
            rep_stmt = rep_stmt.where(Reply.received_at >= cutoff)
        replied_count = (await session.execute(rep_stmt)).scalar() or 0

        meet_stmt = select(func.count(Meeting.id))
        if cutoff:
            meet_stmt = meet_stmt.where(Meeting.scheduled_time >= cutoff)
        meetings_count = (await session.execute(meet_stmt)).scalar() or 0

        prop_stmt = select(func.count(Proposal.id))
        if cutoff:
            prop_stmt = prop_stmt.where(Proposal.created_at >= cutoff)
        proposals_count = (await session.execute(prop_stmt)).scalar() or 0

        won_stmt = select(func.count(Deal.id)).where(Deal.status.in_(["WON", "PAID", "COMPLETED"]))
        if cutoff:
            won_stmt = won_stmt.where(Deal.created_at >= cutoff)
        won_count = (await session.execute(won_stmt)).scalar() or 0

        rev_stmt = select(func.sum(Payment.amount)).where(Payment.status.in_(["PAID", "COMPLETED"]))
        if cutoff:
            rev_stmt = rev_stmt.where(or_(Payment.paid_at >= cutoff, Payment.created_at >= cutoff))
        actual_revenue = float((await session.execute(rev_stmt)).scalar() or 0.0)

        reply_rate = safe_div(replied_count, contacted_count, multiply_100=True)
        meeting_rate = safe_div(meetings_count, replied_count, multiply_100=True)
        proposal_win_rate = safe_div(won_count, proposals_count, multiply_100=True)
        overall_win_rate = safe_div(won_count, contacted_count, multiply_100=True)
        avg_deal_value = safe_div(actual_revenue, won_count)

        insufficient_data_flags = []
        if contacted_count == 0:
            insufficient_data_flags.append("No outreach sent (contacted_count == 0)")
        if replied_count == 0:
            insufficient_data_flags.append("No replies received (replied_count == 0)")
        if proposals_count == 0:
            insufficient_data_flags.append("No proposals issued (proposals_count == 0)")
        if won_count == 0:
            insufficient_data_flags.append("No deals closed won (won_count == 0)")

        return {
            "time_filter": time_filter,
            "counts": {
                "contacted": contacted_count,
                "replied": replied_count,
                "meetings": meetings_count,
                "proposals": proposals_count,
                "won": won_count
            },
            "metrics": {
                "reply_rate_pct": {
                    "value": reply_rate,
                    "display": f"{reply_rate}%" if reply_rate is not None else "Insufficient data",
                    "badge": "ACTUAL"
                },
                "meeting_rate_pct": {
                    "value": meeting_rate,
                    "display": f"{meeting_rate}%" if meeting_rate is not None else "Insufficient data",
                    "badge": "ACTUAL"
                },
                "proposal_win_rate_pct": {
                    "value": proposal_win_rate,
                    "display": f"{proposal_win_rate}%" if proposal_win_rate is not None else "Insufficient data",
                    "badge": "ACTUAL"
                },
                "overall_win_rate_pct": {
                    "value": overall_win_rate,
                    "display": f"{overall_win_rate}%" if overall_win_rate is not None else "Insufficient data",
                    "badge": "ACTUAL"
                },
                "average_deal_value_usd": {
                    "value": avg_deal_value,
                    "display": f"${avg_deal_value:,.2f}" if avg_deal_value is not None else "Insufficient data",
                    "badge": "ACTUAL"
                }
            },
            "insufficient_data_reasons": insufficient_data_flags
        }

    async def get_revenue_analytics(self, session: AsyncSession, time_filter: str = "all") -> Dict[str, Any]:
        """
        Detailed revenue analytics strictly separating cash revenue from pipeline opportunity.
        """
        cutoff = get_cutoff_date(time_filter)

        pay_stmt = select(func.sum(Payment.amount)).where(Payment.status.in_(["PAID", "COMPLETED"]))
        if cutoff:
            pay_stmt = pay_stmt.where(or_(Payment.paid_at >= cutoff, Payment.created_at >= cutoff))
        actual_rev = float((await session.execute(pay_stmt)).scalar() or 0.0)

        period_stmt = select(
            func.strftime("%Y-%m", Payment.paid_at).label("period"),
            func.sum(Payment.amount).label("rev")
        ).where(
            Payment.status.in_(["PAID", "COMPLETED"]),
            Payment.paid_at.isnot(None)
        ).group_by("period").order_by("period")
        if cutoff:
            period_stmt = period_stmt.where(Payment.paid_at >= cutoff)

        period_rows = (await session.execute(period_stmt)).all()
        by_period = [{"period": r[0], "amount": float(r[1] or 0.0), "badge": "ACTUAL"} for r in period_rows]

        country_rev_stmt = select(
            Business.country,
            func.sum(Payment.amount).label("amount")
        ).join(Business, Payment.business_id == Business.id).where(
            Payment.status.in_(["PAID", "COMPLETED"])
        ).group_by(Business.country).order_by(desc("amount"))
        if cutoff:
            country_rev_stmt = country_rev_stmt.where(Payment.paid_at >= cutoff)

        country_rows = (await session.execute(country_rev_stmt)).all()
        by_country = [{"country": r[0] or "Unknown", "amount": float(r[1] or 0.0), "badge": "ACTUAL"} for r in country_rows]

        deal_rev_stmt = select(
            Deal.service_type,
            func.sum(Payment.amount).label("amount")
        ).join(Deal, Payment.deal_id == Deal.id).where(
            Payment.status.in_(["PAID", "COMPLETED"])
        ).group_by(Deal.service_type).order_by(desc("amount"))
        if cutoff:
            deal_rev_stmt = deal_rev_stmt.where(Payment.paid_at >= cutoff)

        serv_rows = (await session.execute(deal_rev_stmt)).all()
        by_service = [{"service": r[0] or "Custom Engagement", "amount": float(r[1] or 0.0), "badge": "ACTUAL"} for r in serv_rows]

        open_deals_stmt = select(func.sum(Deal.total_value)).where(
            Deal.status.notin_(["WON", "LOST", "REFUNDED", "CANCELLED"])
        )
        if cutoff:
            open_deals_stmt = open_deals_stmt.where(Deal.created_at >= cutoff)
        pipeline_val = float((await session.execute(open_deals_stmt)).scalar() or 0.0)

        return {
            "time_filter": time_filter,
            "actual_revenue_total": {
                "amount": actual_rev,
                "badge": "ACTUAL CASH COLLECTED",
                "label": "Total Cash Collected"
            },
            "revenue_by_period": by_period,
            "revenue_by_country": by_country,
            "revenue_by_service": by_service,
            "pipeline_value": {
                "amount": pipeline_val,
                "badge": "PIPELINE - NOT REVENUE",
                "label": "Open Pipeline Potential"
            },
            "separation_notice": "Pipeline value represents active unclosed opportunities and must never be conflated with actual collected revenue."
        }

    async def get_estimated_value(self, session: AsyncSession, time_filter: str = "all") -> Dict[str, Any]:
        """
        Aggregates estimated recoverable customer value from client intelligence records.
        Mandates explicit disclaimer disclosure and sets is_revenue=False.
        """
        cutoff = get_cutoff_date(time_filter)

        intel_stmt = select(ClientIntelligenceRecord.roi_estimate)
        if cutoff:
            intel_stmt = intel_stmt.where(ClientIntelligenceRecord.created_at >= cutoff)
        rows = (await session.execute(intel_stmt)).all()

        total_annual = 0.0
        total_monthly = 0.0
        count = 0

        for r in rows:
            roi = r[0] or {}
            annual = float(roi.get("estimated_annual_recoverable_usd") or roi.get("annual_revenue_uplift_usd") or 0.0)
            monthly = float(roi.get("estimated_monthly_recoverable_usd") or (annual / 12.0) if annual > 0 else 0.0)
            if annual > 0 or monthly > 0:
                total_annual += annual
                total_monthly += monthly
                count += 1

        avg_monthly = safe_div(total_monthly, count)

        return {
            "time_filter": time_filter,
            "total_estimated_annual_recoverable_value": total_annual,
            "total_estimated_monthly_recoverable_value": total_monthly,
            "avg_monthly_recoverable_per_prospect": avg_monthly,
            "prospects_with_estimate_count": count,
            "badge": "ESTIMATED",
            "is_revenue": False,
            "mandatory_disclosure": "Model estimate based on stated assumptions; not guaranteed revenue."
        }

    async def get_model_outputs_summary(self, session: AsyncSession, time_filter: str = "all") -> Dict[str, Any]:
        """
        Summarizes internal model outputs (Fit Score, P(Win), Selection Score).
        Strictly tagged as INTERNAL ONLY and never safe for client claims.
        """
        cutoff = get_cutoff_date(time_filter)

        intel_stmt = select(
            ClientIntelligenceRecord.fit_score,
            ClientIntelligenceRecord.p_win,
            ClientIntelligenceRecord.selection_score
        )
        if cutoff:
            intel_stmt = intel_stmt.where(ClientIntelligenceRecord.created_at >= cutoff)
        rows = (await session.execute(intel_stmt)).all()

        fit_scores = [float(r[0]) for r in rows if r[0] is not None]
        p_wins = [float(r[1]) for r in rows if r[1] is not None]
        sel_scores = [float(r[2]) for r in rows if r[2] is not None]

        def summarize(lst):
            if not lst:
                return {"count": 0, "avg": None, "min": None, "max": None}
            return {
                "count": len(lst),
                "avg": round(sum(lst) / len(lst), 3),
                "min": round(min(lst), 3),
                "max": round(max(lst), 3)
            }

        return {
            "time_filter": time_filter,
            "fit_score": {
                **summarize(fit_scores),
                "badge": "MODEL OUTPUT / INTERNAL ONLY",
                "description": "Algorithmic match score between prospect audit signals and agency service capabilities."
            },
            "p_win": {
                **summarize(p_wins),
                "badge": "MODEL OUTPUT / INTERNAL ONLY",
                "description": "Heuristic probability of deal closure based on business digital weakness and category fit."
            },
            "selection_score": {
                **summarize(sel_scores),
                "badge": "MODEL OUTPUT / INTERNAL ONLY",
                "description": "Composite priority index for active outreach lock acquisition."
            },
            "client_facing_safety": False,
            "disclaimer": "All predictive scores are model-generated heuristics for internal prioritization only and must never be presented as factual claims to clients."
        }

    async def get_data_quality_metrics(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Reports empirical data quality, evidence freshness, missing contacts, and gate blocks.
        """
        total_biz = (await session.execute(select(func.count(Business.id)))).scalar() or 0
        ver_biz = (await session.execute(
            select(func.count(Business.id)).where(Business.verification_status == "VERIFIED")
        )).scalar() or 0

        coverage_pct = safe_div(ver_biz, total_biz, multiply_100=True)

        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        stale_stmt = select(func.count(ProspectEvidence.id)).where(ProspectEvidence.retrieved_at < thirty_days_ago)
        stale_count = (await session.execute(stale_stmt)).scalar() or 0

        missing_stmt = select(func.count(Business.id)).where(
            or_(Business.public_email.is_(None), Business.public_email == ""),
            or_(Business.phone.is_(None), Business.phone == "")
        )
        missing_contact_count = (await session.execute(missing_stmt)).scalar() or 0

        blocked_stmt = select(func.count(Business.id)).where(
            or_(
                Business.verification_status.in_(["REJECTED", "GATE_REJECTED"]),
                Business.pipeline_stage == "REJECTED"
            )
        )
        gate_blocked_count = (await session.execute(blocked_stmt)).scalar() or 0

        acq_fail = (await session.execute(
            select(func.count(AcquisitionRun.id)).where(AcquisitionRun.status == "FAILED")
        )).scalar() or 0
        disc_fail = (await session.execute(
            select(func.count(DiscoveryRun.id)).where(DiscoveryRun.status == "FAILED")
        )).scalar() or 0
        provider_failure_count = acq_fail + disc_fail

        if total_biz == 0:
            health_status = "INSUFFICIENT_DATA"
        elif coverage_pct is not None and coverage_pct >= 60.0 and provider_failure_count == 0:
            health_status = "HEALTHY"
        else:
            health_status = "WARNING"

        return {
            "total_businesses": total_biz,
            "verified_businesses": ver_biz,
            "evidence_coverage_pct": {
                "value": coverage_pct,
                "display": f"{coverage_pct}%" if coverage_pct is not None else "Insufficient data",
                "badge": "ACTUAL"
            },
            "stale_evidence_count": {
                "value": stale_count,
                "threshold_days": 30,
                "badge": "ACTUAL"
            },
            "missing_contact_count": {
                "value": missing_contact_count,
                "badge": "ACTUAL"
            },
            "gate_blocked_count": {
                "value": gate_blocked_count,
                "badge": "ACTUAL"
            },
            "provider_failure_count": {
                "value": provider_failure_count,
                "badge": "ACTUAL"
            },
            "overall_quality_status": health_status
        }


analytics_service = AnalyticsService()
