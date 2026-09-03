import logging
from typing import Dict, Any, Optional
from app.ai.base import BaseAIProvider
from app.ai.schemas import LeadQualificationResult, OutreachDraftResult

logger = logging.getLogger(__name__)

class PersonalizedOutreachWriter:
    """
    Personalized Outreach Writer adapted from agency-agents 'marketing-email-strategist'.
    Generates plain-text, high-deliverability outreach referencing real diagnostic audit evidence.
    """

    def __init__(self, ai_provider: BaseAIProvider):
        self.ai = ai_provider

    async def draft(
        self,
        business_info: Dict[str, Any],
        audit_info: Dict[str, Any],
        qualification: LeadQualificationResult,
        channel: str = "EMAIL"
    ) -> OutreachDraftResult:
        draft = await self.ai.generate_outreach(
            business_info=business_info,
            audit_info=audit_info,
            qualification=qualification,
            channel=channel
        )
        logger.info(f"Outreach Drafted for {business_info.get('name')}: '{draft.subject}'")
        return draft
