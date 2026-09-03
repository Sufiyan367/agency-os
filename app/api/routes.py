from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.database.connection import get_db
from app.database.models import (
    Business, Contact, AuditRun, AuditFinding, LeadScore,
    Offer, OutreachMessage, OutreachStatus, PipelineStage, SystemRun, MarketOpportunity, Customer,
    Payment, Reply, Project, Proposal, Deal, DealAuditTrail
)
from app.analytics.engine import analytics_engine
from app.market_intelligence.engine import market_intelligence_engine
from app.outreach.queue import outreach_approval_queue
from app.outreach.sender import outreach_sender_adapter
from app.crm.pipeline import pipeline_manager
from app.crm.reply_classifier import reply_classifier
from app.crm.inbox_poller import inbox_poller
from app.payments.provider import stripe_payment_provider, get_active_payment_provider
from app.payments.razorpay import razorpay_payment_provider
from app.payments.service import payment_service
from app.payments.deal_service import deal_closing_service
from app.orchestrator.worker import agency_worker
from app.delivery.report_generator import delivery_report_generator
from app.orchestrator.loop import orchestrator
from app.core.config import settings
from app.core.security import (
    create_session_token, verify_session_token,
    verify_login_credentials, verify_api_key
)
from app.database.backup import backup_manager

router = APIRouter()

# --- Authentication Dependency ---
def require_auth(request: Request) -> str:
    if not settings.AUTH_ENABLED:
        return "admin"
    
    # 1. Check secure session cookie
    cookie_token = request.cookies.get("agency_session")
    if cookie_token:
        user = verify_session_token(cookie_token)
        if user:
            return user
            
    # 2. Check Authorization Header (Bearer or API Key)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if verify_api_key(token):
            return "api_client"
        user = verify_session_token(token)
        if user:
            return user
            
    raise HTTPException(status_code=401, detail="Authentication required. Please log in.")

# --- Authentication Endpoints ---
class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/api/auth/login")
async def login(req: LoginRequest, response: Response):
    if not verify_login_credentials(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    token = create_session_token(req.username.strip())
    response.set_cookie(
        key="agency_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.SESSION_MAX_AGE_DAYS * 86400,
        secure=not settings.DEBUG
    )
    return {"status": "SUCCESS", "username": req.username, "token": token}

@router.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("agency_session")
    return {"status": "SUCCESS", "message": "Logged out successfully"}

@router.get("/api/auth/me")
async def auth_me(request: Request):
    if not settings.AUTH_ENABLED:
        return {"authenticated": True, "auth_enabled": False, "username": "admin"}
    
    token = request.cookies.get("agency_session")
    user = verify_session_token(token) if token else None
    return {
        "authenticated": bool(user),
        "auth_enabled": True,
        "username": user
    }

# --- Cloud Health & Readiness ---
@router.get("/health")
@router.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    db_status = "connected"
    try:
        await db.execute(select(Business.id).limit(1))
    except Exception:
        db_status = "unreachable"

    worker_status = agency_worker.get_status()
    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "service": settings.APP_NAME,
        "env": settings.APP_ENV,
        "database": db_status,
        "worker": {
            "is_running": worker_status.get("is_running", False),
            "ticks_executed": worker_status.get("ticks_executed", 0),
            "last_tick_at": worker_status.get("last_tick_at")
        },
        "cloud_mode": True,
        "auth_enabled": settings.AUTH_ENABLED
    }

@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(select(Business).limit(1))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database not ready: {str(e)}")

# --- Database Backup & Recovery Endpoints ---
@router.get("/api/system/backups", dependencies=[Depends(require_auth)])
async def get_backups():
    return {"backups": backup_manager.list_backups()}

@router.post("/api/system/backup", dependencies=[Depends(require_auth)])
async def trigger_backup():
    try:
        res = backup_manager.create_backup()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")

# Metrics
@router.get("/api/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db)):
    return await analytics_engine.get_dashboard_metrics(db)

# Markets
@router.get("/api/markets")
async def get_markets(db: AsyncSession = Depends(get_db)):
    q = select(MarketOpportunity).order_by(desc(MarketOpportunity.opportunity_score))
    opps = (await db.execute(q)).scalars().all()
    results = []
    for o in opps:
        results.append({
            "id": o.id,
            "country": o.country.name if o.country else "Unknown",
            "country_code": o.country.code if o.country else "",
            "niche": o.niche.name if o.niche else "Unknown",
            "niche_slug": o.niche.slug if o.niche else "",
            "opportunity_score": o.opportunity_score,
            "expected_deal_value": o.expected_deal_value,
            "digital_weakness": o.digital_weakness_score,
            "reasoning": o.reasoning,
            "confidence": o.confidence
        })
    return results

# Leads
@router.get("/api/leads")
async def list_leads(
    stage: Optional[str] = None,
    priority: Optional[str] = None,
    country: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    q = select(Business).order_by(desc(Business.id))
    if stage:
        q = q.where(Business.pipeline_stage == stage)
    if country:
        q = q.where(Business.country == country.upper())
    if search:
        q = q.where(Business.name.ilike(f"%{search}%") | Business.domain.ilike(f"%{search}%"))

    businesses = (await db.execute(q.limit(limit))).scalars().all()
    results = []
    for b in businesses:
        score_val = b.lead_score.total_score if b.lead_score else None
        prio_val = b.lead_score.priority if b.lead_score else None
        if priority and prio_val != priority:
            continue
        results.append({
            "id": b.id,
            "name": b.name,
            "domain": b.domain,
            "website_url": b.website_url,
            "country": b.country,
            "city": b.city,
            "niche": b.niche,
            "email": b.public_email,
            "phone": b.phone,
            "verification_status": b.verification_status,
            "pipeline_stage": b.pipeline_stage,
            "lead_score": score_val,
            "priority": prio_val
        })
    return results

# Lead Detail
@router.get("/api/leads/{lead_id}")
async def get_lead_detail(lead_id: int, db: AsyncSession = Depends(get_db)):
    b = await db.get(Business, lead_id)
    if not b:
        raise HTTPException(status_code=404, detail="Lead not found")

    audit_q = select(AuditRun).where(AuditRun.business_id == lead_id).order_by(desc(AuditRun.audited_at))
    audit = (await db.execute(audit_q)).scalars().first()

    findings_list = []
    if audit:
        findings_q = select(AuditFinding).where(AuditFinding.audit_id == audit.id)
        findings = (await db.execute(findings_q)).scalars().all()
        for f in findings:
            findings_list.append({
                "category": f.category,
                "finding": f.finding,
                "severity": f.severity,
                "evidence": f.evidence,
                "recommended_fix": f.recommended_fix,
                "estimated_business_impact": f.estimated_business_impact
            })

    offer_q = select(Offer).where(Offer.business_id == lead_id)
    offer = (await db.execute(offer_q)).scalars().first()

    outreach_q = select(OutreachMessage).where(OutreachMessage.business_id == lead_id)
    outreach = (await db.execute(outreach_q)).scalars().first()

    return {
        "business": {
            "id": b.id,
            "name": b.name,
            "domain": b.domain,
            "website_url": b.website_url,
            "country": b.country,
            "city": b.city,
            "niche": b.niche,
            "email": b.public_email,
            "email_status": b.email_status,
            "phone": b.phone,
            "verification_status": b.verification_status,
            "pipeline_stage": b.pipeline_stage
        },
        "score": {
            "total_score": b.lead_score.total_score if b.lead_score else None,
            "priority": b.lead_score.priority if b.lead_score else None,
            "rationale": b.lead_score.rationale if b.lead_score else None,
            "breakdown": b.lead_score.scoring_breakdown if b.lead_score else {}
        },
        "audit": {
            "overall_health": audit.overall_health_score if audit else None,
            "performance": audit.performance_score if audit else None,
            "seo": audit.seo_score if audit else None,
            "accessibility": audit.a11y_score if audit else None,
            "ux_conversion": audit.ux_conversion_score if audit else None,
            "security": audit.security_score if audit else None,
            "content": audit.content_score if audit else None,
            "summary": audit.summary if audit else None,
            "tech_stack": audit.tech_stack if audit else [],
            "findings": findings_list
        },
        "offer": {
            "title": offer.title if offer else None,
            "service_type": offer.service_type if offer else None,
            "price_min": offer.suggested_price_min if offer else None,
            "price_max": offer.suggested_price_max if offer else None,
            "recommended_price": offer.recommended_price if offer else None,
            "delivery_days": offer.estimated_delivery_days if offer else None,
            "deliverables": offer.deliverables if offer else [],
            "value_prop": offer.value_proposition if offer else None
        },
        "outreach": {
            "id": outreach.id if outreach else None,
            "status": outreach.status if outreach else None,
            "subject": outreach.subject if outreach else None,
            "body": outreach.body if outreach else None,
            "variant": outreach.variant_name if outreach else None
        }
    }

# Outreach Queue
@router.get("/api/queue")
async def get_outreach_queue(db: AsyncSession = Depends(get_db)):
    msgs = await outreach_approval_queue.list_pending(db)
    items = []
    for m in msgs:
        biz = await db.get(Business, m.business_id)
        offer = await db.get(Offer, m.offer_id) if m.offer_id else None
        items.append({
            "message_id": m.id,
            "business_id": m.business_id,
            "business_name": biz.name if biz else "Unknown",
            "domain": biz.domain if biz else "",
            "country": biz.country if biz else "",
            "niche": biz.niche if biz else "",
            "recipient_email": m.recipient_email,
            "subject": m.subject,
            "body": m.body,
            "variant": m.variant_name,
            "status": m.status,
            "confidence": m.confidence,
            "recommended_service": offer.title if offer else "Website Turnaround",
            "recommended_price": offer.recommended_price if offer else 650.0,
            "lead_score": biz.lead_score.total_score if biz and biz.lead_score else 75.0
        })
    return items

@router.get("/api/outreach/delivery-metrics")
async def get_outreach_delivery_metrics(db: AsyncSession = Depends(get_db)):
    from app.outreach.delivery_service import outreach_delivery_service
    return await outreach_delivery_service.get_outreach_metrics(db)

@router.post("/api/queue/{message_id}/approve")
async def approve_outreach(message_id: int, auto_send: bool = True, db: AsyncSession = Depends(get_db)):
    appr = await outreach_approval_queue.approve_message(db, message_id)
    send_result = None
    if auto_send:
        send_result = await outreach_sender_adapter.send_approved_message(db, message_id)
    return {"status": "APPROVED", "message_id": appr.id, "send_result": send_result}

@router.post("/api/queue/{message_id}/reject")
async def reject_outreach(message_id: int, db: AsyncSession = Depends(get_db)):
    rej = await outreach_approval_queue.reject_message(db, message_id)
    return {"status": "REJECTED", "message_id": rej.id}

class EditMessageRequest(BaseModel):
    subject: str
    body: str

@router.post("/api/queue/{message_id}/edit")
async def edit_outreach(message_id: int, req: EditMessageRequest, db: AsyncSession = Depends(get_db)):
    edited = await outreach_approval_queue.edit_message(db, message_id, req.subject, req.body)
    return {"status": "EDITED", "message_id": edited.id, "subject": edited.subject}

# Pipeline Transition
class StageTransitionRequest(BaseModel):
    target_stage: str
    note: str = ""
    deal_value: float = 0.0

@router.post("/api/pipeline/{business_id}/transition")
async def transition_pipeline(business_id: int, req: StageTransitionRequest, db: AsyncSession = Depends(get_db)):
    try:
        stage_enum = PipelineStage(req.target_stage)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid pipeline stage: {req.target_stage}")

    updated = await pipeline_manager.transition_stage(
        db, business_id, stage_enum, note=req.note, deal_value=req.deal_value
    )
    return {"status": "SUCCESS", "business_id": updated.id, "new_stage": updated.pipeline_stage}

# Trigger Full Cycle
@router.post("/api/run-cycle")
async def trigger_cycle():
    summary = await orchestrator.run_full_autonomous_cycle(target_leads_per_market=4, max_opportunities_to_mine=2)
    return summary

# --- Canonical Autonomous Prospecting Endpoints ---

class ProspectingRunRequest(BaseModel):
    countries: Optional[List[str]] = None
    cities: Optional[List[str]] = None
    niches: Optional[List[str]] = None
    min_service_value: float = 500.0
    max_prospects: int = 20
    provider: str = "real"

@router.get("/api/prospecting/config")
async def get_prospecting_config():
    """Returns available countries, cities, niches and default commercial floor from configuration."""
    from app.lead_generation.targeting import load_targeting_config
    cfg = load_targeting_config()
    return {
        "available_countries": [
            {
                "code": c.code,
                "name": c.name,
                "regions": c.regions,
                "cities": c.cities
            } for c in cfg.available_countries
        ],
        "available_niches": [
            {
                "name": n.name,
                "slug": n.slug,
                "category": n.category,
                "min_estimated_service_value": n.min_estimated_service_value
            } for n in cfg.available_niches
        ],
        "defaults": {
            "min_service_value": 500.0,
            "max_prospects": 20,
            "countries": [c.code for c in cfg.available_countries] if cfg.available_countries else ["US"],
            "cities": cfg.cities,
            "niches": cfg.niches
        }
    }

@router.post("/api/prospecting/run")
async def trigger_prospecting_cycle(req: ProspectingRunRequest):
    """
    Triggers an autonomous prospecting cycle from the Dashboard.
    Enforces $500 minimum commercial floor and delegates to the canonical LeadDiscoveryService.
    """
    if req.min_service_value < 500.0:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum commercial value (${req.min_service_value:.2f}) cannot be less than the $500.00 floor."
        )

    from app.lead_generation.job_runner import prospecting_job_manager
    try:
        res = await prospecting_job_manager.start_prospecting_job(
            targeting_params=req.model_dump(),
            provider_type=req.provider
        )
        return res
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start prospecting cycle: {str(e)}")

@router.get("/api/prospecting/status")
async def get_prospecting_status(job_id: Optional[str] = None):
    """Returns the live status and progress counters of the prospecting cycle."""
    from app.lead_generation.job_runner import prospecting_job_manager
    return prospecting_job_manager.get_current_status(job_id=job_id)

# System Runs
@router.get("/api/runs")
async def get_system_runs(db: AsyncSession = Depends(get_db)):
    q = select(SystemRun).order_by(desc(SystemRun.started_at)).limit(20)
    runs = (await db.execute(q)).scalars().all()
    return [{
        "run_id": r.run_id,
        "job_name": r.job_name,
        "status": r.status,
        "records_processed": r.records_processed,
        "records_failed": r.records_failed,
        "duration_seconds": r.duration_seconds,
        "started_at": r.started_at.isoformat() if r.started_at else None
    } for r in runs]

# Audit Report Export
@router.get("/api/reports/audit/{business_id}")
async def export_audit_report(business_id: int, db: AsyncSession = Depends(get_db)):
    report_md = await delivery_report_generator.generate_audit_report_markdown(db, business_id)
    return {"business_id": business_id, "markdown": report_md}

# --- Payments & Stripe Webhooks ---

class CheckoutSessionRequest(BaseModel):
    business_id: int
    offer_id: Optional[int] = None

@router.post("/api/payments/checkout-session")
async def create_checkout_session(req: CheckoutSessionRequest, db: AsyncSession = Depends(get_db)):
    biz = await db.get(Business, req.business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    offer = None
    if req.offer_id:
        offer = await db.get(Offer, req.offer_id)
    else:
        q_off = select(Offer).where(Offer.business_id == req.business_id).order_by(desc(Offer.created_at))
        offer = (await db.execute(q_off)).scalars().first()

    title = offer.title if offer else "Website Turnaround & Optimization Package"
    amount = offer.recommended_price if offer else 650.0

    provider = get_active_payment_provider()
    session_data = await provider.create_payment_link(
        business_id=biz.id,
        offer_id=offer.id if offer else 0,
        title=title,
        amount_usd=amount,
        customer_email=biz.public_email
    )
    return session_data

@router.get("/api/payments")
async def list_payments(db: AsyncSession = Depends(get_db)):
    q = select(Payment).order_by(desc(Payment.created_at))
    payments = (await db.execute(q)).scalars().all()
    results = []
    for p in payments:
        cust = await db.get(Customer, p.customer_id)
        results.append({
            "id": p.id,
            "customer_id": p.customer_id,
            "company_name": cust.company_name if cust else "Unknown",
            "amount": p.amount,
            "currency": p.currency,
            "status": p.status,
            "reference_id": p.reference_id,
            "created_at": p.created_at.isoformat() if p.created_at else None
        })
    return results

class ManualPaymentConfirmRequest(BaseModel):
    business_id: int
    amount: float
    reference_id: str
    payer_email: Optional[str] = None

@router.post("/api/payments/confirm-manual")
async def confirm_payment_manual(req: ManualPaymentConfirmRequest, db: AsyncSession = Depends(get_db)):
    res = await payment_service.confirm_payment_and_onboard(
        session=db,
        business_id=req.business_id,
        amount_usd=req.amount,
        reference_id=req.reference_id,
        payer_email=req.payer_email
    )
    return res

@router.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload_bytes = await request.body()
    sig_header = request.headers.get("x-razorpay-signature")

    is_valid, reason = razorpay_payment_provider.verify_webhook_signature(payload_bytes, sig_header)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Webhook signature verification failed: {reason}")

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("event", "")
    payload = event.get("payload", {})

    # 1. Payment Link Paid Event
    if event_type == "payment_link.paid":
        plink_entity = payload.get("payment_link", {}).get("entity", {})
        pmt_entity = payload.get("payment", {}).get("entity", {})
        notes = plink_entity.get("notes") or pmt_entity.get("notes") or {}
        biz_id_str = notes.get("business_id")
        amount_subunits = plink_entity.get("amount_paid") or pmt_entity.get("amount") or 0
        amount_usd = float(amount_subunits) / 100.0 if amount_subunits > 100 else float(amount_subunits)
        customer_email = plink_entity.get("customer", {}).get("email") or pmt_entity.get("email")
        ref_id = pmt_entity.get("id") or plink_entity.get("id", f"rzp_{event.get('created_at', 'evt')}")

        if biz_id_str and str(biz_id_str).isdigit():
            biz_id = int(biz_id_str)
            await payment_service.confirm_payment_and_onboard(
                session=db,
                business_id=biz_id,
                amount_usd=amount_usd,
                reference_id=ref_id,
                payer_email=customer_email
            )
            return {"status": "SUCCESS", "event": event_type, "business_id": biz_id}

    # 2. Payment Captured / Order Paid Event
    elif event_type in ("payment.captured", "order.paid"):
        pmt_entity = payload.get("payment", {}).get("entity", {})
        notes = pmt_entity.get("notes", {})
        biz_id_str = notes.get("business_id")
        amount_subunits = pmt_entity.get("amount", 0)
        amount_usd = float(amount_subunits) / 100.0 if amount_subunits > 100 else float(amount_subunits)
        customer_email = pmt_entity.get("email")
        ref_id = pmt_entity.get("id", f"rzp_{event.get('created_at', 'evt')}")

        if biz_id_str and str(biz_id_str).isdigit():
            biz_id = int(biz_id_str)
            await payment_service.confirm_payment_and_onboard(
                session=db,
                business_id=biz_id,
                amount_usd=amount_usd,
                reference_id=ref_id,
                payer_email=customer_email
            )
            return {"status": "SUCCESS", "event": event_type, "business_id": biz_id}

    # Check if this event belongs to a commercial proposal/deal
    prop_id = None
    pmt_entity = payload.get("payment", {}).get("entity", {})
    plink_entity = payload.get("payment_link", {}).get("entity", {})
    notes = pmt_entity.get("notes") or plink_entity.get("notes") or {}
    if "proposal_id" in notes and str(notes["proposal_id"]).isdigit():
        prop_id = int(notes["proposal_id"])
    
    if prop_id or pmt_entity.get("order_id"):
        try:
            deal_res = await deal_closing_service.process_payment_webhook(
                session=db,
                payload_bytes=payload_bytes,
                signature=sig_header,
                event_dict=event
            )
            return deal_res
        except Exception as de:
            logger.warning(f"[Razorpay Webhook] Deal closing service check: {de}")

    return {"status": "ACKNOWLEDGED", "event": event_type}

# --- Commercial Proposal & Deal Endpoints ---
class CreateProposalRequest(BaseModel):
    business_id: int
    title: str
    total_value: float
    advance_required: Optional[float] = None
    advance_percentage: Optional[float] = None
    service_type: Optional[str] = "Website Turnaround & Automation"
    lead_id: Optional[int] = None
    is_mock: Optional[bool] = None

class RequestPaymentOrderRequest(BaseModel):
    payment_type: Optional[str] = "ADVANCE"

@router.post("/api/proposals")
async def create_proposal_endpoint(req: CreateProposalRequest, db: AsyncSession = Depends(get_db)):
    try:
        adv_req = req.advance_required
        if adv_req is None:
            pct = req.advance_percentage if req.advance_percentage is not None else getattr(settings, "DEFAULT_ADVANCE_PERCENTAGE", 40.0)
            adv_req = round(req.total_value * (pct / 100.0), 2)

        prop = await deal_closing_service.create_proposal(
            session=db,
            business_id=req.business_id,
            title=req.title,
            total_value=req.total_value,
            advance_required=adv_req,
            service_type=req.service_type or "Website Turnaround & Automation",
            lead_id=req.lead_id,
            is_mock=req.is_mock
        )
        return {
            "id": prop.id,
            "business_id": prop.business_id,
            "title": prop.title,
            "total_value": prop.total_value,
            "advance_required": prop.advance_required,
            "remaining_balance": prop.remaining_balance,
            "status": prop.status,
            "delivery_status": prop.delivery_status,
            "created_at": prop.created_at.isoformat()
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.post("/api/proposals/{proposal_id}/approve")
async def approve_proposal_endpoint(proposal_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        operator = "operator"
        prop = await deal_closing_service.approve_proposal(db, proposal_id, operator=operator)
        return {
            "status": "APPROVED",
            "proposal_id": prop.id,
            "approved_by": prop.approved_by,
            "approved_at": prop.approved_at.isoformat() if prop.approved_at else None,
            "total_value": prop.total_value,
            "advance_required": prop.advance_required
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.post("/api/proposals/{proposal_id}/request-payment")
async def request_payment_order_endpoint(
    proposal_id: int,
    req: RequestPaymentOrderRequest = RequestPaymentOrderRequest(),
    db: AsyncSession = Depends(get_db)
):
    try:
        res = await deal_closing_service.request_payment_order(
            session=db,
            proposal_id=proposal_id,
            payment_type=req.payment_type or "ADVANCE"
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.get("/api/deals/metrics")
async def get_deals_metrics(include_mock: bool = False, db: AsyncSession = Depends(get_db)):
    return await deal_closing_service.get_real_deal_metrics(session=db, include_mock=include_mock)

@router.get("/api/deals")
async def list_deals(db: AsyncSession = Depends(get_db)):
    q = select(Proposal).order_by(desc(Proposal.id))
    props = (await db.execute(q)).scalars().all()
    results = []
    for p in props:
        biz = await db.get(Business, p.business_id)
        results.append({
            "id": p.id,
            "business_id": p.business_id,
            "business_name": biz.name if biz else f"Business #{p.business_id}",
            "title": p.title,
            "service_type": p.service_type,
            "total_value": p.total_value,
            "advance_required": p.advance_required,
            "advance_received": p.advance_received,
            "remaining_balance": p.remaining_balance,
            "status": p.status,
            "delivery_status": p.delivery_status,
            "approved_by": p.approved_by,
            "is_mock": p.is_mock,
            "created_at": p.created_at.isoformat() if p.created_at else None
        })
    return results

@router.get("/api/deals/{proposal_id}")
async def get_deal_detail(proposal_id: int, db: AsyncSession = Depends(get_db)):
    prop = await db.get(Proposal, proposal_id)
    if not prop:
        raise HTTPException(status_code=404, detail=f"Deal/Proposal #{proposal_id} not found")
    biz = await db.get(Business, prop.business_id)
    
    q_audit = select(DealAuditTrail).where(DealAuditTrail.proposal_id == proposal_id).order_by(DealAuditTrail.created_at.asc())
    audits = (await db.execute(q_audit)).scalars().all()
    
    q_pmts = select(Payment).where(Payment.proposal_id == proposal_id).order_by(Payment.created_at.desc())
    pmts = (await db.execute(q_pmts)).scalars().all()

    return {
        "id": prop.id,
        "business_id": prop.business_id,
        "business_name": biz.name if biz else f"Business #{prop.business_id}",
        "domain": biz.domain if biz else "",
        "title": prop.title,
        "service_type": prop.service_type,
        "total_value": prop.total_value,
        "advance_required": prop.advance_required,
        "advance_received": prop.advance_received,
        "remaining_balance": prop.remaining_balance,
        "status": prop.status,
        "delivery_status": prop.delivery_status,
        "approved_by": prop.approved_by,
        "approved_at": prop.approved_at.isoformat() if prop.approved_at else None,
        "is_mock": prop.is_mock,
        "created_at": prop.created_at.isoformat() if prop.created_at else None,
        "payments": [
            {
                "id": p.id,
                "amount": p.amount,
                "currency": p.currency,
                "payment_type": p.payment_type,
                "status": p.status,
                "reference_id": p.reference_id,
                "razorpay_payment_id": p.razorpay_payment_id,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None
            }
            for p in pmts
        ],
        "audit_trail": [
            {
                "event_type": a.event_type,
                "operator": a.operator,
                "payload": a.payload,
                "created_at": a.created_at.isoformat()
            }
            for a in audits
        ]
    }

@router.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload_bytes = await request.body()
    sig_header = request.headers.get("stripe-signature")

    is_valid, reason = stripe_payment_provider.verify_webhook_signature(payload_bytes, sig_header)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Webhook signature verification failed: {reason}")

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("type", "")
    data_obj = event.get("data", {}).get("object", {})

    if event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        meta = data_obj.get("metadata", {})
        biz_id_str = meta.get("business_id") or data_obj.get("client_reference_id")
        amount_total = data_obj.get("amount_total") or data_obj.get("amount") or 0
        amount_usd = float(amount_total) / 100.0 if amount_total > 100 else float(amount_total)
        customer_email = data_obj.get("customer_details", {}).get("email") or data_obj.get("customer_email")
        ref_id = data_obj.get("id", f"stripe_{event.get('id', 'evt')}")

        if biz_id_str and str(biz_id_str).isdigit():
            biz_id = int(biz_id_str)
            await payment_service.confirm_payment_and_onboard(
                session=db,
                business_id=biz_id,
                amount_usd=amount_usd,
                reference_id=ref_id,
                payer_email=customer_email
            )
            return {"status": "SUCCESS", "event": event_type, "business_id": biz_id}

    return {"status": "ACKNOWLEDGED", "event": event_type}

# --- Inbound Email & Reply Webhooks ---

class InboundEmailWebhook(BaseModel):
    sender_email: str
    subject: str = ""
    body: str

@router.post("/api/webhooks/inbound-email")
async def inbound_email_webhook(data: InboundEmailWebhook, db: AsyncSession = Depends(get_db)):
    reply = await inbox_poller.process_inbound_message(
        session=db,
        sender_email=data.sender_email,
        subject=data.subject,
        body=data.body
    )
    if not reply:
        return {"status": "IGNORED", "message": "Sender does not match any active lead."}
    return {
        "status": "PROCESSED",
        "reply_id": reply.id,
        "classification": reply.classification,
        "confidence": reply.confidence,
        "suggested_response": reply.suggested_response
    }

# --- Replies Management ---

@router.get("/api/replies")
async def list_replies(db: AsyncSession = Depends(get_db)):
    q = select(Reply).order_by(desc(Reply.received_at))
    replies = (await db.execute(q)).scalars().all()
    results = []
    for r in replies:
        biz = await db.get(Business, r.business_id)
        results.append({
            "id": r.id,
            "business_id": r.business_id,
            "business_name": biz.name if biz else "Unknown",
            "domain": biz.domain if biz else "",
            "sender_email": r.sender_email,
            "raw_body": r.raw_body,
            "classification": r.classification,
            "confidence": r.confidence,
            "suggested_response": r.suggested_response,
            "received_at": r.received_at.isoformat() if r.received_at else None
        })
    return results

class SimulateReplyRequest(BaseModel):
    business_id: int
    sender_email: str
    body: str

@router.post("/api/replies/simulate")
async def simulate_incoming_reply(req: SimulateReplyRequest, db: AsyncSession = Depends(get_db)):
    reply = await reply_classifier.process_incoming_reply(
        session=db,
        business_id=req.business_id,
        sender_email=req.sender_email,
        raw_body=req.body
    )
    return {
        "status": "SUCCESS",
        "reply_id": reply.id,
        "classification": reply.classification,
        "confidence": reply.confidence,
        "suggested_response": reply.suggested_response
    }

# --- Background Worker Control ---

@router.get("/api/worker/status")
async def get_worker_status():
    return agency_worker.get_status()

@router.post("/api/worker/tick")
async def trigger_worker_tick():
    summary = await agency_worker.execute_tick()
    return summary

# --- Production Onboarding & Settings Endpoints ---

class UpdateEmailSettingsRequest(BaseModel):
    provider: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    resend_api_key: Optional[str] = None
    sendgrid_api_key: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None

class TestEmailRequest(BaseModel):
    recipient_email: str

class ToggleLiveEmailRequest(BaseModel):
    enabled: bool

class UpdatePaymentSettingsRequest(BaseModel):
    key_id: Optional[str] = None
    key_secret: Optional[str] = None
    mode: Optional[str] = None
    currency: Optional[str] = None
    default_advance_percentage: Optional[float] = None

@router.get("/api/settings")
async def get_settings_endpoint():
    from app.core.settings_manager import settings_manager
    return settings_manager.get_masked_settings()

@router.post("/api/settings/email")
async def update_email_settings_endpoint(req: UpdateEmailSettingsRequest):
    from app.core.settings_manager import settings_manager
    try:
        return await settings_manager.update_email_settings(
            provider=req.provider,
            from_email=req.from_email,
            from_name=req.from_name,
            reply_to=req.reply_to,
            resend_api_key=req.resend_api_key,
            sendgrid_api_key=req.sendgrid_api_key,
            smtp_host=req.smtp_host,
            smtp_port=req.smtp_port,
            smtp_username=req.smtp_username,
            smtp_password=req.smtp_password
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.post("/api/settings/email/test")
async def send_test_email_endpoint(req: TestEmailRequest):
    from app.core.settings_manager import settings_manager
    try:
        return await settings_manager.send_test_email(req.recipient_email)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/settings/email/toggle-live")
async def toggle_live_email_endpoint(req: ToggleLiveEmailRequest):
    from app.core.settings_manager import settings_manager
    try:
        return await settings_manager.toggle_live_email(req.enabled)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/settings/payments")
async def update_payment_settings_endpoint(req: UpdatePaymentSettingsRequest):
    from app.core.settings_manager import settings_manager
    try:
        return await settings_manager.update_payment_settings(
            key_id=req.key_id,
            key_secret=req.key_secret,
            mode=req.mode,
            currency=req.currency,
            default_advance_percentage=req.default_advance_percentage
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

# --- First Client Mode & Production Lifecycle Endpoints ---

@router.get("/api/production/status")
async def get_production_status_endpoint():
    from app.core.production_mode import first_client_mode
    return first_client_mode.get_mode_status()

@router.post("/api/production/reset")
async def reset_production_database_endpoint():
    from app.database.production_init import production_reset_service
    try:
        summary = production_reset_service.initialize_clean_production(create_backup=True)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset production environment: {e}")

