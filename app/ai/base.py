from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from app.ai.schemas import LeadQualificationResult, OutreachDraftResult, ReplyClassificationResult

class BaseAIProvider(ABC):
    """
    Abstract AI Provider interface.
    The core application and workflows depend strictly on this abstraction.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the identifier of this AI provider."""
        pass

    @abstractmethod
    async def qualify_lead(
        self,
        business_info: Dict[str, Any],
        audit_info: Dict[str, Any],
        reviews_data: Optional[Dict[str, Any]] = None
    ) -> LeadQualificationResult:
        """Evaluates business and technical audit signals to qualify the lead."""
        pass

    @abstractmethod
    async def generate_outreach(
        self,
        business_info: Dict[str, Any],
        audit_info: Dict[str, Any],
        qualification: LeadQualificationResult,
        channel: str = "EMAIL"
    ) -> OutreachDraftResult:
        """Generates evidence-backed personalized outreach copy."""
        pass

    @abstractmethod
    async def classify_reply(
        self,
        incoming_message: str,
        history: List[Dict[str, str]],
        business_info: Dict[str, Any]
    ) -> ReplyClassificationResult:
        """Classifies incoming prospect replies and determines next action."""
        pass
