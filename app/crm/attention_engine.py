"""
Attention Engine and Executive Exception Routing Layer.
Automatically categorizes agency operational events into:
- HIGH PRIORITY: Inbound interested replies, meeting requests, payment events, complaints, unsubscribes, human takeover.
- MEDIUM PRIORITY: Approved prospects waiting for sender capacity, sent emails awaiting reply, follow-up eligibility.
- NORMAL PRIORITY: Routine discovery, audit, scoring, queue maintenance.

Enforces CEO Notification Policy:
- Routine operations remain completely silent (ALL_CLEAR).
- Only genuine exceptions or high-value commercial events trigger notifications (ATTENTION_REQUIRED).
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc

from app.database.models import (
    Business, OutreachMessage, OutreachStatus, OutreachEvent,
    Reply, ReplyClassification, Payment, Proposal, FollowupSequence,
    PipelineStage, ProspectMemory
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class AttentionEngine:
    """Evaluates agency operational state and generates prioritized attention feeds."""

    async def get_attention_feed(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Scans all operational entities and returns structured attention items
        segmented into HIGH, MEDIUM, and NORMAL priority tiers.
        """
        high_items: List[Dict[str, Any]] = []
        medium_items: List[Dict[str, Any]] = []
        normal_items: List[Dict[str, Any]] = []

        # 1. HIGH PRIORITY: Inbound Interested, Meeting Requests, Complaints, Payments
        q_high_replies = select(Reply).where(
            Reply.is_handled == False,
            Reply.classification.in_([
                ReplyClassification.INTERESTED.value,
                ReplyClassification.MEETING_REQUEST.value,
                ReplyClassification.PRICE_REQUEST.value
            ])
        ).order_by(Reply.received_at.desc())
        interested_replies = (await session.execute(q_high_replies)).scalars().all()
        for r in interested_replies:
            biz = await session.get(Business, r.business_id)
            high_items.append({
                "id": f"reply-high-{r.id}",
                "type": "INTERESTED_PROSPECT",
                "priority": "HIGH",
                "severity": "SUCCESS",
                "title": f"Commercial Lead: {biz.name if biz else r.sender_email} ({r.classification})",
                "description": f"Prospect sent commercial reply: \"{r.raw_body[:120]}...\"",
                "business_id": r.business_id,
                "domain": biz.domain if biz else "",
                "deal_value": 650.0,
                "action_view": "sales",
                "action_label": "Review & Close Deal",
                "timestamp": r.received_at.isoformat() if r.received_at else None
            })

        q_pay_issues = select(Payment).where(
            Payment.status.in_(["FAILED", "DISPUTED"])
        ).order_by(Payment.created_at.desc())
        payment_issues = (await session.execute(q_pay_issues)).scalars().all()
        for p in payment_issues:
            biz = await session.get(Business, p.business_id)
            high_items.append({
                "id": f"pay-issue-{p.id}",
                "type": "PAYMENT_EXCEPTION",
                "priority": "HIGH",
                "severity": "CRITICAL",
                "title": f"Payment {p.status}: {biz.name if biz else 'Client'}",
                "description": f"Transaction #{p.id} ({p.amount} {p.currency}) reported status: {p.status}.",
                "business_id": p.business_id,
                "domain": biz.domain if biz else "",
                "deal_value": float(p.amount),
                "action_view": "clients",
                "action_label": "Inspect Billing",
                "timestamp": p.created_at.isoformat() if p.created_at else None
            })

        q_pay_won = select(Payment).where(
            Payment.status == "COMPLETED"
        ).order_by(Payment.created_at.desc()).limit(5)
        recent_payments = (await session.execute(q_pay_won)).scalars().all()
        for p in recent_payments:
            biz = await session.get(Business, p.business_id)
            high_items.append({
                "id": f"pay-won-{p.id}",
                "type": "PAYMENT_CONFIRMED",
                "priority": "HIGH",
                "severity": "SUCCESS",
                "title": f"Payment Secured: ${p.amount:,.0f} from {biz.name if biz else 'Client'}",
                "description": f"Client advance paid via {p.reference_id}. Fulfillment ready.",
                "business_id": p.business_id,
                "domain": biz.domain if biz else "",
                "deal_value": float(p.amount),
                "action_view": "clients",
                "action_label": "View Client Project",
                "timestamp": p.created_at.isoformat() if p.created_at else None
            })

        q_takeover_mem = select(ProspectMemory).where(
            ProspectMemory.pipeline_stage == "HUMAN_TAKEOVER"
        ).limit(10)
        takeover_mems = (await session.execute(q_takeover_mem)).scalars().all()
        for pm in takeover_mems:
            b = await session.get(Business, pm.business_id) if pm.business_id else None
            high_items.append({
                "id": f"takeover-{pm.id}",
                "type": "HUMAN_TAKEOVER_REQUIRED",
                "priority": "HIGH",
                "severity": "WARNING",
                "title": f"Attention Required: {b.name if b else pm.domain} ({pm.domain})",
                "description": "Sensitive inquiry or complex objection flagged for executive attention.",
                "business_id": pm.business_id,
                "domain": pm.domain,
                "deal_value": float(pm.estimated_value or 650.0),
                "action_view": "sales",
                "action_label": "Direct Engagement",
                "timestamp": pm.updated_at.isoformat() if pm.updated_at else None
            })

        # 2. MEDIUM PRIORITY: Approved Queue Waiting for Capacity, Awaiting Replies
        q_waiting_cap = select(OutreachMessage).where(
            OutreachMessage.status == OutreachStatus.APPROVED.value
        ).order_by(OutreachMessage.created_at.asc())
        waiting_messages = (await session.execute(q_waiting_cap)).scalars().all()
        for m in waiting_messages:
            biz = await session.get(Business, m.business_id)
            medium_items.append({
                "id": f"queued-cap-{m.id}",
                "type": "QUEUED_SENDER_CAPACITY",
                "priority": "MEDIUM",
                "severity": "INFO",
                "title": f"Queued for Outbound Capacity: {biz.name if biz else m.recipient_email}",
                "description": f"Message #{m.id} approved and ready. Waiting for daily rollout quota / sender capacity.",
                "business_id": m.business_id,
                "domain": biz.domain if biz else "",
                "deal_value": 650.0,
                "action_view": "outreach",
                "action_label": "View Queue",
                "timestamp": m.created_at.isoformat() if m.created_at else None
            })

        q_sent_awaiting = select(OutreachMessage).where(
            OutreachMessage.status == OutreachStatus.SENT.value
        ).order_by(OutreachMessage.sent_at.desc()).limit(10)
        sent_awaiting = (await session.execute(q_sent_awaiting)).scalars().all()
        for m in sent_awaiting:
            q_has_rep = select(func.count(Reply.id)).where(Reply.outreach_message_id == m.id)
            rep_count = (await session.execute(q_has_rep)).scalar() or 0
            if rep_count == 0:
                biz = await session.get(Business, m.business_id)
                medium_items.append({
                    "id": f"sent-awaiting-{m.id}",
                    "type": "AWAITING_REPLY",
                    "priority": "MEDIUM",
                    "severity": "INFO",
                    "title": f"Contacted: {biz.name if biz else m.recipient_email}",
                    "description": f"Outreach sent {m.sent_at.strftime('%b %d, %H:%M') if m.sent_at else ''}. Awaiting reply.",
                    "business_id": m.business_id,
                    "domain": biz.domain if biz else "",
                    "deal_value": 650.0,
                    "action_view": "outreach",
                    "action_label": "Track Thread",
                    "timestamp": m.sent_at.isoformat() if m.sent_at else None
                })

        # 3. NORMAL PRIORITY: Routine Discovery, Audits, Scoring, Maintenance
        q_recent_discovered = select(Business).where(
            Business.pipeline_stage.in_([PipelineStage.DISCOVERED.value, PipelineStage.VERIFIED.value, PipelineStage.AUDITED.value])
        ).order_by(Business.created_at.desc()).limit(5)
        recent_leads = (await session.execute(q_recent_discovered)).scalars().all()
        for b in recent_leads:
            normal_items.append({
                "id": f"discovery-routine-{b.id}",
                "type": "ROUTINE_PIPELINE",
                "priority": "NORMAL",
                "severity": "INFO",
                "title": f"Discovered & Audited: {b.name} ({b.domain})",
                "description": f"Stage: {b.pipeline_stage}. Audit score: {b.prospect_score}/100.",
                "business_id": b.id,
                "domain": b.domain,
                "deal_value": 650.0,
                "action_view": "prospects",
                "action_label": "View Prospect",
                "timestamp": b.created_at.isoformat() if b.created_at else None
            })

        # 4. CEO Notification Policy Evaluation
        has_high_priority_exception = len(high_items) > 0
        status = "ATTENTION_REQUIRED" if has_high_priority_exception else "ALL_CLEAR"
        if has_high_priority_exception:
            ceo_message = f"{len(high_items)} high-value commercial event{'s' if len(high_items) > 1 else ''} require CEO engagement."
        else:
            ceo_message = "All autonomous operations running nominally. Zero routine manual work required."

        return {
            "status": status,
            "overall_status": status,
            "ceo_notification_required": has_high_priority_exception,
            "ceo_notification": "ATTENTION_REQUIRED" if has_high_priority_exception else "ALL_CLEAR",
            "message": ceo_message,
            "high_priority_count": len(high_items),
            "medium_priority_count": len(medium_items),
            "normal_priority_count": len(normal_items),
            "total_items_count": len(high_items) + len(medium_items) + len(normal_items),
            "counts": {
                "high_priority": len(high_items),
                "medium_priority": len(medium_items),
                "normal_priority": len(normal_items)
            },
            "items": {
                "high": high_items,
                "medium": medium_items,
                "normal": normal_items
            },
            "feed": high_items + medium_items
        }

    async def get_contacted_history(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Historical Visibility Query Engine (Requirement 7):
        Provides precise, structured answers to the core operating questions:
        - Who have we contacted?
        - What did we send?
        - When?
        - What was offered?
        - Did they reply?
        - What did they reply?
        - What is the current state?
        - What action is pending?
        - What is the deal value?
        - Which prospects are waiting for sender capacity?
        """
        q_contacted = select(OutreachMessage).where(
            OutreachMessage.status == OutreachStatus.SENT.value
        ).order_by(OutreachMessage.sent_at.desc())
        sent_messages = (await session.execute(q_contacted)).scalars().all()

        contacted_records = []
        for msg in sent_messages:
            biz = await session.get(Business, msg.business_id) if msg.business_id else None
            q_ev = select(OutreachEvent).where(OutreachEvent.outreach_message_id == msg.id).order_by(OutreachEvent.created_at.desc())
            ev = (await session.execute(q_ev)).scalars().first()
            ev_det = ev.details if ev and ev.details else {}

            q_rep = select(Reply).where(
                or_(
                    Reply.outreach_message_id == msg.id,
                    Reply.business_id == msg.business_id
                )
            ).order_by(Reply.received_at.desc())
            replies = (await session.execute(q_rep)).scalars().all()
            latest_rep = replies[0] if replies else None

            q_mem = select(ProspectMemory).where(ProspectMemory.business_id == msg.business_id)
            mem = (await session.execute(q_mem)).scalars().first()

            contacted_records.append({
                "business_id": biz.id if biz else None,
                "business_name": biz.name if biz else "Unknown",
                "domain": biz.domain if biz else "",
                "recipient_email": msg.recipient_email,
                "country": biz.country if biz else "US",
                "message_id": msg.id,
                "provider_message_id": ev_det.get("message_id") or ev_det.get("gmail_message_id"),
                "thread_id": ev_det.get("thread_id") or (mem.thread_id if mem else None),
                "subject": msg.subject,
                "body": msg.body,
                "variant": msg.variant_name,
                "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
                "deal_value": 650.0,
                "offer_title": mem.offer_proposal.get("title", "Website Turnaround") if mem and mem.offer_proposal else "Website Turnaround & Optimization",
                "has_replied": len(replies) > 0,
                "reply_count": len(replies),
                "latest_reply": {
                    "classification": latest_rep.classification,
                    "body": latest_rep.raw_body,
                    "received_at": latest_rep.received_at.isoformat() if latest_rep.received_at else None,
                    "is_interested": latest_rep.classification == "INTERESTED"
                } if latest_rep else None,
                "current_pipeline_stage": biz.pipeline_stage if biz else "CONTACTED",
                "pending_action": mem.next_expected_action if mem else "AWAITING_REPLY",
                "delivery_status": ev_det.get("delivery_status", "DELIVERED")
            })

        q_waiting = select(OutreachMessage).where(
            OutreachMessage.status == OutreachStatus.APPROVED.value
        ).order_by(OutreachMessage.created_at.asc())
        waiting_messages = (await session.execute(q_waiting)).scalars().all()

        waiting_records = []
        for wm in waiting_messages:
            biz = await session.get(Business, wm.business_id) if wm.business_id else None
            waiting_records.append({
                "message_id": wm.id,
                "business_id": wm.business_id,
                "business_name": biz.name if biz else "Unknown",
                "domain": biz.domain if biz else "",
                "recipient_email": wm.recipient_email,
                "subject": wm.subject,
                "status": wm.status,
                "approved_at": wm.approved_at.isoformat() if wm.approved_at else None,
                "deal_value": 650.0,
                "reason_waiting": "Awaiting available daily sender quota or rollout stage expansion"
            })

        return {
            "total_contacted": len(contacted_records),
            "contacted_prospects": contacted_records,
            "waiting_for_sender_capacity_count": len(waiting_records),
            "waiting_for_sender_capacity": waiting_records,
            "summary": {
                "replied_count": sum(1 for c in contacted_records if c["has_replied"]),
                "interested_count": sum(1 for c in contacted_records if c["has_replied"] and c["latest_reply"] and c["latest_reply"]["is_interested"]),
                "awaiting_reply_count": sum(1 for c in contacted_records if not c["has_replied"])
            }
        }


attention_engine = AttentionEngine()
