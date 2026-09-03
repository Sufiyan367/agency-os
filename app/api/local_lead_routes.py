from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database.connection import get_db
from app.models.entities import (
    Business, Lead, Audit, OutreachMessage, FollowupSchedule, LeadEvent,
    EventType, LeadStatus, FollowupStatus
)
from app.services.outreach import OutreachService
from app.services.followup_engine import FollowUpEngine
from app.services.notification import LocalNotificationService

router = APIRouter(tags=["Local Lead Recovery"])

class TakeoverRequest(BaseModel):
    enabled: bool
    reason: Optional[str] = "Manual operator intervention"

class SimulateReplyRequest(BaseModel):
    lead_id: int
    message_text: str

@router.get("/api/v2/leads")
async def list_local_leads(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Lead).order_by(Lead.id.desc()))
    leads = result.scalars().all()
    output = []
    for l in leads:
        output.append({
            "id": l.id,
            "business_name": l.business.name if l.business else "Unknown",
            "domain": l.business.domain if l.business else "",
            "contact_name": l.contact_name,
            "contact_email": l.contact_email,
            "lead_score": l.lead_score,
            "qualification": l.qualification,
            "status": l.status,
            "human_takeover": l.human_takeover,
            "human_takeover_reason": l.human_takeover_reason,
            "created_at": l.created_at.isoformat()
        })
    return output

@router.get("/api/v2/leads/{lead_id}")
async def get_local_lead_detail(lead_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = res.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    biz = lead.business
    audit_res = await db.execute(
        select(Audit).where(Audit.business_id == lead.business_id).order_by(Audit.audited_at.desc())
    )
    audit = audit_res.scalars().first()

    return {
        "lead": {
            "id": lead.id,
            "contact_name": lead.contact_name,
            "contact_email": lead.contact_email,
            "lead_score": lead.lead_score,
            "qualification": lead.qualification,
            "status": lead.status,
            "pain_points": lead.pain_points,
            "recommended_service": lead.recommended_service,
            "reasoning": lead.reasoning,
            "human_takeover": lead.human_takeover,
            "human_takeover_reason": lead.human_takeover_reason
        },
        "business": {
            "name": biz.name if biz else "",
            "domain": biz.domain if biz else "",
            "niche": biz.niche if biz else "",
            "city": biz.city if biz else ""
        },
        "audit": {
            "overall_health_score": audit.overall_health_score if audit else None,
            "performance_score": audit.performance_score if audit else None,
            "seo_score": audit.seo_score if audit else None,
            "mobile_responsive": audit.mobile_responsive if audit else True,
            "findings": audit.findings if audit else []
        },
        "outreach_messages": [
            {
                "id": m.id,
                "subject": m.subject,
                "body": m.body,
                "status": m.status,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None
            } for m in lead.outreach_messages
        ],
        "followups": [
            {
                "id": f.id,
                "step_number": f.step_number,
                "scheduled_for": f.scheduled_for.isoformat(),
                "status": f.status,
                "subject": f.subject,
                "cancel_reason": f.cancel_reason
            } for f in lead.followups
        ],
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "payload": e.payload,
                "created_at": e.created_at.isoformat()
            } for e in lead.events
        ]
    }

@router.post("/api/v2/leads/{lead_id}/takeover")
async def toggle_human_takeover(
    lead_id: int,
    req: TakeoverRequest,
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = res.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.human_takeover = req.enabled
    lead.human_takeover_reason = req.reason if req.enabled else None

    if req.enabled:
        lead.status = LeadStatus.HUMAN_TAKEOVER.value
        # Freeze and cancel any active pending follow-up messages!
        engine = FollowUpEngine()
        await engine.cancel_followups_for_lead(db, lead_id, reason=f"Human Takeover Enabled: {req.reason}")

    event = LeadEvent(
        lead_id=lead.id,
        event_type=EventType.HUMAN_TAKEOVER_ENABLED.value if req.enabled else EventType.HUMAN_TAKEOVER_DISABLED.value,
        payload={"enabled": req.enabled, "reason": req.reason}
    )
    db.add(event)
    await db.commit()
    await db.refresh(lead)

    return {
        "success": True,
        "lead_id": lead.id,
        "human_takeover": lead.human_takeover,
        "status": lead.status,
        "message": "Automation paused for this lead" if req.enabled else "Automation standby"
    }

@router.post("/api/v2/leads/{lead_id}/outreach/approve")
async def approve_lead_outreach(
    lead_id: int,
    message_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    outreach_svc = OutreachService()
    try:
        msg = await outreach_svc.approve_and_send(db, message_id)
        return {"success": True, "message_id": msg.id, "status": msg.status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/v2/simulate-reply")
async def simulate_incoming_reply(
    req: SimulateReplyRequest,
    db: AsyncSession = Depends(get_db)
):
    from app.ai.factory import get_ai_provider
    res = await db.execute(select(Lead).where(Lead.id == req.lead_id))
    lead = res.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    ai = get_ai_provider()
    classification = await ai.classify_reply(req.message_text, [], {})

    # Auto-stop followups
    engine = FollowUpEngine()
    cancelled = await engine.cancel_followups_for_lead(
        db, lead.id, reason=f"Prospect replied: {classification.classification}"
    )

    lead.status = LeadStatus.REPLIED.value
    if classification.needs_human:
        lead.human_takeover = True
        lead.human_takeover_reason = f"Reply required intervention: {classification.summary}"

    event = LeadEvent(
        lead_id=lead.id,
        event_type=EventType.CUSTOMER_REPLY.value,
        payload={
            "message_text": req.message_text,
            "classification": classification.model_dump(),
            "cancelled_followups": cancelled
        }
    )
    db.add(event)
    await db.commit()

    # Notify owner
    notifier = LocalNotificationService()
    await notifier.notify_owner_escalation(
        db, lead, reason=f"Customer Reply: {classification.classification}", incoming_message=req.message_text
    )

    return {
        "success": True,
        "lead_id": lead.id,
        "classification": classification.model_dump(),
        "cancelled_followups": cancelled,
        "human_takeover_active": lead.human_takeover
    }

@router.get("/local-dashboard", response_class=HTMLResponse)
async def serve_local_dashboard():
    """
    Lightweight functional local dashboard for monitoring leads, scores,
    and toggling the Human Takeover / Pause Automation switch.
    """
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Local AI Lead Recovery & Follow-Up Automation</title>
    <style>
        :root {
            --bg: #0b0f19;
            --surface: #131b2e;
            --border: #1f293d;
            --primary: #00e5ff;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text: #f8fafc;
            --muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 24px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }
        .header h1 { font-size: 1.4rem; color: var(--primary); }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-hot { background: rgba(239,68,68,0.2); color: var(--danger); border: 1px solid var(--danger); }
        .badge-warm { background: rgba(245,158,11,0.2); color: var(--warning); border: 1px solid var(--warning); }
        .badge-cold { background: rgba(148,163,184,0.2); color: var(--muted); border: 1px solid var(--muted); }
        .badge-takeover { background: rgba(239,68,68,0.3); color: #fff; border: 1px solid var(--danger); }
        
        .grid { display: grid; grid-template-columns: 1fr 1.2fr; gap: 24px; }
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 20px;
        }
        .card h2 { font-size: 1.1rem; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
        table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
        th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }
        th { color: var(--muted); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }
        tr:hover { background: rgba(255,255,255,0.02); cursor: pointer; }
        tr.selected { background: rgba(0,229,255,0.08); border-left: 3px solid var(--primary); }
        
        .btn {
            padding: 6px 12px;
            border-radius: 4px;
            border: none;
            font-weight: 600;
            font-size: 0.8rem;
            cursor: pointer;
        }
        .btn-takeover-active { background: var(--danger); color: #fff; }
        .btn-takeover-off { background: var(--surface); color: var(--muted); border: 1px solid var(--border); }
        .btn-approve { background: var(--success); color: #fff; }
        pre {
            background: #060911;
            padding: 12px;
            border-radius: 4px;
            font-size: 0.82rem;
            color: #cbd5e1;
            white-space: pre-wrap;
            border: 1px solid var(--border);
            max-height: 200px;
            overflow-y: auto;
        }
        .timeline-item {
            padding: 8px 12px;
            border-left: 2px solid var(--primary);
            margin-bottom: 8px;
            background: rgba(0,0,0,0.2);
            font-size: 0.8rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>// LOCAL AI LEAD RECOVERY AUTOMATION</h1>
            <p style="color:var(--muted); font-size:0.85rem; margin-top:4px;">Local-First System • Zero Cloud Costs • Human Takeover Guard</p>
        </div>
        <div>
            <span class="badge" style="background:rgba(16,185,129,0.15); color:var(--success); border:1px solid var(--success);">● LOCAL ENGINE READY</span>
        </div>
    </div>

    <div class="grid">
        <!-- Leads List Table -->
        <div class="card">
            <h2>Qualified Lead Registry</h2>
            <table>
                <thead>
                    <tr>
                        <th>Business</th>
                        <th>Score</th>
                        <th>Status</th>
                        <th>Takeover</th>
                    </tr>
                </thead>
                <tbody id="leads-tbody">
                    <tr><td colspan="4" style="text-align:center; color:var(--muted);">Loading leads...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Lead Inspector & Takeover Control -->
        <div class="card" id="detail-card">
            <h2>Lead Inspector & Action Center</h2>
            <div id="lead-inspector-content" style="color:var(--muted);">
                Select a lead from the registry to view diagnostic audit findings, outreach copy, and control human takeover.
            </div>
        </div>
    </div>

    <script>
        let currentLeadId = null;

        async function loadLeads() {
            try {
                const res = await fetch('/api/v2/leads');
                const leads = await res.json();
                const tbody = document.getElementById('leads-tbody');
                tbody.innerHTML = '';
                if (leads.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--muted);">No leads recorded. Run lifecycle demo to populate!</td></tr>';
                    return;
                }
                leads.forEach(l => {
                    const tr = document.createElement('tr');
                    tr.onclick = () => selectLead(l.id);
                    if (currentLeadId === l.id) tr.className = 'selected';
                    const qBadge = l.qualification === 'HOT' ? 'badge-hot' : (l.qualification === 'WARM' ? 'badge-warm' : 'badge-cold');
                    tr.innerHTML = `
                        <td><strong>${l.business_name}</strong><br><span style="color:var(--muted); font-size:0.75rem;">${l.contact_email}</span></td>
                        <td><span class="badge ${qBadge}">${l.lead_score.toFixed(0)} (${l.qualification})</span></td>
                        <td><span style="font-size:0.8rem;">${l.status}</span></td>
                        <td>${l.human_takeover ? '<span class="badge badge-takeover">TAKEOVER ACTIVE</span>' : '<span style="color:var(--success); font-size:0.75rem;">AUTOMATED</span>'}</td>
                    `;
                    tbody.appendChild(tr);
                });
                if (!currentLeadId && leads.length > 0) selectLead(leads[0].id);
            } catch (e) {
                console.error(e);
            }
        }

        async function selectLead(leadId) {
            currentLeadId = leadId;
            const res = await fetch(`/api/v2/leads/${leadId}`);
            const data = await res.json();
            const container = document.getElementById('lead-inspector-content');
            const l = data.lead;
            const b = data.business;
            const a = data.audit;

            container.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; flex-wrap:wrap; gap:10px;">
                    <div>
                        <h3 style="color:#fff; font-size:1.15rem;">${b.name}</h3>
                        <p style="color:var(--muted); font-size:0.85rem;">${l.contact_name} &bull; ${l.contact_email} &bull; ${b.city}</p>
                    </div>
                    <div>
                        <button class="btn ${l.human_takeover ? 'btn-takeover-active' : 'btn-takeover-off'}" onclick="toggleTakeover(${l.id}, ${!l.human_takeover})">
                            ${l.human_takeover ? '🛑 Human Takeover ACTIVE (Click to Resume Auto)' : '👤 Enable Human Takeover'}
                        </button>
                    </div>
                </div>

                <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; margin-bottom:16px;">
                    <div style="background:#060911; padding:10px; border-radius:4px; border:1px solid var(--border);">
                        <span style="font-size:0.75rem; color:var(--muted);">Lead Score</span><br>
                        <strong style="color:var(--primary); font-size:1.1rem;">${l.lead_score.toFixed(1)}/100</strong>
                    </div>
                    <div style="background:#060911; padding:10px; border-radius:4px; border:1px solid var(--border);">
                        <span style="font-size:0.75rem; color:var(--muted);">Audit Health</span><br>
                        <strong style="color:#fff; font-size:1.1rem;">${a.overall_health_score || 'N/A'}/100</strong>
                    </div>
                    <div style="background:#060911; padding:10px; border-radius:4px; border:1px solid var(--border);">
                        <span style="font-size:0.75rem; color:var(--muted);">Service Fit</span><br>
                        <strong style="color:var(--success); font-size:0.85rem;">${l.recommended_service}</strong>
                    </div>
                </div>

                <h4 style="font-size:0.85rem; color:var(--muted); margin-bottom:6px;">Technical Bottlenecks Identified:</h4>
                <ul style="padding-left:18px; margin-bottom:16px; font-size:0.85rem; color:#cbd5e1;">
                    ${(l.pain_points || []).map(p => `<li>${p}</li>`).join('')}
                </ul>

                <h4 style="font-size:0.85rem; color:var(--muted); margin-bottom:6px;">Personalized Outreach Copy:</h4>
                ${data.outreach_messages.length > 0 ? `
                    <div style="margin-bottom:16px;">
                        <p style="font-size:0.85rem; margin-bottom:4px;"><strong>Subject:</strong> ${data.outreach_messages[0].subject}</p>
                        <pre>${data.outreach_messages[0].body}</pre>
                        ${data.outreach_messages[0].status === 'PENDING_APPROVAL' ? `
                            <button class="btn btn-approve" style="margin-top:8px;" onclick="approveOutreach(${l.id}, ${data.outreach_messages[0].id})">✓ Approve & Send (Simulated)</button>
                        ` : `<span style="font-size:0.8rem; color:var(--success); margin-top:4px; display:inline-block;">Status: ${data.outreach_messages[0].status}</span>`}
                    </div>
                ` : '<p style="color:var(--muted); font-size:0.85rem; margin-bottom:16px;">No outreach drafted yet.</p>'}

                <h4 style="font-size:0.85rem; color:var(--muted); margin-bottom:6px;">Follow-Up Sequence & Schedule:</h4>
                <div style="margin-bottom:16px;">
                    ${data.followups.length > 0 ? data.followups.map(f => `
                        <div style="display:flex; justify-content:space-between; font-size:0.8rem; padding:6px 0; border-bottom:1px solid var(--border);">
                            <span>Step #${f.step_number}: ${f.subject}</span>
                            <span style="color:${f.status === 'SENT' ? 'var(--success)' : (f.status.startsWith('CANCELLED') ? 'var(--danger)' : 'var(--warning)')}">${f.status}</span>
                        </div>
                    `).join('') : '<p style="color:var(--muted); font-size:0.85rem;">No followups scheduled.</p>'}
                </div>

                <h4 style="font-size:0.85rem; color:var(--muted); margin-bottom:6px;">Audit Trail & Event Log (${data.events.length}):</h4>
                <div style="max-height:160px; overflow-y:auto;">
                    ${data.events.map(e => `
                        <div class="timeline-item">
                            <strong>[${e.event_type}]</strong> - ${new Date(e.created_at).toLocaleTimeString()}<br>
                            <span style="color:var(--muted); font-size:0.75rem;">${JSON.stringify(e.payload)}</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        async function toggleTakeover(leadId, enable) {
            await fetch(`/api/v2/leads/${leadId}/takeover`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: enable, reason: enable ? 'Operator manual takeover from local dashboard' : null })
            });
            loadLeads();
            selectLead(leadId);
        }

        async function approveOutreach(leadId, messageId) {
            await fetch(`/api/v2/leads/${leadId}/outreach/approve?message_id=${messageId}`, { method: 'POST' });
            loadLeads();
            selectLead(leadId);
        }

        loadLeads();
        setInterval(loadLeads, 10000);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
