from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, Header, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os
from pydantic import BaseModel

from app.database.connection import get_db
from app.database.models import (
    Business, Contact, AuditRun, AuditFinding, LeadScore,
    Offer, OutreachMessage, OutreachStatus, PipelineStage, SystemRun, MarketOpportunity, Customer,
    Payment, Reply, Project, Proposal, Deal, DealAuditTrail,
    AgentActivityEvent, Artifact, ProspectMemory, Country, Niche, ModelPrediction,
    PaymentWebhookEvent, SecurityAuditLog, ProspectEvidence, ClientIntelligenceRecord, PipelineEvent,
    User
)
from app.services.audit_service import AuditService, sanitize_audit_payload
from app.ml import (
    model_runner, baseline_scorer, prospect_ranker,
    training_pipeline, feature_store, expected_revenue_model,
    FEATURE_NAMES
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
from app.core.logging import logger
from app.core.security import (
    create_session_token, verify_session_token,
    verify_login_credentials, verify_api_key
)
from app.database.backup import backup_manager

router = APIRouter()

# --- Authentication Dependency ---
def get_current_user_info(request: Request) -> Dict[str, str]:
    if not settings.AUTH_ENABLED:
        return {"username": "admin", "role": "admin"}
    
    from app.core.auth_service import auth_service
    from app.core.security import verify_api_key, verify_session_token_with_role

    token = request.cookies.get("agency_session")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            
    if token:
        if verify_api_key(token):
            return {"username": "api_client", "role": "admin"}
        info = verify_session_token_with_role(token)
        if info and not auth_service.is_session_revoked(info["username"], token):
            return info

    raise HTTPException(status_code=401, detail="Authentication required. Please log in.")

def require_auth(request: Request) -> str:
    user_info = get_current_user_info(request)
    return user_info["username"]

# --- Authentication Endpoints ---
class LoginRequest(BaseModel):
    username: str
    password: str

class SetupRequest(BaseModel):
    username: Optional[str] = "admin"
    password: str
    confirm_password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

class ForgotPasswordRequest(BaseModel):
    username: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str


@router.get("/api/auth/status")
async def auth_status(request: Request, db: AsyncSession = Depends(get_db)):
    from app.core.auth_service import auth_service
    from app.core.security import verify_api_key, verify_session_token_with_role

    try:
        setup_req = await auth_service.is_setup_required(db)
    except Exception as e:
        logger.error(f"[AuthStatus] Failed to query setup status from database: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Database unavailable. Cannot determine setup state.",
                "setup_required": False,
                "authenticated": False,
                "auth_enabled": settings.AUTH_ENABLED,
                "status": "ERROR"
            }
        )

    authenticated = False
    username = None
    role = None

    if not setup_req:
        token = request.cookies.get("agency_session")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()

        if token:
            if verify_api_key(token):
                authenticated = True
                username = "api_client"
                role = "admin"
            else:
                info = verify_session_token_with_role(token)
                if info and not auth_service.is_session_revoked(info["username"], token):
                    authenticated = True
                    username = info.get("username")
                    role = info.get("role")

    return {
        "setup_required": setup_req,
        "authenticated": authenticated,
        "username": username,
        "role": role,
        "auth_enabled": settings.AUTH_ENABLED,
        "status": "SETUP_REQUIRED" if setup_req else "READY"
    }

@router.post("/api/auth/setup")
async def setup_admin(req: SetupRequest, response: Response, db: AsyncSession = Depends(get_db)):
    from app.core.auth_service import auth_service
    try:
        setup_needed = await auth_service.is_setup_required(db)
    except Exception as e:
        logger.error(f"[AuthSetup] Database error checking setup status: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable.")

    if not setup_needed:
        raise HTTPException(status_code=400, detail="Initial setup has already been completed.")

    try:
        user = await auth_service.complete_setup(
            session=db,
            username=req.username or "admin",
            password=req.password,
            confirm_password=req.confirm_password
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    token = create_session_token(user.username, role=user.role)
    response.set_cookie(
        key="agency_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.SESSION_MAX_AGE_DAYS * 86400,
        secure=not settings.DEBUG
    )
    return {
        "status": "SUCCESS",
        "message": "Administrator account configured successfully.",
        "username": user.username,
        "role": user.role,
        "token": token
    }

@router.post("/api/auth/change-password")
async def change_password(
    req: ChangePasswordRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    from app.core.auth_service import auth_service
    user_info = get_current_user_info(request)
    username = user_info.get("username", "")
    role = user_info.get("role", "")

    if role == "viewer":
        raise HTTPException(status_code=403, detail="Forbidden: Viewers cannot modify administrator credentials.")

    try:
        await auth_service.change_user_password(
            session=db,
            username=username,
            current_password=req.current_password,
            new_password=req.new_password,
            confirm_password=req.confirm_password
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    # Invalidate session cookie
    response.delete_cookie("agency_session")
    return {
        "status": "SUCCESS",
        "message": "Password updated successfully. Existing sessions have been invalidated. Please log in again."
    }

@router.post("/api/auth/login")
async def login(req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    from app.core.auth_service import auth_service

    # 1. Try database user first
    user = await auth_service.verify_user(db, req.username, req.password)
    role = "admin"
    if user:
        role = user.role
        username = user.username
    elif verify_login_credentials(req.username, req.password):
        from app.core.security import get_user_role
        role = get_user_role(req.username.strip())
        username = req.username.strip()
    else:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_session_token(username, role=role)
    response.set_cookie(
        key="agency_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.SESSION_MAX_AGE_DAYS * 86400,
        secure=not settings.DEBUG
    )
    return {"status": "SUCCESS", "username": username, "role": role, "token": token}

@router.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("agency_session")
    return {"status": "SUCCESS", "message": "Logged out successfully"}

@router.post("/api/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    from app.core.auth_service import auth_service
    clean_username = req.username.strip()
    if not clean_username:
        raise HTTPException(status_code=400, detail="Username or email is required.")

    result = await auth_service.create_password_reset_token(db, clean_username)
    if result:
        raw_token, _ = result
        return {
            "status": "SUCCESS",
            "message": "Password reset token generated. Valid for 15 minutes.",
            "reset_token": raw_token,
            "reset_url": f"/reset-password?token={raw_token}"
        }
    return {
        "status": "SUCCESS",
        "message": "If an account matches that username or email, a reset link has been generated."
    }

@router.post("/api/auth/reset-password")
async def reset_password(req: ResetPasswordRequest, response: Response, db: AsyncSession = Depends(get_db)):
    from app.core.auth_service import auth_service
    try:
        user = await auth_service.verify_and_use_reset_token(
            session=db,
            raw_token=req.token,
            new_password=req.new_password,
            confirm_password=req.confirm_password
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    response.delete_cookie("agency_session")
    return {
        "status": "SUCCESS",
        "message": "Password reset successfully. Please log in with your new credentials.",
        "username": user.username
    }


@router.get("/api/auth/me")
async def auth_me(request: Request):
    if not settings.AUTH_ENABLED:
        return {"authenticated": True, "auth_enabled": False, "username": "admin", "role": "admin"}
    
    token = request.cookies.get("agency_session")
    auth_header = request.headers.get("Authorization", "")
    if not token and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        
    user_info = None
    if token:
        from app.core.security import verify_api_key, verify_session_token_with_role
        from app.core.auth_service import auth_service
        if verify_api_key(token):
            user_info = {"username": "api_client", "role": "admin"}
        else:
            info = verify_session_token_with_role(token)
            if info and not auth_service.is_session_revoked(info["username"], token):
                user_info = info

    return {
        "authenticated": bool(user_info),
        "auth_enabled": True,
        "username": user_info.get("username") if user_info else None,
        "role": user_info.get("role") if user_info else None
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
        service_name = None
        target_price = None
        if b.client_intelligence and b.client_intelligence.top_service_name:
            service_name = b.client_intelligence.top_service_name
            target_price = float(b.client_intelligence.recommended_price_usd) if b.client_intelligence.recommended_price_usd else None
        elif b.offers and len(b.offers) > 0:
            service_name = b.offers[0].title or b.offers[0].service_type
            target_price = float(b.offers[0].recommended_price) if b.offers[0].recommended_price else None

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
            "research_status": getattr(b, "research_status", "RESEARCH_REQUIRED"),
            "pipeline_stage": b.pipeline_stage,
            "evidence_count": getattr(b, "evidence_count", 0) or 0,
            "effective_evidence_score": float(getattr(b, "effective_evidence_score", 0.0) or 0.0),
            "prospect_score": float(getattr(b, "prospect_score", 0.0)) if getattr(b, "prospect_score", None) is not None else None,
            "recommended_service": service_name,
            "target_offer": target_price,
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

    res = {
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
            "research_status": getattr(b, "research_status", "RESEARCH_REQUIRED"),
            "pipeline_stage": b.pipeline_stage,
            "evidence_count": getattr(b, "evidence_count", 0) or 0,
            "effective_evidence_score": float(getattr(b, "effective_evidence_score", 0.0) or 0.0),
            "evidence_confidence": float(getattr(b, "evidence_confidence", 0.0) or 0.0),
            "prospect_score": float(getattr(b, "prospect_score", 0.0)) if getattr(b, "prospect_score", None) is not None else None
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

    # Fetch empirical evidence items
    ev_q = select(ProspectEvidence).where(ProspectEvidence.business_id == lead_id).order_by(ProspectEvidence.source_tier.asc(), desc(ProspectEvidence.confidence_score))
    ev_items = (await db.execute(ev_q)).scalars().all()
    res["evidence_items"] = [
        {
            "id": ev.id,
            "evidence_id": ev.evidence_id,
            "claim": ev.claim,
            "source_url": ev.source_url,
            "source_domain": ev.source_domain,
            "source_type": ev.source_type,
            "source_tier": ev.source_tier,
            "publisher": ev.publisher,
            "raw_excerpt": ev.raw_excerpt,
            "evidence_category": ev.evidence_category,
            "confidence_score": ev.confidence_score,
            "source_quality_score": ev.source_quality_score,
            "freshness_score": ev.freshness_score,
            "is_verified": ev.is_verified,
            "http_status": getattr(ev, "http_status", 200),
            "content_hash": getattr(ev, "content_hash", None),
            "verification_status": getattr(ev, "verification_status", "VERIFIED" if ev.is_verified else "UNVERIFIED"),
            "verification_reason": getattr(ev, "verification_reason", None),
            "business_identity_match": getattr(ev, "business_identity_match", False),
            "source_independence_group": getattr(ev, "source_independence_group", ev.source_domain),
            "created_at": ev.created_at.isoformat() if ev.created_at else None
        }
        for ev in ev_items
    ]

    # Fetch persisted Client Intelligence
    intel_q = select(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == lead_id)
    intel_rec = (await db.execute(intel_q)).scalars().first()
    if intel_rec:
        res["client_intelligence"] = {
            "segment": intel_rec.segment,
            "top_service_id": intel_rec.top_service_id,
            "top_service_name": intel_rec.top_service_name,
            "fit_score": intel_rec.fit_score,
            "selection_score": intel_rec.selection_score,
            "recommended_price_usd": float(intel_rec.recommended_price_usd) if intel_rec.recommended_price_usd else None,
            "target_price_usd": float(intel_rec.target_price_usd) if intel_rec.target_price_usd else None,
            "pain_points": intel_rec.pain_points,
            "service_matches": intel_rec.service_matches,
            "roi_estimate": intel_rec.roi_estimate,
            "why_this_business": intel_rec.why_this_business,
            "decision_trace": intel_rec.decision_trace
        }
    else:
        res["client_intelligence"] = None

    # Fetch Real Empirical Pipeline Events Timeline
    events_q = select(PipelineEvent).where(PipelineEvent.business_id == lead_id).order_by(PipelineEvent.created_at.asc())
    events = (await db.execute(events_q)).scalars().all()
    res["timeline"] = [
        {
            "id": ev.id,
            "from_stage": ev.from_stage,
            "to_stage": ev.to_stage,
            "deal_value": float(ev.deal_value) if ev.deal_value else 0.0,
            "note": ev.note,
            "created_at": ev.created_at.isoformat() if ev.created_at else None
        }
        for ev in events
    ]

    # Fetch latest ModelPrediction if available
    pred_q = (
        select(ModelPrediction)
        .where(ModelPrediction.entity_id == lead_id, ModelPrediction.entity_type == "business")
        .order_by(desc(ModelPrediction.id))
    )
    latest_pred = (await db.execute(pred_q)).scalars().first()
    if latest_pred:
        res["ml_intelligence"] = {
            "prediction_id": latest_pred.prediction_id,
            "model_name": latest_pred.model_name,
            "model_version": latest_pred.model_version,
            "predicted_score": latest_pred.predicted_value,
            "probability_win": latest_pred.confidence_score,
            "is_baseline": latest_pred.is_baseline,
            "model_status": latest_pred.metadata_json.get("model_status", "BASELINE" if latest_pred.is_baseline else "TRAINED_MODEL"),
            "expected_revenue_usd": latest_pred.metadata_json.get("expected_revenue_usd"),
            "commercial_tier": latest_pred.metadata_json.get("commercial_tier"),
            "drivers": latest_pred.metadata_json.get("drivers", []),
            "rationale": latest_pred.metadata_json.get("rationale", "")
        }
    else:
        # Compute baseline preview
        try:
            feats = feature_store.extract_features(business=b, audit=audit)
            base_pred = baseline_scorer.predict(feats)
            rev_pred = expected_revenue_model.evaluate_deal_potential(
                probability_win=base_pred["probability_of_conversion"],
                proposed_price_usd=feats.get("niche_avg_deal_size", 750.0),
                niche_avg_deal_size=feats.get("niche_avg_deal_size", 750.0),
                data_source="BASELINE"
            )
            res["ml_intelligence"] = {
                "prediction_id": None,
                "model_name": "lead_scoring_baseline",
                "model_version": baseline_scorer.VERSION_TAG,
                "predicted_score": base_pred["total_score"],
                "probability_win": base_pred["probability_of_conversion"],
                "is_baseline": True,
                "model_status": "BASELINE",
                "expected_revenue_usd": rev_pred["expected_revenue_usd"],
                "commercial_tier": rev_pred["commercial_tier"],
                "drivers": base_pred["explainability"]["drivers"],
                "rationale": base_pred["explainability"]["rationale"]
            }
        except Exception:
            res["ml_intelligence"] = None

    return res

# --- ML Decision Layer Endpoints ---
@router.get("/api/ml/status", dependencies=[Depends(require_auth)])
async def get_ml_status(db: AsyncSession = Depends(get_db)):
    active_model_name = "lead_scoring_model"
    active_ml = model_runner.active_models.get(active_model_name)
    if active_ml is not None:
        model_mode = "TRAINED_MODEL"
        version_tag = getattr(active_ml, "version_tag", "v2.0.0-sklearn")
    else:
        model_mode = "BASELINE"
        version_tag = baseline_scorer.VERSION_TAG

    return {
        "status": "OPERATIONAL",
        "model_mode": model_mode,
        "active_model": active_model_name,
        "version_tag": version_tag,
        "schema_version": model_runner.SCHEMA_VERSION,
        "features_count": len(FEATURE_NAMES),
        "features": FEATURE_NAMES,
        "commercial_floor_usd": 500.0,
        "safety_gates": {
            "kill_switch_active": not settings.AUTONOMOUS_AGENT_ENABLED,
            "email_dry_run": settings.EMAIL_DRY_RUN,
            "voice_dry_run": settings.VOICE_DRY_RUN,
            "payment_dry_run": settings.PAYMENT_DRY_RUN
        }
    }

@router.post("/api/ml/predict/{lead_id}", dependencies=[Depends(require_auth)])
async def predict_lead_ml(lead_id: int, db: AsyncSession = Depends(get_db)):
    b = await db.get(Business, lead_id)
    if not b:
        raise HTTPException(status_code=404, detail="Lead not found")

    audit_q = select(AuditRun).where(AuditRun.business_id == lead_id).order_by(desc(AuditRun.audited_at))
    audit = (await db.execute(audit_q)).scalars().first()

    country_q = select(Country).where(Country.code == b.country) if b.country else None
    country = (await db.execute(country_q)).scalar_one_or_none() if country_q is not None else None

    niche_q = select(Niche).where(Niche.name == b.niche) if b.niche else None
    niche = (await db.execute(niche_q)).scalar_one_or_none() if niche_q is not None else None

    try:
        eval_result = await model_runner.score_and_evaluate_lead(
            session=db,
            business=b,
            audit=audit,
            country=country,
            niche=niche
        )
        await db.commit()
        return eval_result
    except Exception as e:
        from app.core.logging import logger
        logger.error(f"[API] ML evaluation failed for lead #{lead_id}: {e}")
        raise HTTPException(status_code=400, detail=f"ML evaluation failed: {str(e)}")

@router.get("/api/ml/prospects/ranked", dependencies=[Depends(require_auth)])
async def get_ranked_prospects(limit: int = 50, db: AsyncSession = Depends(get_db)):
    q = select(Business).where(
        Business.pipeline_stage.notin_([PipelineStage.LOST.value, PipelineStage.REJECTED.value])
    ).order_by(desc(Business.id)).limit(limit)
    businesses = (await db.execute(q)).scalars().all()

    prospect_items = []
    for b in businesses:
        audit_q = select(AuditRun).where(AuditRun.business_id == b.id).order_by(desc(AuditRun.audited_at))
        audit = (await db.execute(audit_q)).scalars().first()

        features = feature_store.extract_features(business=b, audit=audit)
        base_res = baseline_scorer.predict(features)
        rev_res = expected_revenue_model.evaluate_deal_potential(
            probability_win=base_res["probability_of_conversion"],
            proposed_price_usd=features.get("niche_avg_deal_size", 750.0),
            niche_avg_deal_size=features.get("niche_avg_deal_size", 750.0),
            data_source="BASELINE"
        )

        prospect_items.append({
            "business_id": b.id,
            "name": b.name,
            "domain": b.domain,
            "pipeline_stage": b.pipeline_stage,
            "expected_revenue": rev_res["expected_revenue_usd"],
            "lead_quality": base_res["quality_score"],
            "contactability": base_res["contactability_score"],
            "service_fit": features.get("service_fit_score", 70.0),
            "critical_findings_count": features.get("critical_findings_count", 0.0),
            "high_findings_count": features.get("high_findings_count", 0.0),
            "probability_win": base_res["probability_of_conversion"],
            "total_score": base_res["total_score"],
            "priority": base_res["priority"]
        })

    ranked = prospect_ranker.rank_prospects(prospect_items)
    return {"count": len(ranked), "ranked_prospects": ranked}

@router.post("/api/ml/train", dependencies=[Depends(require_auth)])
async def trigger_ml_training(db: AsyncSession = Depends(get_db)):
    try:
        result = await training_pipeline.run_training(db)
        return result
    except Exception as e:
        from app.core.logging import logger
        logger.error(f"[API] ML training trigger failed: {e}")
        raise HTTPException(status_code=500, detail=f"ML training pipeline failed: {str(e)}")

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
async def approve_outreach(message_id: int, auto_send: bool = True, force_live: bool = False, db: AsyncSession = Depends(get_db)):
    appr = await outreach_approval_queue.approve_message(db, message_id)
    send_result = None
    if auto_send:
        send_result = await outreach_sender_adapter.send_approved_message(db, message_id, force_live=force_live)
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

# --- Autonomous Revenue Agent Endpoints ---

class AgentStepRequest(BaseModel):
    name: str = "Apex Mechanical"
    domain: Optional[str] = "apexmechanical.com"
    email: Optional[str] = "service@apexmechanical.com"
    phone: Optional[str] = "+1-512-555-0188"
    estimated_value: float = 750.0
    buyer_score: float = 84.0
    opportunity_score: float = 78.0

@router.get("/api/agent/status")
async def get_agent_status():
    """Returns live status of the autonomous revenue agent."""
    from app.agents.revenue_agent import revenue_agent_orchestrator
    return revenue_agent_orchestrator.get_status()

@router.post("/api/agent/start")
async def start_agent():
    """Starts the autonomous revenue agent."""
    from app.agents.revenue_agent import revenue_agent_orchestrator
    return revenue_agent_orchestrator.start()

@router.post("/api/agent/pause")
async def pause_agent():
    """Pauses the autonomous revenue agent."""
    from app.agents.revenue_agent import revenue_agent_orchestrator
    return revenue_agent_orchestrator.pause()

@router.post("/api/agent/stop")
async def stop_agent():
    """Stops the autonomous revenue agent."""
    from app.agents.revenue_agent import revenue_agent_orchestrator
    return revenue_agent_orchestrator.stop()

@router.post("/api/agent/kill")
async def kill_agent():
    """Global emergency kill switch: immediately shuts down autonomous agent activities."""
    from app.agents.revenue_agent import revenue_agent_orchestrator
    return revenue_agent_orchestrator.trigger_kill_switch()

@router.post("/api/agent/step")
async def step_agent(req: AgentStepRequest):
    """Executes a single-prospect pass through the autonomous revenue loop."""
    from app.agents.revenue_agent import revenue_agent_orchestrator
    return await revenue_agent_orchestrator.step_single_prospect(req.model_dump())

# --- Production Voice-Sales Layer Endpoints ---

class VoiceCallRequest(BaseModel):
    phone: str
    business_name: str
    niche: str = "Commercial Services"
    city: str = "Austin"
    business_id: Optional[int] = None
    language: str = "en"

class VoiceTranscriptWebhookRequest(BaseModel):
    call_sid: str
    transcript: str
    duration_seconds: int = 0
    recording_url: Optional[str] = None

@router.get("/api/voice/config")
async def get_voice_config():
    """Returns active telephony provider configuration, caller ID, and safety gates."""
    return {
        "voice_provider": settings.VOICE_PROVIDER,
        "voice_dry_run": settings.VOICE_DRY_RUN,
        "caller_id": settings.VOICE_CALLER_ID,
        "recording_enabled": settings.VOICE_RECORDING_ENABLED,
        "consent_disclosure": settings.VOICE_CONSENT_DISCLOSURE,
        "has_twilio_credentials": bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN),
        "has_bland_credentials": bool(settings.BLAND_API_KEY)
    }

@router.post("/api/voice/call")
async def trigger_voice_call(req: VoiceCallRequest):
    """Initiates an outbound voice call to a qualified prospect."""
    from app.services.voice_service import VoiceSalesService
    return await VoiceSalesService.initiate_outbound_call(
        prospect_phone=req.phone,
        business_name=req.business_name,
        niche=req.niche,
        city=req.city,
        business_id=req.business_id,
        language=req.language
    )

@router.post("/api/voice/webhook/transcript")
async def voice_transcript_webhook(req: VoiceTranscriptWebhookRequest):
    """Processes incoming transcript callbacks from telephony providers to qualify and schedule."""
    from app.core.security import PromptInjectionGuard
    is_safe, threat = PromptInjectionGuard.scan_text(req.transcript)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Malicious transcript rejected: {threat}")

    from app.services.voice_service import VoiceSalesService
    return await VoiceSalesService.process_call_transcript(
        call_sid=req.call_sid,
        transcript=req.transcript,
        duration=req.duration_seconds,
        recording_url=req.recording_url
    )

@router.get("/api/voice/calls")
async def list_voice_calls(limit: int = 50):
    """Returns history of voice sales calls, transcripts, and outcomes."""
    from app.services.voice_service import VoiceSalesService
    return await VoiceSalesService.get_call_logs(limit=limit)

@router.get("/api/voice/meetings")
async def list_scheduled_meetings(limit: int = 50):
    """Returns booked meetings and consultations scheduled by the voice agent."""
    from app.services.voice_service import VoiceSalesService
    return await VoiceSalesService.get_meetings(limit=limit)

# --- Production Readiness, Health, & Controlled E2E Test Endpoints ---

@router.get("/api/production/health")
async def get_production_health():
    """Performs deep diagnostic health checks on database, email, voice, payments, and webhooks."""
    from app.services.health_service import ProductionHealthService
    return await ProductionHealthService.check_system_health()

class ActivationRequest(BaseModel):
    provider: str
    confirmation: str

class DeactivationRequest(BaseModel):
    provider: str
    reason: Optional[str] = "Manual operator deactivation"

@router.get("/api/production/activation-status")
async def get_production_activation_status(db: AsyncSession = Depends(get_db)):
    """Returns independent provider readiness, safety states, and blockers for production activation."""
    from app.infrastructure.production_activation import production_activation_manager
    panel = await production_activation_manager.get_readiness_panel(db)
    return panel.model_dump()

@router.post("/api/production/activate")
async def activate_production_provider(
    req: ActivationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Safely activates a provider into production mode with strict hard gates and confirmation phrase verification."""
    actor = "operator"
    if settings.AUTH_ENABLED:
        user_info = get_current_user_info(request)
        if user_info.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Privileged access required: Administrator credentials required.")
        actor = user_info.get("username", "admin")

    from app.infrastructure.production_activation import production_activation_manager
    client_ip = request.client.host if request.client else None
    try:
        res = await production_activation_manager.request_activation(
            provider=req.provider,
            actor=actor,
            confirmation_phrase=req.confirmation,
            db_session=db,
            ip_address=client_ip
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/production/deactivate")
async def deactivate_production_provider(
    req: DeactivationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Immediately restores dry-run safety gates for a provider."""
    actor = "operator"
    if settings.AUTH_ENABLED:
        user_info = get_current_user_info(request)
        if user_info.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Privileged access required: Administrator credentials required.")
        actor = user_info.get("username", "admin")

    from app.infrastructure.production_activation import production_activation_manager
    client_ip = request.client.host if request.client else None
    try:
        res = await production_activation_manager.request_deactivation(
            provider=req.provider,
            actor=actor,
            reason=req.reason or "Operator request",
            db_session=db,
            ip_address=client_ip
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/production/test/e2e")
async def run_controlled_e2e_test():
    """Executes a controlled, single-prospect end-to-end dry-run test across all 10 revenue stages."""
    from app.services.controlled_test_service import ControlledTestService
    return await ControlledTestService.run_controlled_e2e_test()

@router.get("/api/compliance/calling-hours")
async def check_calling_hours(country: str = "US", city: Optional[str] = None, phone: Optional[str] = None):
    """Verifies whether a prospective business is currently within permissible calling hours."""
    from app.compliance.calling_hours import calling_hours_compliance
    return calling_hours_compliance.is_calling_window_open(country=country, city=city, phone=phone)

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

    from app.core.security import webhook_replay_guard
    if sig_header:
        fresh = await webhook_replay_guard.record_and_verify(f"rzp:{sig_header}")
        if not fresh:
            return {"status": "DUPLICATE_IGNORED", "message": "Webhook event already processed."}

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("event", "")
    payload = event.get("payload", {})
    plink_entity = payload.get("payment_link", {}).get("entity", {})
    pmt_entity = payload.get("payment", {}).get("entity", {})

    raw_evt_id = event.get("id") or pmt_entity.get("id") or plink_entity.get("id") or (sig_header[:64] if sig_header else f"rzp_{datetime.utcnow().timestamp()}")
    event_id = str(raw_evt_id)

    # Database-level Idempotency Check
    existing_evt = (await db.execute(
        select(PaymentWebhookEvent).where(
            PaymentWebhookEvent.provider == "razorpay",
            PaymentWebhookEvent.event_id == event_id
        )
    )).scalars().first()
    if existing_evt and existing_evt.processing_status in ("PROCESSED", "DUPLICATE"):
        return {"status": "DUPLICATE_IGNORED", "message": "Webhook event already processed."}

    if not existing_evt:
        existing_evt = PaymentWebhookEvent(
            provider="razorpay",
            event_id=event_id,
            event_type=event_type,
            processing_status="PROCESSING",
            payload_json=sanitize_audit_payload(event)
        )
        db.add(existing_evt)
        try:
            await db.flush()
        except Exception:
            await db.rollback()
            return {"status": "DUPLICATE_IGNORED", "message": "Webhook event already processed."}

    # 1. Payment Link Paid Event
    if event_type == "payment_link.paid":
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
            existing_evt.processing_status = "PROCESSED"
            existing_evt.processed_at = datetime.utcnow()
            existing_evt.outcome = "SUCCESS"
            await AuditService.log_event(
                db=db,
                actor="webhook:razorpay",
                action="payment.webhook_processed",
                entity_type="payment",
                entity_id=event_id,
                reason=f"Processed {event_type} for business {biz_id}",
                result="SUCCESS",
                details={"event_type": event_type, "business_id": biz_id, "amount_usd": amount_usd}
            )
            return {"status": "SUCCESS", "event": event_type, "business_id": biz_id}

    # 2. Payment Captured / Order Paid Event
    elif event_type in ("payment.captured", "order.paid"):
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
            existing_evt.processing_status = "PROCESSED"
            existing_evt.processed_at = datetime.utcnow()
            existing_evt.outcome = "SUCCESS"
            await AuditService.log_event(
                db=db,
                actor="webhook:razorpay",
                action="payment.webhook_processed",
                entity_type="payment",
                entity_id=event_id,
                reason=f"Processed {event_type} for business {biz_id}",
                result="SUCCESS",
                details={"event_type": event_type, "business_id": biz_id, "amount_usd": amount_usd}
            )
            return {"status": "SUCCESS", "event": event_type, "business_id": biz_id}

    # Check if this event belongs to a commercial proposal/deal
    prop_id = None
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
            existing_evt.processing_status = "PROCESSED"
            existing_evt.processed_at = datetime.utcnow()
            existing_evt.outcome = "SUCCESS"
            return deal_res
        except Exception as de:
            logger.warning(f"[Razorpay Webhook] Deal closing service check: {de}")

    existing_evt.processing_status = "PROCESSED"
    existing_evt.processed_at = datetime.utcnow()
    existing_evt.outcome = "ACKNOWLEDGED"
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

@router.get("/api/proposals")
async def list_proposals_endpoint(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user_info: Dict[str, str] = Depends(get_current_user_info)
):
    stmt = (
        select(Proposal, Business.name.label("business_name"))
        .outerjoin(Business, Proposal.business_id == Business.id)
        .order_by(desc(Proposal.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    proposals = []
    for prop, biz_name in rows:
        proposals.append({
            "id": prop.id,
            "business_id": prop.business_id,
            "business_name": biz_name or f"Business #{prop.business_id}",
            "title": prop.title,
            "total_value": prop.total_value,
            "advance_required": prop.advance_required,
            "advance_received": prop.advance_received,
            "remaining_balance": prop.remaining_balance,
            "status": prop.status,
            "delivery_status": prop.delivery_status,
            "service_type": prop.service_type,
            "created_at": prop.created_at.isoformat() if prop.created_at else None,
            "approved_at": prop.approved_at.isoformat() if prop.approved_at else None,
            "approved_by": prop.approved_by
        })
    return {"proposals": proposals, "count": len(proposals)}

@router.get("/api/owner/attention")
async def get_owner_attention_endpoint(
    db: AsyncSession = Depends(get_db),
    user_info: Dict[str, str] = Depends(get_current_user_info)
):
    """
    Owner Attention Feed:
    Scans agency operations for events requiring human owner intervention:
    1. Pending Outreach Approvals (AI messages staged for human approval)
    2. Unhandled Inbound Replies (Prospect objections, meeting requests, inquiries)
    3. Failed or Disputed Payments (Payment provider exceptions requiring investigation)
    """
    items = []
    
    # 1. Pending Outreach Approvals
    pending_outreach_count = await db.scalar(
        select(func.count()).select_from(OutreachMessage).where(OutreachMessage.status == OutreachStatus.PENDING_APPROVAL.value)
    ) or 0
    if pending_outreach_count > 0:
        items.append({
            "id": "pending_outreach",
            "type": "OUTREACH_APPROVAL",
            "severity": "WARNING",
            "title": f"{pending_outreach_count} Outreach Message{'s' if pending_outreach_count > 1 else ''} Pending Approval",
            "description": "Commercial outreach generated by AI requires human operator sign-off before dispatch.",
            "action_view": "outreach",
            "action_label": "Review Queue",
            "count": pending_outreach_count
        })

    # 2. Unhandled Inbound Replies
    unhandled_replies_count = await db.scalar(
        select(func.count()).select_from(Reply).where(Reply.is_handled == False)
    ) or 0
    if unhandled_replies_count > 0:
        items.append({
            "id": "unhandled_replies",
            "type": "INBOUND_REPLY",
            "severity": "WARNING",
            "title": f"{unhandled_replies_count} Inbound Repl{'ies' if unhandled_replies_count > 1 else 'y'} Awaiting Action",
            "description": "Prospects have responded with inquiries, objections, or meeting requests needing response.",
            "action_view": "sales",
            "action_label": "Handle Replies",
            "count": unhandled_replies_count
        })

    # 3. Failed Payments
    failed_payments_count = await db.scalar(
        select(func.count()).select_from(Payment).where(Payment.status.in_(["FAILED", "DISPUTED"]))
    ) or 0
    if failed_payments_count > 0:
        items.append({
            "id": "failed_payments",
            "type": "PAYMENT_ISSUE",
            "severity": "CRITICAL",
            "title": f"{failed_payments_count} Payment Exception{'s' if failed_payments_count > 1 else ''}",
            "description": "Transactions flagged as failed or disputed require billing inspection.",
            "action_view": "clients",
            "action_label": "Inspect Billing",
            "count": failed_payments_count
        })

    total_count = sum(item["count"] for item in items)
    return {
        "items": items,
        "count": total_count,
        "status": "ATTENTION_REQUIRED" if total_count > 0 else "ALL_CLEAR",
        "message": "All systems operating nominally. Nothing needs your attention." if total_count == 0 else f"{total_count} operational item{'s' if total_count > 1 else ''} require owner intervention."
    }

@router.get("/api/client/portal-data")
async def get_client_portal_data_endpoint(
    db: AsyncSession = Depends(get_db),
    user_info: Dict[str, str] = Depends(get_current_user_info)
):
    """
    Tenant-Isolated Client Portal Data:
    Returns exclusively the authenticated client's project, milestones,
    tasks, deliverables, and payment status.
    Client CANNOT see agency-wide metrics, internal logs, pipelines, or other clients.
    """
    username = user_info.get("username", "")
    
    # 1. Fetch user record
    user_res = await db.execute(select(User).where(User.username == username))
    user = user_res.scalar_one_or_none()

    customer = None
    if user and user.customer_id:
        cust_res = await db.execute(select(Customer).where(Customer.id == user.customer_id))
        customer = cust_res.scalar_one_or_none()

    if not customer and username:
        # Fallback to matching contact_email
        cust_res = await db.execute(select(Customer).where(Customer.contact_email == username))
        customer = cust_res.scalar_one_or_none()

    # If no customer is linked, return safe minimal unlinked client payload
    if not customer:
        return {
            "has_account": False,
            "client_name": username,
            "company_name": "Valued Client",
            "contact_email": username,
            "onboarding_status": "PENDING_ONBOARDING",
            "contract_amount": 0.0,
            "active_project": None,
            "projects": [],
            "deliverables": [],
            "tasks": [],
            "payments": [],
            "support_email": getattr(settings, "SUPPORT_EMAIL", "support@agency.internal"),
            "agency_name": settings.APP_NAME
        }

    # Fetch projects strictly isolated by customer_id
    proj_res = await db.execute(
        select(Project).where(Project.customer_id == customer.id).order_by(desc(Project.created_at))
    )
    projects = proj_res.scalars().all()

    # Fetch payments strictly isolated by customer_id
    pay_res = await db.execute(
        select(Payment).where(Payment.customer_id == customer.id).order_by(desc(Payment.created_at))
    )
    payments = pay_res.scalars().all()

    active_proj = projects[0] if projects else None

    project_list = []
    deliverables = []
    tasks = []

    for p in projects:
        project_list.append({
            "id": p.id,
            "title": p.title,
            "service_type": p.service_type,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
        })
        if p.audit_report_path:
            deliverables.append({
                "title": "Technical Performance & UX Audit Report",
                "type": "AUDIT_REPORT",
                "status": "DELIVERED" if p.status == "COMPLETED" else "IN_PROGRESS",
                "project_id": p.id
            })
        if p.tasks:
            for t in p.tasks:
                tasks.append({
                    "task": t.get("name") or t.get("task", "Implementation Milestone"),
                    "status": t.get("status", "IN_PROGRESS"),
                    "category": t.get("category", "Engineering"),
                    "completed": t.get("completed", False)
                })

    payment_list = []
    for pay in payments:
        payment_list.append({
            "id": pay.id,
            "amount": pay.amount,
            "currency": pay.currency,
            "status": pay.status,
            "payment_type": pay.payment_type,
            "created_at": pay.created_at.isoformat() if pay.created_at else None,
            "paid_at": pay.paid_at.isoformat() if pay.paid_at else None,
            "is_mock": pay.is_mock
        })

    return {
        "has_account": True,
        "client_name": username,
        "company_name": customer.company_name,
        "contact_email": customer.contact_email,
        "onboarding_status": customer.onboarding_status,
        "contract_amount": customer.contract_amount,
        "active_project": {
            "id": active_proj.id,
            "title": active_proj.title,
            "service_type": active_proj.service_type,
            "status": active_proj.status,
            "created_at": active_proj.created_at.isoformat() if active_proj.created_at else None,
        } if active_proj else None,
        "projects": project_list,
        "deliverables": deliverables,
        "tasks": tasks,
        "payments": payment_list,
        "support_email": getattr(settings, "SUPPORT_EMAIL", "support@agency.internal"),
        "agency_name": settings.APP_NAME
    }

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

class SendProposalClientRequest(BaseModel):
    send_live: Optional[bool] = False
    custom_message: Optional[str] = None

@router.post("/api/proposals/{proposal_id}/send-to-client")
async def send_proposal_to_client(
    proposal_id: int,
    req: SendProposalClientRequest = SendProposalClientRequest(),
    db: AsyncSession = Depends(get_db)
):
    """
    Owner Authorization Gate:
    Validates proposal >= $500, generates checkout payment link,
    and dispatches commercial proposal with payment link to client.
    """
    prop = await db.get(Proposal, proposal_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if prop.total_value < getattr(settings, "COMMERCIAL_FLOOR_USD", 500.0):
        raise HTTPException(status_code=400, detail="Proposal total value is below $500 commercial floor")

    biz = await db.get(Business, prop.business_id)
    if not biz or not biz.public_email:
        raise HTTPException(status_code=400, detail="Target business has no verified contact email")

    if prop.status == "DRAFT":
        await deal_closing_service.approve_proposal(db, prop.id, operator="owner")

    order_res = await deal_closing_service.request_payment_order(
        session=db,
        proposal_id=prop.id,
        payment_type="ADVANCE"
    )
    checkout_url = order_res.get("checkout_url", "")

    subj = f"Official Project Proposal & Scope: {prop.title} ({biz.domain})"
    body = req.custom_message or (
        f"Dear {biz.name} Team,\n\n"
        f"Following our recent communication, here is our formal commercial proposal for {biz.domain}.\n\n"
        f"• Scope: {prop.title}\n"
        f"• Total Investment: ${prop.total_value:,.2f} USD\n"
        f"• Initial Deposit: ${prop.advance_required:,.2f} USD\n\n"
        f"You can review the scope and complete your project reservation deposit directly via our secure payment link:\n"
        f"{checkout_url}\n\n"
        f"Upon receipt of your deposit, our technical team initiates immediate delivery and diagnostic onboarding.\n\n"
        f"Best regards,\n"
        f"{settings.OUTREACH_FROM_NAME}"
    )

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email=biz.public_email,
        subject=subj,
        body=body,
        variant_name="Commercial Proposal & Payment Link",
        status=OutreachStatus.APPROVED.value,
        confidence=1.0
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    send_res = await outreach_sender_adapter.send_approved_message(
        session=db,
        message_id=msg.id,
        force_live=req.send_live or False
    )

    biz.pipeline_stage = PipelineStage.PROPOSAL.value
    await db.commit()

    return {
        "status": "SENT",
        "proposal_id": prop.id,
        "recipient": biz.public_email,
        "checkout_url": checkout_url,
        "send_result": send_res
    }

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

    from app.core.security import webhook_replay_guard
    if sig_header:
        fresh = await webhook_replay_guard.record_and_verify(f"stripe:{sig_header}")
        if not fresh:
            return {"status": "DUPLICATE_IGNORED", "message": "Webhook event already processed."}

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("type", "")
    data_obj = event.get("data", {}).get("object", {})

    raw_evt_id = event.get("id") or data_obj.get("id") or (sig_header[:64] if sig_header else f"stripe_{datetime.utcnow().timestamp()}")
    event_id = str(raw_evt_id)

    # Database-level Idempotency Check
    existing_evt = (await db.execute(
        select(PaymentWebhookEvent).where(
            PaymentWebhookEvent.provider == "stripe",
            PaymentWebhookEvent.event_id == event_id
        )
    )).scalars().first()
    if existing_evt and existing_evt.processing_status in ("PROCESSED", "DUPLICATE"):
        return {"status": "DUPLICATE_IGNORED", "message": "Webhook event already processed."}

    if not existing_evt:
        existing_evt = PaymentWebhookEvent(
            provider="stripe",
            event_id=event_id,
            event_type=event_type,
            processing_status="PROCESSING",
            payload_json=sanitize_audit_payload(event)
        )
        db.add(existing_evt)
        try:
            await db.flush()
        except Exception:
            await db.rollback()
            return {"status": "DUPLICATE_IGNORED", "message": "Webhook event already processed."}

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
            existing_evt.processing_status = "PROCESSED"
            existing_evt.processed_at = datetime.utcnow()
            existing_evt.outcome = "SUCCESS"
            await AuditService.log_event(
                db=db,
                actor="webhook:stripe",
                action="payment.webhook_processed",
                entity_type="payment",
                entity_id=event_id,
                reason=f"Processed {event_type} for business {biz_id}",
                result="SUCCESS",
                details={"event_type": event_type, "business_id": biz_id, "amount_usd": amount_usd}
            )
            return {"status": "SUCCESS", "event": event_type, "business_id": biz_id}

    existing_evt.processing_status = "PROCESSED"
    existing_evt.processed_at = datetime.utcnow()
    existing_evt.outcome = "ACKNOWLEDGED"
    return {"status": "ACKNOWLEDGED", "event": event_type}

# --- Inbound Email & Reply Webhooks ---

class InboundEmailWebhook(BaseModel):
    sender_email: str
    subject: str = ""
    body: str

@router.post("/api/webhooks/inbound-email")
async def inbound_email_webhook(data: InboundEmailWebhook, db: AsyncSession = Depends(get_db)):
    from app.core.security import PromptInjectionGuard
    is_safe, threat = PromptInjectionGuard.scan_text(f"{data.subject} {data.body}")
    if not is_safe:
        return {"status": "FLAGGED", "message": "Inbound message flagged for prompt injection and routed to human review."}

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


# --- Real-Time Agent Observability & Artifacts Endpoints ---

@router.websocket("/ws/agent-activity")
async def agent_activity_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    Live WebSocket feed delivering real-time agent activity events to connected dashboards.
    Protected when settings.AUTH_ENABLED is True.
    """
    from app.agents.activity_broadcaster import activity_broadcaster
    from app.core.security import verify_session_token_with_role, verify_api_key

    if getattr(settings, "AUTH_ENABLED", False):
        cookie_token = websocket.cookies.get("agency_session")
        auth_header = websocket.headers.get("authorization", "")
        header_token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else None
        target_token = token or cookie_token or header_token

        is_authed = False
        if target_token:
            if verify_api_key(target_token) or verify_session_token_with_role(target_token):
                is_authed = True

        if not is_authed:
            # Reject unauthenticated WebSocket connection with policy violation
            await websocket.close(code=1008, reason="Authentication required")
            return

    await websocket.accept()
    await activity_broadcaster.register(websocket)
    try:
        while True:
            # Keep connection open; listen for heartbeat or client pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        await activity_broadcaster.unregister(websocket)
    except Exception as e:
        await activity_broadcaster.unregister(websocket)


@router.get("/api/agent/activity")
async def get_agent_activity(
    limit: int = Query(100, ge=1, le=500),
    run_id: Optional[str] = None,
    since_seq: Optional[int] = None,
    business_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Returns chronologically ordered recent activity events for hydration and historical inspection."""
    from app.agents.activity_broadcaster import activity_broadcaster
    events = await activity_broadcaster.get_recent_events(
        session=db,
        limit=limit,
        run_id=run_id,
        since_seq=since_seq,
        business_id=business_id
    )
    return {
        "status": "SUCCESS",
        "count": len(events),
        "events": events
    }


@router.get("/api/agent/outreach/{message_id}")
async def get_outreach_details(
    message_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Inspects the exact generated outreach message with grounding evidence and dry-run flag."""
    from app.core.security import validate_safe_id
    clean_msg_id = validate_safe_id(message_id, "message_id")
    msg = await db.get(OutreachMessage, clean_msg_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Outreach message not found")

    biz = await db.get(Business, msg.business_id) if msg.business_id else None

    # Load associated audit and offer
    audit_data = {}
    offer_data = {}
    if biz:
        audit_q = select(AuditRun).where(AuditRun.business_id == biz.id).order_by(desc(AuditRun.audited_at)).limit(1)
        audit_res = await db.execute(audit_q)
        audit = audit_res.scalar_one_or_none()
        if audit:
            metrics = audit.metrics if audit and audit.metrics else {}
            load_time = metrics.get("load_time_seconds") or metrics.get("load_time") or 3.2
            audit_data = {
                "performance_score": audit.performance_score,
                "load_time_seconds": load_time,
                "seo_score": audit.seo_score,
                "a11y_score": audit.a11y_score,
                "findings": [getattr(f, "finding", "Diagnostic finding") for f in (audit.findings or [])]
            }

        offer_q = select(Offer).where(Offer.business_id == biz.id).order_by(desc(Offer.created_at)).limit(1)
        offer_res = await db.execute(offer_q)
        off = offer_res.scalar_one_or_none()
        if off:
            offer_data = {
                "title": off.title,
                "price": off.recommended_price,
                "deliverables": off.deliverables or []
            }

    return {
        "id": msg.id,
        "business_id": msg.business_id,
        "domain": biz.domain if biz else "unknown",
        "business_name": biz.name if biz else "Unknown Business",
        "channel": getattr(msg, "channel", "EMAIL"),
        "status": msg.status,
        "variant": msg.variant_name,
        "subject": msg.subject,
        "body": msg.body,
        "recipient_email": msg.recipient_email,
        "from_email": settings.EMAIL_FROM,
        "from_name": settings.OUTREACH_FROM_NAME,
        "dry_run": settings.EMAIL_DRY_RUN,
        "simulation_notice": "SIMULATED — NO EXTERNAL TRANSMISSION (DRY RUN)",
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
        "offer": offer_data,
        "audit_grounding": audit_data,
        "grounding_evidence": {
            "audit": audit_data,
            "offer": offer_data
        }
    }


@router.get("/api/agent/audit-evidence/{business_id}")
async def get_audit_evidence_details(
    business_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Inspects deep audit findings and diagnostic vectors for a business."""
    from app.core.security import validate_safe_id
    clean_biz_id = validate_safe_id(business_id, "business_id")
    biz = await db.get(Business, clean_biz_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    audit_q = select(AuditRun).where(AuditRun.business_id == clean_biz_id).order_by(desc(AuditRun.audited_at)).limit(1)
    audit_res = await db.execute(audit_q)
    audit = audit_res.scalar_one_or_none()

    findings_list = []
    if audit and audit.findings:
        for f in audit.findings:
            findings_list.append({
                "category": f.category,
                "title": getattr(f, "finding", "Diagnostic finding"),
                "description": getattr(f, "recommended_fix", "") or getattr(f, "evidence", ""),
                "severity": f.severity,
                "impact_score": getattr(f, "confidence", 0.9)
            })

    metrics = audit.metrics if audit and audit.metrics else {}
    load_time = metrics.get("load_time_seconds") or metrics.get("load_time") or 3.2
    cwv_lcp = metrics.get("cwv_lcp") or metrics.get("lcp") or "2.4s"
    cwv_fid = metrics.get("cwv_fid") or metrics.get("fid") or "18ms"
    cwv_cls = metrics.get("cwv_cls") or metrics.get("cls") or "0.04"

    return {
        "business_id": biz.id,
        "domain": biz.domain,
        "business_name": biz.name,
        "niche": biz.niche,
        "city": biz.city,
        "audit_run_id": audit.id if audit else None,
        "performance_score": audit.performance_score if audit else None,
        "load_time_seconds": load_time if audit else None,
        "seo_score": audit.seo_score if audit else None,
        "a11y_score": audit.a11y_score if audit else None,
        "cwv_lcp": cwv_lcp if audit else None,
        "cwv_fid": cwv_fid if audit else None,
        "cwv_cls": cwv_cls if audit else None,
        "core_web_vitals": {
            "lcp_seconds": cwv_lcp if audit else "2.4s",
            "fid_ms": cwv_fid if audit else "18ms",
            "cls": cwv_cls if audit else "0.04"
        },
        "findings": findings_list,
        "created_at": audit.audited_at.isoformat() if audit and audit.audited_at else None
    }


@router.get("/api/agent/safety-guardrails")
async def get_safety_guardrails():
    """Returns live backend safety guardrails, dry-run flags, and commercial floors."""
    from app.agents.revenue_agent import revenue_agent_orchestrator
    status = revenue_agent_orchestrator.get_status()
    return status.get("safety_guardrails", {})


@router.get("/api/agent/prospect-memory/{domain_or_id}")
async def get_prospect_memory_details(
    domain_or_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieves full persistent memory snapshot and conversation history for a prospect."""
    from app.crm.memory_service import memory_service
    from app.core.security import validate_safe_id, validate_safe_domain

    if str(domain_or_id).isdigit():
        clean_id = validate_safe_id(domain_or_id)
        mem = await memory_service.get_memory(db, business_id=clean_id)
    else:
        clean_domain = validate_safe_domain(domain_or_id)
        mem = await memory_service.get_memory(db, domain=clean_domain)

    if not mem:
        raise HTTPException(status_code=404, detail="Prospect memory not found")

    biz = await db.get(Business, mem.business_id) if mem.business_id else None

    return {
        "id": mem.id,
        "business_id": mem.business_id,
        "business_name": biz.name if biz else "N/A",
        "domain": mem.domain,
        "contact_name": mem.contact_name or (biz.name if biz else "Primary Contact"),
        "contact_email": mem.contact_email or (biz.public_email if biz else "N/A"),
        "contact_phone": mem.contact_phone or (biz.phone if biz else "N/A"),
        "thread_id": mem.thread_id,
        "channel_used": mem.channel_used,
        "pipeline_stage": mem.pipeline_stage,
        "buyer_score": mem.buyer_score,
        "opportunity_score": mem.opportunity_score,
        "estimated_value": mem.estimated_value,
        "audit_results": mem.audit_results or {},
        "offer_proposal": mem.offer_proposal or {},
        "outreach_message": mem.outreach_message or {},
        "last_interaction": mem.last_interaction,
        "next_expected_action": mem.next_expected_action,
        "conversation_history": mem.conversation_history or [],
        "timestamp": mem.timestamp.isoformat() if mem.timestamp else None,
        "updated_at": mem.updated_at.isoformat() if mem.updated_at else None
    }


@router.post("/api/agent/build-website/{business_id}")
async def build_website_for_prospect(
    business_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Triggers the real website artifact generator for an audited prospect."""
    from app.core.security import validate_safe_id
    clean_id = validate_safe_id(business_id)
    biz = await db.get(Business, clean_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    # Fetch audit and offer
    audit_q = select(AuditRun).where(AuditRun.business_id == clean_id).order_by(desc(AuditRun.audited_at)).limit(1)
    audit_res = await db.execute(audit_q)
    audit = audit_res.scalar_one_or_none()
    metrics = audit.metrics if audit and audit.metrics else {}
    load_time = metrics.get("load_time_seconds") or metrics.get("load_time") or 3.8
    audit_results = {
        "performance_score": audit.performance_score if audit else 48.0,
        "load_time_seconds": load_time,
        "seo_score": audit.seo_score if audit else 62.0
    }

    offer_q = select(Offer).where(Offer.business_id == clean_id).order_by(desc(Offer.created_at)).limit(1)
    offer_res = await db.execute(offer_q)
    off = offer_res.scalar_one_or_none()
    offer_proposal = {
        "title": off.title if off else "Speed & Conversion Acceleration",
        "deliverables": off.deliverables if off else []
    }

    from app.delivery.website_builder import WebsiteBuilder
    artifact = await WebsiteBuilder.build_website_for_business(
        session=db,
        business=biz,
        audit_results=audit_results,
        offer_proposal=offer_proposal
    )

    return {
        "status": "SUCCESS",
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "name": artifact.name,
        "preview_url": artifact.preview_url,
        "path": artifact.path
    }


@router.get("/api/artifacts")
async def list_artifacts(
    business_id: Optional[int] = None,
    artifact_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Lists generated artifacts."""
    q = select(Artifact)
    if business_id is not None:
        q = q.where(Artifact.business_id == business_id)
    if artifact_type is not None:
        q = q.where(Artifact.artifact_type == artifact_type)
    q = q.order_by(desc(Artifact.created_at))
    res = await db.execute(q)
    artifacts = res.scalars().all()

    return {
        "artifacts": [
            {
                "id": a.id,
                "business_id": a.business_id,
                "artifact_type": a.artifact_type,
                "name": a.name,
                "version": a.version,
                "status": a.status,
                "preview_url": a.preview_url,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in artifacts
        ]
    }


@router.get("/api/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Gets complete artifact metadata and file path."""
    from app.core.security import validate_safe_id
    clean_art_id = validate_safe_id(artifact_id, "artifact_id")
    artifact = await db.get(Artifact, clean_art_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return {
        "id": artifact.id,
        "business_id": artifact.business_id,
        "artifact_type": artifact.artifact_type,
        "name": artifact.name,
        "version": artifact.version,
        "status": artifact.status,
        "path": artifact.path,
        "preview_url": artifact.preview_url,
        "metadata_json": artifact.metadata_json or {},
        "created_at": artifact.created_at.isoformat() if artifact.created_at else None
    }


@router.get("/api/artifacts/{artifact_id}/preview")
async def preview_artifact(
    artifact_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Safely serves the actual generated HTML/CSS/JS artifact for embedded preview in dashboard iframes.
    Strictly prevents path traversal and scrubs sensitive credentials.
    """
    from app.core.security import validate_safe_id, validate_safe_path_within_root
    clean_art_id = validate_safe_id(artifact_id, "artifact_id")
    artifact = await db.get(Artifact, clean_art_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    from app.delivery.website_builder import ARTIFACTS_ROOT
    abs_file_path = validate_safe_path_within_root(artifact.path, ARTIFACTS_ROOT)

    if not os.path.exists(abs_file_path):
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    with open(abs_file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Secret Scrubbing: ensure no credentials appear in rendered HTML
    from app.core.logging import SENSITIVE_KEY_VALUE_PATTERNS, STANDALONE_SECRET_PATTERNS
    for pattern in SENSITIVE_KEY_VALUE_PATTERNS:
        content = pattern.sub(r'\1: [REDACTED]', content)
    for pattern in STANDALONE_SECRET_PATTERNS:
        content = pattern.sub('[REDACTED_SECRET]', content)

    headers = {
        "X-Frame-Options": "SAMEORIGIN",
        "Content-Security-Policy": "frame-ancestors 'self'",
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff"
    }
    return HTMLResponse(content=content, status_code=200, headers=headers)


# =====================================================================
# Phase 6: Prospect Memory & Objection Handling Cockpit Endpoints
# =====================================================================

@router.get("/api/memory/prospects")
async def list_prospect_memories(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Lists prospects with persistent memory and objection state."""
    from app.database.models import ProspectMemory, Business
    q = select(ProspectMemory).order_by(desc(ProspectMemory.updated_at)).limit(limit)
    memories = (await db.execute(q)).scalars().all()
    results = []
    for m in memories:
        biz = await db.get(Business, m.business_id)
        latest_objection = m.objection_history[-1] if m.objection_history else None
        results.append({
            "business_id": m.business_id,
            "domain": m.domain,
            "name": biz.name if biz else m.domain,
            "pipeline_stage": m.pipeline_stage,
            "contact_email": m.contact_email or (biz.public_email if biz else None),
            "estimated_value": m.estimated_value,
            "last_interaction": m.last_interaction,
            "next_expected_action": m.next_expected_action,
            "latest_objection": latest_objection.get("primary") if latest_objection else None,
            "objection_categories": latest_objection.get("objections", []) if latest_objection else [],
            "draft_response": latest_objection.get("draft_response") if latest_objection else None,
            "recommended_action": latest_objection.get("recommended_action") if latest_objection else None,
            "human_takeover": getattr(biz, "human_takeover", False) if biz else False,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None
        })
    return results


@router.get("/api/memory/prospects/{business_id}")
async def get_prospect_full_memory(business_id: int, db: AsyncSession = Depends(get_db)):
    """Returns complete multi-touch commercial context and memory snapshot for a prospect."""
    from app.crm.memory_service import memory_service
    snapshot = await memory_service.get_full_commercial_context(db, business_id)
    if "error" in snapshot:
        raise HTTPException(status_code=404, detail=snapshot["error"])
    return snapshot


class MemoryDecisionRequest(BaseModel):
    decision: str  # APPROVE, EDIT, REJECT, TAKE_OVER
    edited_text: Optional[str] = None
    operator: str = "owner"


@router.post("/api/memory/prospects/{business_id}/decide")
async def record_prospect_memory_decision(
    business_id: int,
    req: MemoryDecisionRequest,
    db: AsyncSession = Depends(get_db)
):
    """Records owner decision on AI objection response draft."""
    from app.crm.memory_service import memory_service
    res = await memory_service.record_human_decision(
        db,
        business_id=business_id,
        decision=req.decision,
        edited_text=req.edited_text,
        operator=req.operator
    )
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@router.post("/api/memory/prospects/{business_id}/create-proposal")
async def create_memory_aware_proposal_endpoint(
    business_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Generates an evidence-grounded proposal using prospect memory and audit findings."""
    from app.payments.deal_service import deal_closing_service
    try:
        prop = await deal_closing_service.create_memory_aware_proposal(db, business_id)
        return {
            "status": "PROPOSAL_CREATED",
            "proposal_id": prop.id,
            "title": prop.title,
            "total_value": prop.total_value,
            "advance_required": prop.advance_required
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Phase 7: Client Intelligence & Service Matching Endpoints ---

@router.get("/api/client-intelligence/services")
async def get_service_catalog():
    """Returns the complete 10-service catalog with requirements, pricing, and outcomes."""
    from app.client_intelligence.engine import client_intelligence_engine
    return {"status": "SUCCESS", "services": client_intelligence_engine.list_services()}


@router.get("/api/client-intelligence/top")
async def get_top_ranked_prospects(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """Returns top ranked prospects ordered by selection_score (P(Win) * Expected Value)."""
    from app.client_intelligence.engine import client_intelligence_engine
    prospects = await client_intelligence_engine.select_top_prospects_async(db, limit=limit)
    return {"status": "SUCCESS", "count": len(prospects), "prospects": prospects}


@router.get("/api/client-intelligence/{business_id}")
async def get_client_intelligence_for_business(
    business_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Retrieves full client intelligence, pain points, service match, and decision trace."""
    from app.client_intelligence.engine import client_intelligence_engine
    intel = await client_intelligence_engine.get_client_intelligence_async(db, business_id)
    if not intel:
        stmt = select(Business).where(Business.id == business_id)
        res = await db.execute(stmt)
        biz = res.scalar_one_or_none()
        if not biz:
            raise HTTPException(status_code=404, detail=f"Business {business_id} not found")
        
        audit_stmt = select(AuditRun).where(AuditRun.business_id == business_id).order_by(desc(AuditRun.audited_at))
        audit_res = await db.execute(audit_stmt)
        audit = audit_res.scalar_one_or_none()

        intel = await client_intelligence_engine.analyze_business_async(db, biz, audit=audit, persist=True)
    
    return {"status": "SUCCESS", "client_intelligence": intel}


@router.post("/api/client-intelligence/analyze/{business_id}")
async def run_client_intelligence_analysis(
    business_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Executes fresh client intelligence analysis and updates records and memory."""
    from app.client_intelligence.engine import client_intelligence_engine
    stmt = select(Business).where(Business.id == business_id)
    res = await db.execute(stmt)
    biz = res.scalar_one_or_none()
    if not biz:
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")

    audit_stmt = select(AuditRun).where(AuditRun.business_id == business_id).order_by(desc(AuditRun.audited_at))
    audit_res = await db.execute(audit_stmt)
    audit = audit_res.scalar_one_or_none()

    intel = await client_intelligence_engine.analyze_business_async(db, biz, audit=audit, persist=True)
    return {"status": "SUCCESS", "message": f"Client intelligence generated for {biz.name}", "client_intelligence": intel}


# ==========================================
# PHASE 9 — ML EVALUATION, DRIFT & MONITORING
# ==========================================

class OutcomeCreateRequest(BaseModel):
    entity_type: str
    entity_id: int
    event_name: str
    value: float = 0.0
    prediction_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    occurred_at: Optional[datetime] = None


@router.get("/api/ml/health")
async def get_ml_model_health(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns unified ML model health telemetry, composite score (0-100),
    active scoring engine, fallback status, drift report, and data quality.
    """
    user_info = get_current_user_info(request)
    from app.ml.health_service import model_health_service
    health_data = await model_health_service.get_model_health(db)

    # If degraded, log an alert event with deduplication
    if health_data.get("status") == "DEGRADED":
        twelve_hours_ago = datetime.utcnow() - timedelta(hours=12)
        q_dup = select(SecurityAuditLog).where(
            SecurityAuditLog.action == "ML_MODEL_DEGRADED",
            SecurityAuditLog.created_at >= twelve_hours_ago
        ).limit(1)
        existing_alert = (await db.execute(q_dup)).scalar_one_or_none()
        if not existing_alert:
            await AuditService.log_event(
                db=db,
                actor="SystemMonitor",
                action="ML_MODEL_DEGRADED",
                entity_type="ModelVersion",
                entity_id="lead_scoring_model",
                reason="Composite model health score degraded below 60.0.",
                result="FALLBACK_ACTIVATED",
                details={
                    "health_score": health_data.get("composite_health_score"),
                    "reasons": health_data.get("reasons"),
                    "active_engine": health_data.get("active_scoring_engine")
                }
            )

    return {"status": "SUCCESS", "health": health_data}


@router.get("/api/ml/evaluation")
async def get_ml_evaluation(
    request: Request,
    model_version: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns production evaluation metrics (ROC-AUC, PR-AUC, F1, Precision@K,
    Brier calibration, MAE) or INSUFFICIENT_DATA status if below sample thresholds.
    """
    user_info = get_current_user_info(request)
    from app.ml.outcome_service import outcome_service
    from app.ml.evaluator import model_evaluator

    pairs = await outcome_service.get_prediction_outcome_pairs(
        session=db,
        model_version=model_version
    )
    report = model_evaluator.evaluate_predictions(pairs, model_version=model_version)
    return {"status": "SUCCESS", "evaluation": report}


@router.get("/api/ml/drift")
async def get_ml_drift_telemetry(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns numerical PSI, KS test statistics, categorical distribution shifts,
    and output probability drift.
    """
    user_info = get_current_user_info(request)
    from app.ml.health_service import model_health_service
    health_data = await model_health_service.get_model_health(db)
    return {
        "status": "SUCCESS",
        "feature_drift": health_data.get("feature_drift"),
        "prediction_drift": health_data.get("prediction_drift")
    }


@router.get("/api/ml/data-quality")
async def get_ml_data_quality_report(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns feature missing rates, out-of-bounds anomaly counts, and schema audit scores.
    """
    user_info = get_current_user_info(request)
    from app.ml.health_service import model_health_service
    health_data = await model_health_service.get_model_health(db)
    return {
        "status": "SUCCESS",
        "data_quality": health_data.get("data_quality")
    }


@router.post("/api/ml/outcomes")
async def record_ml_outcome(
    req: OutcomeCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Securely records a real lifecycle outcome (contact, reply, proposal, win, loss)
    and links it to prior predictions without temporal leakage.
    """
    user_info = get_current_user_info(request)
    from app.ml.outcome_service import outcome_service

    outcome = await outcome_service.record_outcome(
        session=db,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        event_name=req.event_name,
        value=req.value,
        prediction_id=req.prediction_id,
        metadata=req.metadata,
        occurred_at=req.occurred_at
    )
    await db.commit()
    return {
        "status": "SUCCESS",
        "message": f"Outcome {outcome.event_name} recorded for {outcome.entity_type}:{outcome.entity_id}",
        "outcome_id": outcome.id,
        "prediction_id": outcome.prediction_id
    }


@router.post("/api/ml/retraining/evaluate")
async def evaluate_retraining_policy(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Evaluates whether real data volume and drift justify model retraining.
    """
    user_info = get_current_user_info(request)
    from app.ml.outcome_service import outcome_service
    from app.ml.retraining_policy import retraining_policy
    from app.ml.health_service import model_health_service

    pairs = await outcome_service.get_prediction_outcome_pairs(session=db)
    health = await model_health_service.get_model_health(db)

    policy_decision = retraining_policy.evaluate_retraining_trigger(
        resolved_outcomes=pairs,
        drift_report=health.get("feature_drift")
    )
    return {"status": "SUCCESS", "retraining_policy": policy_decision}


# ============================================================
# Public Business Website Inquiries
# ============================================================

class ContactInquiryRequest(BaseModel):
    name: str
    email: str
    company: str
    service_interest: str
    message: str


@router.post("/api/contact")
async def submit_contact_inquiry(
    payload: ContactInquiryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Public business contact inquiry endpoint.
    Validates submission, logs the inquiry safely, and returns a verified confirmation.
    Zero outgoing emails are dispatched directly to respect EMAIL_DRY_RUN / outbound safety rules.
    """
    name = (payload.name or "").strip()
    email = (payload.email or "").strip()
    company = (payload.company or "").strip()
    service_interest = (payload.service_interest or "").strip()
    message = (payload.message or "").strip()

    if not name or not email or not company or not service_interest or not message:
        raise HTTPException(status_code=400, detail="All contact inquiry fields are required.")

    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Please enter a valid business email address.")

    logger.info(f"[ContactInquiry] Received inquiry from {name} <{email}> at {company} regarding {service_interest}")

    try:
        activity = AgentActivityEvent(
            run_id="public_inquiry",
            event_type="CONTACT_INQUIRY",
            status="SUCCESS",
            message=f"Contact inquiry received from {name} ({company}) - {service_interest}",
            metadata_json={
                "name": name,
                "email": email,
                "company": company,
                "service_interest": service_interest,
                "message_length": len(message),
                "client_ip": request.client.host if request.client else "unknown",
                "received_at": datetime.utcnow().isoformat()
            }
        )
        db.add(activity)
        await db.commit()
    except Exception as e:
        logger.warning(f"[ContactInquiry] Failed to record activity event in DB: {e}")

    return {
        "success": True,
        "message": "Thank you for reaching out. We have received your inquiry and our team will get back to you within 24 business hours.",
        "inquiry": {
            "name": name,
            "company": company,
            "service_interest": service_interest,
            "received_at": datetime.utcnow().isoformat()
        }
    }






