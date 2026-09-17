"""Production Truth Engine.

Centralized canonical single-source-of-truth queries and deterministic provenance classifiers.
Enforces that synthetic, historical/dev, canary, demo/test, and unverified records
are NEVER displayed as real commercial outcomes on the CEO Command Center or executive funnels.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_
from app.database.models import (
    Business, OutreachMessage, OutreachStatus, Reply,
    ReplyClassification, Customer, PipelineStage, Offer,
    LeadScore, AuditRun, Proposal, Payment, Artifact,
    SuppressionList, Deal, ProjectProposal
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


PROHIBITED_COUNTRIES = {"IN", "PK", "IL", "DE", "IT", "ES", "CH"}

REAL_PRODUCTION_ACTIONS = {
    "LEAD_DISCOVERED", "PROSPECT_FOUND", "DISCOVERY_STARTED", "DISCOVERY_COMPLETED",
    "PROSPECT_SCORED", "PROSPECT_QUALIFIED", "SCORING_STARTED", "SCORING_COMPLETED",
    "COMMERCIAL_QUALIFICATION",
    "LEAD_VERIFIED", "VERIFICATION_STARTED", "VERIFICATION_COMPLETED",
    "AUDIT_STARTED", "AUDIT_COMPLETED",
    "COMPLIANCE_STARTED", "COMPLIANCE_PASSED",
    "OFFER_GENERATION_STARTED", "OFFER_GENERATED",
    "OUTREACH_DRAFT_STARTED", "OUTREACH_DRAFTED", "OUTREACH_APPROVED",
    "OUTREACH_QUEUED", "OUTREACH_DISPATCH_STARTED", "OUTREACH_DISPATCHED",
    "OUTREACH_SENT", "OUTREACH_DELIVERED",
    "INBOUND_EVENT_RECEIVED", "REPLY_RECEIVED", "CUSTOMER_REPLY_RECEIVED",
    "REPLY_CLASSIFIED", "CONVERSATION_RESPONSE_GENERATED",
    "COMMITMENT_CREATED", "COMMITMENT_COMPLETED", "OBJECTION_DETECTED",
    "LEAD_CONTEXT_RECONSTRUCTED", "MEMORY_PERSISTED",
    "DEAL_SIGNED", "DEAL_WON", "CONTRACT_SIGNED", "PROPOSAL_SENT", "PROPOSAL_ACCEPTED",
    "PAYMENT_CONFIRMED", "PRODUCTION_AUTHORIZED", "PAYMENT_RECEIVED", "REVENUE_SETTLED",
    "WEBSITE_BUILD_STARTED", "WEBSITE_BUILD_PROGRESS", "WEBSITE_BUILD_COMPLETED",
    "DEPLOYED", "DELIVERY_COMPLETE", "DEMO_STARTED", "DEMO_READY", "DEMO_GENERATED",
}

SYSTEM_ACTIONS = {
    "RUN_STARTED", "RUN_COMPLETED", "RUN_FAILED",
    "MARKET_SELECTED", "MARKET_REBALANCED", "MARKET_ACTIVATED",
    "MARKET_DEACTIVATED", "MARKET_PAUSED", "MARKET_REACTIVATED",
    "SAFEGUARD_TRIGGERED", "KILL_SWITCH_ACTIVATED", "HUMAN_TAKEOVER",
    "SYSTEM_MAINTENANCE", "BACKUP_COMPLETED", "CAPACITY_EVALUATED",
    "CEO_ALERT", "ERROR"
}


def is_audit_complete(audit: Any, findings_count: int = 0) -> bool:
    """Verifies empirical audit completion: positive overall score, valid url, findings recorded, no failure flags."""
    if not audit:
        return False
    score = float(getattr(audit, "overall_health_score", 0.0) or 0.0)
    if score <= 0.0:
        return False
    url = getattr(audit, "url_audited", "") or ""
    if not url.strip():
        return False
    summary = (getattr(audit, "summary", "") or "").upper()
    if any(k in summary for k in ("RESEARCH_INSUFFICIENT", "FAILED", "UNREACHABLE", "ERROR")):
        return False
    metrics = getattr(audit, "metrics", {}) or {}
    if isinstance(metrics, dict) and (metrics.get("error") or metrics.get("status") == "FAILED"):
        return False
    findings = getattr(audit, "findings", None)
    total_findings = len(findings) if findings is not None else findings_count
    if total_findings <= 0:
        return False
    return True


def is_compliance_passed(
    biz: Any,
    audit: Any = None,
    suppressed_domains: Optional[Set[str]] = None,
    suppressed_emails: Optional[Set[str]] = None
) -> bool:
    """Verifies that a business satisfies all compliance gates: non-prohibited country, not suppressed, no compliance failure flags."""
    if not biz:
        return False
    country = (getattr(biz, "country", "") or "").upper().strip()
    if country in PROHIBITED_COUNTRIES:
        return False
    domain = (getattr(biz, "domain", "") or "").lower().strip()
    if suppressed_domains and domain in suppressed_domains:
        return False
    email = (getattr(biz, "public_email", "") or "").lower().strip()
    if suppressed_emails and email in suppressed_emails:
        return False
    whatsapp_status = getattr(biz, "whatsapp_consent_status", "") or ""
    if whatsapp_status == "COMPLIANCE_FAILED":
        return False
    comp_status = (getattr(biz, "compliance_status", "") or "").upper()
    if comp_status in ("FAILED", "REJECTED", "NON_COMPLIANT"):
        return False
    if audit:
        metrics = getattr(audit, "metrics", {}) or {}
        if isinstance(metrics, dict) and metrics.get("compliance_passed") is False:
            return False
    return True


def is_lead_qualified(
    biz: Any,
    score: Any,
    audit: Any,
    suppressed_domains: Optional[Set[str]] = None,
    suppressed_emails: Optional[Set[str]] = None
) -> bool:
    """
    Canonical Qualification Invariant:
    1. Business provenance is REAL
    2. Verification status is VERIFIED
    3. LeadScore total_score >= 55.0
    4. Empirical audit completed with overall_health_score > 0 and findings recorded
    5. Compliance passed (jurisdiction allowed, not suppressed, no compliance rejection flags)
    """
    if not biz:
        return False
    if classify_business_provenance(biz) != "REAL":
        return False
    if getattr(biz, "verification_status", "") != "VERIFIED":
        return False
    if not score or float(getattr(score, "total_score", 0.0) or 0.0) < 55.0:
        return False
    if not is_audit_complete(audit):
        return False
    if not is_compliance_passed(biz, audit, suppressed_domains, suppressed_emails):
        return False
    return True


def classify_proposal_provenance(prop: Any, biz: Any = None) -> str:
    """Classifies a proposal into REAL_CUSTOMER, TEST_MOCK, or OPERATOR_TEST."""
    if not prop or getattr(prop, "is_mock", False) is True:
        return "TEST_MOCK"
    extra = getattr(prop, "extra_metadata", None) or {}
    if isinstance(extra, dict):
        if any(extra.get(k) is True for k in ("is_mock", "is_test", "mock", "dry_run", "simulation")):
            return "TEST_MOCK"
    title = (getattr(prop, "title", None) or "").lower()
    if "test" in title or "mock" in title:
        return "TEST_MOCK"
    if biz and classify_business_provenance(biz) != "REAL":
        return "OPERATOR_TEST"
    return "REAL_CUSTOMER"


def classify_deal_provenance(deal_or_biz: Any, biz: Any = None) -> str:
    """Classifies a deal into REAL_CUSTOMER or SIMULATED_TEST."""
    if not deal_or_biz:
        return "SIMULATED_TEST"
    if getattr(deal_or_biz, "is_mock", False) is True:
        return "SIMULATED_TEST"
    d_id = str(getattr(deal_or_biz, "id", "") or "")
    if d_id.startswith("mock-") or d_id.startswith("test-"):
        return "SIMULATED_TEST"
    deal_extra = getattr(deal_or_biz, "extra_metadata", None) or {}
    if isinstance(deal_extra, dict):
        if any(deal_extra.get(k) is True for k in ("is_mock", "is_test", "mock", "dry_run", "simulation")):
            return "SIMULATED_TEST"
    d_name = getattr(deal_or_biz, "deal_name", None) or getattr(deal_or_biz, "name", None) or ""
    if any(k in d_name.lower() for k in ("[test]", "[mock]", "sample", "test")):
        return "SIMULATED_TEST"
    target_biz = biz or deal_or_biz
    if classify_business_provenance(target_biz) != "REAL":
        return "SIMULATED_TEST"
    return "REAL_CUSTOMER"


def classify_payment_provenance(
    pay: Any,
    biz: Any = None,
    proposal: Any = None,
    deal: Any = None,
    customer: Any = None,
    outreach: Any = None,
    reply: Any = None
) -> str:
    """
    Classifies a payment into REAL_CUSTOMER, TEST_MOCK, or OPERATOR_TEST with fail-closed commercial provenance:
    If ANY upstream commercial object (payment, proposal, deal, customer, outreach, reply) is synthetic/mock,
    or originates from a simulated/dry-run test, classify as TEST_MOCK or OPERATOR_TEST.
    """
    if not pay:
        return "TEST_MOCK"

    # 1. Direct payment mock/test flags
    if getattr(pay, "is_mock", False) is True:
        return "TEST_MOCK"

    p_id = str(getattr(pay, "id", "") or "")
    if p_id.startswith("mock-") or p_id.startswith("test-") or p_id.startswith("sim-"):
        return "TEST_MOCK"

    extra = getattr(pay, "extra_metadata", None) or {}
    if isinstance(extra, dict):
        if any(extra.get(k) is True for k in ("is_mock", "is_test", "mock", "dry_run", "simulated", "simulation")):
            return "TEST_MOCK"
        source_str = str(extra.get("source", "")).lower()
        if any(k in source_str for k in ("test", "mock", "simulation", "synthetic", "dry_run")):
            return "TEST_MOCK"

    gateway = (getattr(pay, "gateway", None) or getattr(pay, "provider", None) or "").lower()
    if gateway in ("mock", "test", "dev", "simulation", "sandbox"):
        return "TEST_MOCK"

    ref_id = (getattr(pay, "reference_id", None) or "").lower()
    gpay_ref = (getattr(pay, "gpay_reference", None) or "").lower()
    payer_email = (getattr(pay, "payer_email", None) or getattr(pay, "customer_email", None) or "").lower()

    if any(k in payer_email for k in OPERATOR_EMAILS) or any(k in ref_id for k in ("test", "mock", "sufiyan", "sandbox")) or any(k in gpay_ref for k in ("test", "mock", "sandbox")):
        return "OPERATOR_TEST"

    # 2. Upstream Proposal Provenance Check
    target_prop = proposal or getattr(pay, "proposal", None)
    if target_prop:
        if getattr(target_prop, "is_mock", False) is True:
            return "TEST_MOCK"
        prop_extra = getattr(target_prop, "extra_metadata", None) or {}
        if isinstance(prop_extra, dict):
            if any(prop_extra.get(k) is True for k in ("is_mock", "is_test", "mock", "dry_run", "simulation")):
                return "TEST_MOCK"
        prop_prov = classify_proposal_provenance(target_prop, biz)
        if prop_prov in ("TEST_MOCK", "OPERATOR_TEST"):
            return prop_prov

    # 3. Upstream Deal Provenance Check
    target_deal = deal or getattr(pay, "deal", None)
    if target_deal:
        if getattr(target_deal, "is_mock", False) is True:
            return "TEST_MOCK"
        deal_extra = getattr(target_deal, "extra_metadata", None) or {}
        if isinstance(deal_extra, dict):
            if any(deal_extra.get(k) is True for k in ("is_mock", "is_test", "mock", "dry_run", "simulation")):
                return "TEST_MOCK"
        deal_prov = classify_deal_provenance(target_deal, biz)
        if deal_prov != "REAL_CUSTOMER":
            return "TEST_MOCK"

    # 4. Upstream Customer Provenance Check
    target_cust = customer or getattr(pay, "customer", None)
    if target_cust:
        if getattr(target_cust, "is_mock", False) is True:
            return "TEST_MOCK"
        cust_email = (getattr(target_cust, "email", None) or "").lower()
        if any(k in cust_email for k in OPERATOR_EMAILS) or any(k in cust_email for k in ("test", "example.com")):
            return "OPERATOR_TEST"

    # 5. Upstream Outreach / Reply Check
    target_outreach = outreach or getattr(pay, "outreach", None)
    if target_outreach:
        outreach_prov = classify_outreach_provenance(target_outreach, biz)
        if outreach_prov in ("DEV_SIMULATOR", "SIMULATION", "HISTORICAL_DEV", "TEST", "CANARY"):
            return "TEST_MOCK"

    target_reply = reply or getattr(pay, "reply", None)
    if target_reply:
        reply_prov = classify_reply_provenance(target_reply, biz)
        if reply_prov != "REAL_CUSTOMER":
            return "OPERATOR_TEST" if reply_prov == "OPERATOR_TEST" else "TEST_MOCK"

    # 6. Business Provenance Check
    if biz and classify_business_provenance(biz) != "REAL":
        return "OPERATOR_TEST"

    return "REAL_CUSTOMER"


async def resolve_payment_provenance(
    session: AsyncSession,
    pay: Any,
    biz: Any = None
) -> str:
    """
    Asynchronously resolves upstream commercial objects (proposal, deal, customer, biz)
    if they are not already loaded, then classifies the payment.
    """
    if not pay:
        return "TEST_MOCK"

    if getattr(pay, "is_mock", False) is True:
        return "TEST_MOCK"

    target_biz = biz
    if not target_biz and getattr(pay, "business_id", None):
        target_biz = await session.get(Business, pay.business_id)

    target_prop = getattr(pay, "proposal", None)
    if not target_prop and getattr(pay, "proposal_id", None):
        target_prop = await session.get(Proposal, pay.proposal_id)
        if not target_prop:
            target_prop = await session.get(ProjectProposal, pay.proposal_id)

    target_deal = getattr(pay, "deal", None)
    if not target_deal and getattr(pay, "deal_id", None):
        target_deal = await session.get(Deal, pay.deal_id)

    target_cust = getattr(pay, "customer", None)
    if not target_cust and getattr(pay, "customer_id", None):
        target_cust = await session.get(Customer, pay.customer_id)

    return classify_payment_provenance(
        pay=pay,
        biz=target_biz,
        proposal=target_prop,
        deal=target_deal,
        customer=target_cust
    )


def classify_activity_provenance(event: Any) -> str:
    """
    Classifies an activity event using strict fail-closed evaluation:
    1. SIMULATION
    2. CANARY
    3. TEST
    4. SYSTEM
    5. REAL_PRODUCTION (strictly explicit verified actions and non-synthetic attribution)
    6. UNKNOWN (fallback for all unclassified, ambiguous, or unmatched events)
    """
    if event is None:
        return "UNKNOWN"

    action = (
        getattr(event, "action", None)
        or getattr(event, "event_type", None)
        or (event.get("action") if isinstance(event, dict) else None)
        or (event.get("event_type") if isinstance(event, dict) else None)
        or ""
    ).upper().strip()

    meta = (
        getattr(event, "metadata", None)
        or getattr(event, "metadata_json", None)
        or getattr(event, "details", None)
        or (event.get("metadata_json") if isinstance(event, dict) else None)
        or (event.get("metadata") if isinstance(event, dict) else None)
        or {}
    )
    if isinstance(meta, str):
        import json
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    msg = (
        getattr(event, "message", None)
        or (event.get("message") if isinstance(event, dict) else None)
        or ""
    )
    domain = (
        getattr(event, "domain", None)
        or (event.get("domain") if isinstance(event, dict) else None)
        or (meta.get("domain") if isinstance(meta, dict) else None)
        or ""
    ).lower().strip()

    meta_str = str(meta).lower()
    action_str = action.lower()
    msg_str = str(msg).lower()

    # 1. SIMULATION
    if (
        "simulation" in action_str
        or "simulation" in meta_str
        or "dev_simulator" in action_str
        or "dev_simulator" in meta_str
        or (isinstance(meta, dict) and (meta.get("channel") in ("dev_simulator", "simulation") or meta.get("is_simulation") is True or meta.get("dry_run") is True))
        or "[dry run]" in msg_str
        or "[simulated]" in msg_str
    ):
        return "SIMULATION"

    # 2. CANARY
    if (
        "canary" in action_str
        or "canary" in meta_str
        or "canary" in msg_str
        or (isinstance(meta, dict) and meta.get("is_canary") is True)
    ):
        return "CANARY"

    # 3. TEST
    if (
        "test" in action_str
        or "mock" in action_str
        or "test" in meta_str
        or "mock" in meta_str
        or (isinstance(meta, dict) and (meta.get("is_test") is True or meta.get("is_mock") is True))
        or domain.endswith((".test", ".example", ".invalid", ".local"))
        or any(k in domain for k in ("test.", "example.", "mock.", "synthetic"))
    ):
        return "TEST"

    # 4. SYSTEM
    if (
        action in SYSTEM_ACTIONS
        or any(k in action_str for k in ("cron", "scheduler", "heartbeat", "cleanup", "sync", "system", "daemon", "backup", "health", "reconcile", "init", "checkpoint", "rebalance", "capacity"))
        or any(k in msg_str for k in ("cron", "heartbeat", "scheduler", "health check"))
    ):
        return "SYSTEM"

    # 5. REAL_PRODUCTION
    if action in REAL_PRODUCTION_ACTIONS:
        if domain:
            if domain.endswith((".test", ".example", ".invalid", ".local")) or any(k in domain for k in ("mock", "test", "synthetic", "example")):
                return "TEST"
            if "agencyos.local" in domain or "titan.email" in domain:
                return "SYSTEM"
        
        email = (meta.get("recipient_email") or meta.get("email") or meta.get("payer_email") or "") if isinstance(meta, dict) else ""
        if email:
            email_lower = str(email).lower()
            if any(op in email_lower for op in OPERATOR_EMAILS) or "agencyos.local" in email_lower:
                return "TEST"

        return "REAL_PRODUCTION"

    # 6. UNKNOWN (FAIL CLOSED)
    return "UNKNOWN"


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

    # 3. Real Qualified Leads: verified lead with LeadScore.total_score >= 55.0, audit completed, compliance passed, real provenance
    q_supp = select(SuppressionList)
    supp_rows = (await session.execute(q_supp)).scalars().all()
    supp_domains = {s.domain.lower() for s in supp_rows if s.domain}
    supp_emails = {s.email.lower() for s in supp_rows if s.email}

    q_candidates = (
        select(Business, LeadScore)
        .join(LeadScore, LeadScore.business_id == Business.id)
        .where(
            Business.verification_status == "VERIFIED",
            LeadScore.total_score >= 55.0,
            *biz_filters
        )
    )
    candidates = (await session.execute(q_candidates)).all()
    cand_biz_ids = [b.id for b, _ in candidates]
    audit_map = {}
    if cand_biz_ids:
        q_audits = (
            select(AuditRun)
            .where(AuditRun.business_id.in_(cand_biz_ids))
            .order_by(desc(AuditRun.audited_at))
        )
        for a in (await session.execute(q_audits)).scalars().all():
            if a.business_id not in audit_map:
                audit_map[a.business_id] = a

    real_qualified_leads = 0
    for b, ls in candidates:
        audit = audit_map.get(b.id)
        if is_lead_qualified(b, ls, audit, supp_domains, supp_emails):
            real_qualified_leads += 1

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

    pay_prop_ids = [py.proposal_id for py in all_payments if py.proposal_id]
    pay_prop_map = {}
    if pay_prop_ids:
        pyp_res = await session.execute(select(Proposal).where(Proposal.id.in_(pay_prop_ids)))
        pay_prop_map = {p.id: p for p in pyp_res.scalars().all()}
        missing_prop_ids = [pid for pid in pay_prop_ids if pid not in pay_prop_map]
        if missing_prop_ids:
            pypp_res = await session.execute(select(ProjectProposal).where(ProjectProposal.id.in_(missing_prop_ids)))
            for pp in pypp_res.scalars().all():
                pay_prop_map[pp.id] = pp

    pay_deal_ids = [py.deal_id for py in all_payments if py.deal_id]
    pay_deal_map = {}
    if pay_deal_ids:
        pyd_res = await session.execute(select(Deal).where(Deal.id.in_(pay_deal_ids)))
        pay_deal_map = {d.id: d for d in pyd_res.scalars().all()}

    pay_cust_ids = [py.customer_id for py in all_payments if py.customer_id]
    pay_cust_map = {}
    if pay_cust_ids:
        pyc_res = await session.execute(select(Customer).where(Customer.id.in_(pay_cust_ids)))
        pay_cust_map = {c.id: c for c in pyc_res.scalars().all()}

    real_payments_pending = 0
    real_payments_confirmed = 0
    real_verified_revenue = 0.0

    for py in all_payments:
        biz = pay_biz_map.get(py.business_id)
        prop = pay_prop_map.get(py.proposal_id)
        deal = pay_deal_map.get(py.deal_id)
        cust = pay_cust_map.get(py.customer_id)
        if classify_payment_provenance(py, biz=biz, proposal=prop, deal=deal, customer=cust) == "REAL_CUSTOMER":
            st = (py.status or "").upper()
            if st in ("PENDING", "PROCESSING", "AUTHORIZED", "PAYMENT_PENDING", "PAYMENT_REQUESTED", "PAYMENT_PENDING_VERIFICATION", "PAYMENT_REVIEW_REQUIRED"):
                real_payments_pending += 1
            elif st in ("PAID", "COMPLETED", "SETTLED", "PAYMENT_CONFIRMED", "VERIFIED_PAYMENT"):
                real_payments_confirmed += 1
                real_verified_revenue += float(py.amount or 0.0)

    # 8. Real Deals Won (Zero Deal Inference: Payments are NOT deals)
    q_deals = select(func.count(Business.id)).where(
        Business.pipeline_stage == PipelineStage.WON.value,
        *biz_filters
    )
    real_deals = (await session.execute(q_deals)).scalar() or 0

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
