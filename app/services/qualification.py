from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.entities import Lead, Audit, LeadEvent, EventType, LeadStatus
from app.agents.qualifier import LeadQualificationAgent
from app.ai.base import BaseAIProvider
from app.ai.factory import get_ai_provider
from app.ai.schemas import LeadQualificationResult

class QualificationService:
    """
    Coordinates lead qualification, model persistence, and event logging.
    """

    def __init__(self, ai_provider: Optional[BaseAIProvider] = None):
        self.ai = ai_provider or get_ai_provider()
        self.agent = LeadQualificationAgent(self.ai)

    async def qualify_lead_record(
        self,
        db: AsyncSession,
        lead_id: int,
        reviews_data: Optional[Dict[str, Any]] = None
    ) -> LeadQualificationResult:
        result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead with id {lead_id} not found")

        # Load business and latest audit
        biz = lead.business
        audit_res = await db.execute(
            select(Audit).where(Audit.business_id == lead.business_id).order_by(Audit.audited_at.desc())
        )
        audit = audit_res.scalars().first()

        business_info = {
            "name": biz.name if biz else "Local Business",
            "domain": biz.domain if biz else "",
            "niche": biz.niche if biz else "Local Services",
            "city": biz.city if biz else "",
            "website_url": biz.website_url if biz else ""
        }

        audit_info = {
            "overall_health_score": audit.overall_health_score if audit else 50.0,
            "performance_score": audit.performance_score if audit else 50.0,
            "seo_score": audit.seo_score if audit else 50.0,
            "accessibility_score": audit.accessibility_score if audit else 50.0,
            "mobile_responsive": audit.mobile_responsive if audit else True,
            "findings": audit.findings if audit else []
        }

        qual_result = await self.agent.qualify(business_info, audit_info, reviews_data)

        # Update lead in database
        lead.lead_score = qual_result.lead_score
        lead.qualification = qual_result.qualification
        lead.intent_level = qual_result.intent_level
        lead.confidence = qual_result.confidence
        lead.pain_points = qual_result.pain_points
        lead.recommended_service = qual_result.recommended_service
        lead.reasoning = qual_result.reasoning
        lead.status = LeadStatus.QUALIFIED.value

        # Log event audit trail
        event = LeadEvent(
            lead_id=lead.id,
            event_type=EventType.LEAD_QUALIFIED.value,
            payload={
                "lead_score": qual_result.lead_score,
                "qualification": qual_result.qualification,
                "pain_points": qual_result.pain_points,
                "recommended_service": qual_result.recommended_service
            }
        )
        db.add(event)
        await db.commit()
        await db.refresh(lead)

        return qual_result
