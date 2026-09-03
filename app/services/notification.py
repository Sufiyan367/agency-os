import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.entities import Lead, Audit, OutreachMessage, LeadEvent, EventType

logger = logging.getLogger(__name__)

class LocalNotificationService:
    """
    Local mock notification mechanism for agency owner / operator.
    Renders high-visibility terminal banners and records audit events.
    """

    def __init__(self):
        self._notification_history = []

    async def notify_owner_new_qualified_lead(
        self,
        db: AsyncSession,
        lead: Lead,
        audit: Optional[Audit] = None,
        outreach: Optional[OutreachMessage] = None
    ):
        biz = lead.business
        biz_name = biz.name if biz else "Local Business"
        score = lead.lead_score
        qual = lead.qualification
        health = audit.overall_health_score if audit else "N/A"
        speed = audit.performance_score if audit else "N/A"
        rec_service = lead.recommended_service
        subject = outreach.subject if outreach else "None drafted"

        notification_text = f"""
================================================================================
🚨 [OPERATOR ALERT] NEW QUALIFIED LEAD READY FOR REVIEW
================================================================================
🏢 BUSINESS:      {biz_name} ({biz.domain if biz else 'no domain'})
🎯 QUALIFICATION: {qual} (Opportunity Score: {score:.1f}/100)
📊 AUDIT SIGNALS: Overall Health: {health}/100 | Speed: {speed}/100
💡 PAIN POINTS:   {', '.join(lead.pain_points) if lead.pain_points else 'None listed'}
🛠️ RECOMMENDED:   {rec_service}
📬 OUTREACH:      Subject: "{subject}"
👤 CONTACT:       {lead.contact_name} <{lead.contact_email}>
🛑 HUMAN TAKEOVER: {'ACTIVE (AUTOMATION PAUSED)' if lead.human_takeover else 'STANDBY (AUTOMATED)'}
================================================================================
"""
        print(notification_text)
        logger.info(f"Owner notification dispatched for Lead ID {lead.id}: {biz_name}")

        event = LeadEvent(
            lead_id=lead.id,
            event_type=EventType.OWNER_NOTIFIED.value,
            payload={
                "type": "NEW_QUALIFIED_LEAD",
                "business_name": biz_name,
                "lead_score": score,
                "qualification": qual,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        db.add(event)
        await db.commit()
        self._notification_history.append(notification_text)

    async def notify_owner_escalation(
        self,
        db: AsyncSession,
        lead: Lead,
        reason: str,
        incoming_message: Optional[str] = None
    ):
        biz_name = lead.business.name if lead.business else "Local Business"
        banner = f"""
********************************************************************************
⚠️ [ESCALATION ALERT] IMMEDIATE HUMAN INTERVENTION REQUIRED
********************************************************************************
🏢 BUSINESS:   {biz_name} (Lead ID: {lead.id})
👤 CONTACT:    {lead.contact_name} <{lead.contact_email}>
⚡ REASON:     {reason}
💬 CUSTOMER MESSAGE:
\"{incoming_message or 'No message text provided'}\"
👉 ACTION:     Review in dashboard or contact lead directly.
********************************************************************************
"""
        print(banner)
        logger.warning(f"Owner escalation dispatched for Lead ID {lead.id}: {reason}")

        event = LeadEvent(
            lead_id=lead.id,
            event_type=EventType.OWNER_NOTIFIED.value,
            payload={
                "type": "ESCALATION",
                "reason": reason,
                "incoming_message": incoming_message,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        db.add(event)
        await db.commit()
        self._notification_history.append(banner)
