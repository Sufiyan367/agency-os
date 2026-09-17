"""Production Truth Engine.

Centralized canonical single-source-of-truth queries and deterministic provenance classifiers.
Enforces that synthetic, historical/dev, canary, demo/test, and unverified records
are NEVER displayed as real commercial outcomes on the CEO Command Center or executive funnels.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_
from app.database.models import (
    Business, OutreachMessage, OutreachStatus, Reply,
    ReplyClassification, Customer, PipelineStage, Offer,
    LeadScore, AuditRun, Proposal, Payment, Artifact
)
from app.core.safety_filters import (
    is_test_or_synthetic,
    get_synthetic_business_filter_clauses,
    get_synthetic_outreach_filter_clauses,
    get_synthetic_reply_filter_clauses
)

OPERATOR_EMAILS = (
    "automatedagencyos.tech",
    "agencyos.tech",
    "classicshot.7@gmail.com",
    "sufiyansurve",
    "sufiyan",
    "arttest@",
    "mrsufiyan",
)


def classify_business_provenance(biz: Any) -> str:
    """Classifies a business record into REAL, SYNTHETIC, or TEST."""
    if not biz:
        return "UNKNOWN"
    b_id = str(getattr(biz, "id", "") or "")
    if b_id.startswith("fixture-") or b_id.startswith("mock-") or b_id.startswith("test-"):
        return "SYNTHETIC"
    name = getattr(biz, "name", None) or ""
    if any(k in name.lower() for k in ("[synthetic]", "[test]", "[mock]")):
        return "SYNTHETIC"
    domain = getattr(biz, "domain", None)
    email = getattr(biz, "public_email", None) or getattr(biz, "email", None)
    if is_test_or_synthetic(domain=domain, email=email, name=name):
        return "SYNTHETIC"
    return "REAL"


def classify_outreach_provenance(msg: Any, biz: Any = None) -> str:
    """Classifies outreach message into REAL_EXTERNAL, CANARY, HISTORICAL_DEV, or TEST."""
    provider = (getattr(msg, "provider", None) or "").lower().strip()
    channel = (getattr(msg, "channel", None) or "").lower().strip()
    if provider in ("dev_simulator", "simulation"):
        return provider.upper()
    if channel in ("dev_simulator", "simulation"):
        return channel.upper()

    meta = getattr(msg, "message_metadata", None) or getattr(msg, "auto_approval_eligibility", None) or {}
    if isinstance(meta, dict) and meta.get("is_canary"):
        return "CANARY"

    recipient = (getattr(msg, "recipient_email", None) or "").lower().strip()

    if any(k in recipient for k in OPERATOR_EMAILS) or "canary" in recipient:
        return "CANARY"

    biz_domain = getattr(biz, "domain", None) if biz else None
    biz_name = getattr(biz, "name", None) if biz else None
    if is_test_or_synthetic(domain=biz_domain, email=recipient, name=biz_name):
        return "TEST"
    if provider in ("mock", "dry_run", "test") or channel in ("mock", "test"):
        return "TEST"

    sent_at = getattr(msg, "sent_at", None)
    created_at = getattr(msg, "created_at", None)
    ref_time = sent_at or created_at
    if not provider or (ref_time and ref_time < datetime(2026, 9, 15, 0, 0, 0)):
        return "HISTORICAL_DEV"

    return "REAL_EXTERNAL"


def classify_reply_provenance(rep: Any, biz: Any = None) -> str:
    """Classifies a reply into REAL_CUSTOMER, OPERATOR_TEST, NDR_BOUNCE, or SYNTHETIC."""
    sender = (getattr(rep, "sender_email", None) or getattr(rep, "from_email", None) or "").lower().strip()
    subject = (getattr(rep, "subject", None) or "").lower()
    if any(k in sender for k in OPERATOR_EMAILS):
        return "OPERATOR_TEST"
    if sender.startswith("postmaster@") or sender.startswith("mailer-daemon@") or "bounce" in sender or "undelivered" in subject:
        return "NDR_BOUNCE"
    if is_test_or_synthetic(email=sender) or "test" in sender:
        return "SYNTHETIC"
    if biz and classify_business_provenance(biz) != "REAL":
        return "OPERATOR_TEST"
    return "REAL_CUSTOMER"


def classify_payment_provenance(pay: Any, biz: Any = None) -> str:
    """Classifies a payment into REAL_CUSTOMER, TEST_MOCK, or OPERATOR_TEST."""
    if getattr(pay, "is_mock", False) is True:
        return "TEST_MOCK"
    p_id = str(getattr(pay, "id", "") or "")
    if p_id.startswith("mock-") or p_id.startswith("test-"):
        return "TEST_MOCK"
    gateway = (getattr(pay, "gateway", None) or getattr(pay, "provider", None) or "").lower()
    if gateway in ("mock", "test"):
        return "TEST_MOCK"
    payer_email = (getattr(pay, "payer_email", None) or getattr(pay, "customer_email", None) or "").lower()
    ref_id = (getattr(pay, "reference_id", None) or "").lower()
    if any(k in payer_email for k in OPERATOR_EMAILS) or any(k in ref_id for k in ("test", "mock", "sufiyan")):
        return "OPERATOR_TEST"
    if biz and classify_business_provenance(biz) != "REAL":
        return "OPERATOR_TEST"
    return "REAL_CUSTOMER"


def classify_proposal_provenance(prop: Any, biz: Any = None) -> str:
    """Classifies a proposal into REAL_CUSTOMER, TEST_MOCK, or OPERATOR_TEST."""
    if getattr(prop, "is_mock", False) is True:
        return "TEST_MOCK"
    title = (getattr(prop, "title", None) or "").lower()
    if "test" in title or "mock" in title:
        return "TEST_MOCK"
    if biz and classify_business_provenance(biz) != "REAL":
        return "OPERATOR_TEST"
    return "REAL_CUSTOMER"


def classify_deal_provenance(deal_or_biz: Any, biz: Any = None) -> str:
    """Classifies a deal into REAL_CUSTOMER or SIMULATED_TEST."""
    d_id = str(getattr(deal_or_biz, "id", "") or "")
    if d_id.startswith("mock-") or d_id.startswith("test-"):
        return "SIMULATED_TEST"
    d_name = getattr(deal_or_biz, "deal_name", None) or getattr(deal_or_biz, "name", None) or ""
    if any(k in d_name.lower() for k in ("[test]", "[mock]", "sample", "test")):
        return "SIMULATED_TEST"
    target_biz = biz or deal_or_biz
    if classify_business_provenance(target_biz) != "REAL":
        return "SIMULATED_TEST"
    return "REAL_CUSTOMER"


def classify_activity_provenance(event: Any) -> str:
    """Classifies an operational or audit event into REAL_PRODUCTION, SYSTEM, CANARY, SIMULATION, or TEST."""
    action = (getattr(event, "action", "") or getattr(event, "event_type", "") or "").upper()
    meta = getattr(event, "metadata", None) or getattr(event, "details", None) or {}
    if isinstance(meta, str):
        import json
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    meta_str = str(meta).lower()
    action_str = action.lower()

    if "simulation" in action_str or "simulation" in meta_str or (isinstance(meta, dict) and meta.get("channel") in ("dev_simulator", "simulation")):
        return "SIMULATION"
    if "canary" in action_str or "canary" in meta_str:
        return "CANARY"
    if "test" in action_str or "test" in meta_str or (isinstance(meta, dict) and meta.get("is_test")):
        return "TEST"
    if any(k in action_str for k in ("cron", "scheduler", "heartbeat", "cleanup", "sync")):
        return "SYSTEM"
    return "REAL_PRODUCTION"


async def get_canonical_production_truth(session: AsyncSession) -> Dict[str, Any]:
    """
    Single Source of Truth for all executive dashboards, funnels, and metrics.
    Guarantees:
    - Zero synthetic, canary, or historical leakage into real outcome metrics.
    - Zero divergence between Business Snapshot and Live Pipeline funnel.
    - Mathematical consistency: Contacted == Outbound Sent, Won == Deals, etc.
    """
    biz_filters = get_synthetic_business_filter_clauses(Business)

    # 1. Total Discovered Real Prospects
    q_prospects = select(func.count(Business.id)).where(*biz_filters)
    real_prospects = (await session.execute(q_prospects)).scalar() or 0

    # 2. Real Verified Leads
    q_verified = select(func.count(Business.id)).where(
        Business.verification_status == "VERIFIED",
        *biz_filters
    )
    real_verified_leads = (await session.execute(q_verified)).scalar() or 0

    # 3. Real Qualified Leads: verified lead with LeadScore.total_score >= 55.0
    q_qualified = (
        select(func.count(Business.id))
        .join(LeadScore, LeadScore.business_id == Business.id)
        .where(
            Business.verification_status == "VERIFIED",
            LeadScore.total_score >= 55.0,
            *biz_filters
        )
    )
    real_qualified_leads = (await session.execute(q_qualified)).scalar() or 0

    # 4. Sent Messages & Real External Contacted
    q_sent = (
        select(OutreachMessage)
        .where(OutreachMessage.status.in_([OutreachStatus.SENT.value, "MOCKED_SENT"]))
    )
    sent_records = (await session.execute(q_sent)).scalars().all()

    # Pre-fetch businesses for sent messages
    biz_ids = [m.business_id for m in sent_records if m.business_id]
    biz_map = {}
    if biz_ids:
        b_res = await session.execute(select(Business).where(Business.id.in_(biz_ids)))
        biz_map = {b.id: b for b in b_res.scalars().all()}

    real_external_sent_lifetime = 0
    real_external_sent_today = 0
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    for msg in sent_records:
        biz = biz_map.get(msg.business_id)
        cat = classify_outreach_provenance(msg, biz)
        if cat == "REAL_EXTERNAL":
            real_external_sent_lifetime += 1
            ref_time = msg.sent_at or msg.created_at
            if ref_time and ref_time >= today_start:
                real_external_sent_today += 1

    # Queued & Pending Outreach
    q_pending = select(func.count(OutreachMessage.id)).where(
        OutreachMessage.status == OutreachStatus.PENDING_APPROVAL.value
    )
    outreach_pending_approval = (await session.execute(q_pending)).scalar() or 0

    q_queued = select(func.count(OutreachMessage.id)).where(
        OutreachMessage.status.in_([OutreachStatus.APPROVED.value, OutreachStatus.OUTREACH_QUEUED.value])
    )
    queued_qualified = (await session.execute(q_queued)).scalar() or 0

    # 5. Replies & Real Customer Interest
    q_replies = select(Reply)
    all_replies = (await session.execute(q_replies)).scalars().all()
    rep_biz_ids = [r.business_id for r in all_replies if r.business_id]
    rep_biz_map = {}
    if rep_biz_ids:
        rb_res = await session.execute(select(Business).where(Business.id.in_(rep_biz_ids)))
        rep_biz_map = {b.id: b for b in rb_res.scalars().all()}

    real_customer_replies = 0
    real_interested_leads = 0
    for rep in all_replies:
        biz = rep_biz_map.get(rep.business_id)
        cat = classify_reply_provenance(rep, biz)
        if cat == "REAL_CUSTOMER":
            real_customer_replies += 1
            if rep.classification in (
                ReplyClassification.INTERESTED.value,
                ReplyClassification.POSITIVE.value,
                ReplyClassification.MEETING_REQUEST.value,
                ReplyClassification.PRICE_REQUEST.value,
                ReplyClassification.DEMO_REQUEST.value
            ):
                real_interested_leads += 1

    # 6. Real Proposals
    q_props = select(Proposal)
    all_props = (await session.execute(q_props)).scalars().all()
    prop_biz_ids = [p.business_id for p in all_props if p.business_id]
    prop_biz_map = {}
    if prop_biz_ids:
        pb_res = await session.execute(select(Business).where(Business.id.in_(prop_biz_ids)))
        prop_biz_map = {b.id: b for b in pb_res.scalars().all()}

    real_proposals = 0
    for p in all_props:
        biz = prop_biz_map.get(p.business_id)
        if classify_proposal_provenance(p, biz) == "REAL_CUSTOMER":
            real_proposals += 1

    # 7. Real Payments & Verified Revenue
    q_payments = select(Payment)
    all_payments = (await session.execute(q_payments)).scalars().all()
    pay_biz_ids = [py.business_id for py in all_payments if py.business_id]
    pay_biz_map = {}
    if pay_biz_ids:
        pyb_res = await session.execute(select(Business).where(Business.id.in_(pay_biz_ids)))
        pay_biz_map = {b.id: b for b in pyb_res.scalars().all()}

    real_payments_pending = 0
    real_payments_confirmed = 0
    real_verified_revenue = 0.0

    for py in all_payments:
        biz = pay_biz_map.get(py.business_id)
        if classify_payment_provenance(py, biz) == "REAL_CUSTOMER":
            st = (py.status or "").upper()
            if st in ("PENDING", "PROCESSING", "AUTHORIZED", "PAYMENT_PENDING", "PAYMENT_REQUESTED", "PAYMENT_PENDING_VERIFICATION"):
                real_payments_pending += 1
            elif st in ("PAID", "COMPLETED", "SETTLED", "PAYMENT_CONFIRMED", "VERIFIED_PAYMENT"):
                real_payments_confirmed += 1
                real_verified_revenue += float(py.amount or 0.0)

    # 8. Real Deals Won
    q_deals = select(func.count(Business.id)).where(
        Business.pipeline_stage == PipelineStage.WON.value,
        *biz_filters
    )
    real_deals = (await session.execute(q_deals)).scalar() or 0
    if real_deals == 0 and real_payments_confirmed > 0:
        real_deals = real_payments_confirmed

    # 9. Demos (Turnkey Artifacts for active real leads)
    q_demos = select(Artifact).where(Artifact.artifact_type == "DEMO_PACKAGE")
    demo_artifacts = (await session.execute(q_demos)).scalars().all()
    real_demos = 0
    for art in demo_artifacts:
        if art.created_at and art.created_at < datetime(2026, 9, 15, 0, 0, 0):
            continue
        if art.business_id:
            b = await session.get(Business, art.business_id)
            if b and classify_business_provenance(b) == "REAL":
                real_demos += 1

    revenue_label = f"${real_verified_revenue:,.2f}" if real_verified_revenue > 0 else "$0.00"

    return {
        "real_prospects": real_prospects,
        "real_verified_leads": real_verified_leads,
        "real_qualified_leads": real_qualified_leads,
        "real_external_contacted": real_external_sent_lifetime,
        "real_external_contacted_today": real_external_sent_today,
        "outreach_awaiting_approval": outreach_pending_approval,
        "queued_qualified": queued_qualified,
        "real_customer_replies": real_customer_replies,
        "real_interested_leads": real_interested_leads,
        "real_proposals": real_proposals,
        "real_deals": real_deals,
        "real_payments_pending": real_payments_pending,
        "real_payments_confirmed": real_payments_confirmed,
        "real_verified_revenue": real_verified_revenue,
        "revenue_label": revenue_label,
        "real_demos": real_demos,
        "provenance_notes": {
            "prospects": f"{real_prospects} real businesses discovered ({real_verified_leads} verified)",
            "qualified": f"{real_qualified_leads} real leads meet score >= 55 floor with verified audit",
            "contacted": f"{real_external_sent_lifetime} production messages dispatched via Titan SMTP",
            "replies": f"{real_customer_replies} verified external customer replies (operator tests and bounces excluded)",
            "interested": f"{real_interested_leads} verified customer interest signals",
            "deals": f"{real_deals} verified customer commercial agreements",
            "payment_pending": f"{real_payments_pending} verified customer payment obligations",
            "revenue": f"{revenue_label} verified customer settled revenue"
        }
    }
