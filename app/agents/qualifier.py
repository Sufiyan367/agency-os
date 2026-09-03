import logging
from typing import Dict, Any, Optional
from app.ai.base import BaseAIProvider
from app.ai.schemas import LeadQualificationResult

logger = logging.getLogger(__name__)

class LeadQualificationAgent:
    """
    Lead Qualification Agent adapted from agency-agents 'sales-outbound-strategist'.
    Evaluates raw inbound/discovered business data and technical audit findings,
    producing a validated LeadQualificationResult.
    """

    def __init__(self, ai_provider: BaseAIProvider):
        self.ai = ai_provider

    async def qualify(
        self,
        business_info: Dict[str, Any],
        audit_info: Dict[str, Any],
        reviews_data: Optional[Dict[str, Any]] = None
    ) -> LeadQualificationResult:
        # 1. Sanitize external inputs
        sanitized_biz = {
            "name": str(business_info.get("name", "Unknown Business"))[:100],
            "domain": str(business_info.get("domain", ""))[:100],
            "niche": str(business_info.get("niche", "Local Services"))[:100],
            "city": str(business_info.get("city", ""))[:100],
            "website_url": str(business_info.get("website_url", ""))[:255],
            "booking_url": str(business_info.get("booking_url", ""))[:255]
        }

        sanitized_audit = {
            "overall_health_score": float(audit_info.get("overall_health_score", 50.0)),
            "performance_score": float(audit_info.get("performance_score", 50.0)),
            "seo_score": float(audit_info.get("seo_score", 50.0)),
            "accessibility_score": float(audit_info.get("accessibility_score", 50.0)),
            "mobile_responsive": bool(audit_info.get("mobile_responsive", True)),
            "findings": audit_info.get("findings", [])
        }

        # 2. Execute qualification through the configured AI provider
        result = await self.ai.qualify_lead(sanitized_biz, sanitized_audit, reviews_data)

        # 3. Deterministic sanity checks (safety guardrails)
        if sanitized_audit["overall_health_score"] < 40.0 and result.lead_score < 70.0:
            result.lead_score = 75.0
            result.qualification = "HOT"

        logger.info(
            f"Lead Qualified: {sanitized_biz['name']} -> Score: {result.lead_score} "
            f"({result.qualification}) | Service: {result.recommended_service}"
        )
        return result
