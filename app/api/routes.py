from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.database.connection import get_db
from app.database.models import (
    Business, Contact, AuditRun, AuditFinding, LeadScore,
    Offer, OutreachMessage, OutreachStatus, PipelineStage, SystemRun, MarketOpportunity, Customer
)
from app.analytics.engine import analytics_engine
from app.market_intelligence.engine import market_intelligence_engine
from app.outreach.queue import outreach_approval_queue
from app.outreach.sender import outreach_sender_adapter
from app.crm.pipeline import pipeline_manager
from app.delivery.report_generator import delivery_report_generator
from app.orchestrator.loop import orchestrator
from app.core.config import settings

router = APIRouter()

# Health checks
@router.get("/health")
async def health():
    return {"status": "ok", "service": settings.APP_NAME, "env": settings.APP_ENV}

@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(select(Business).limit(1))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database not ready: {str(e)}")

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
