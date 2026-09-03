from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseEmailProvider(ABC):
    """Abstract base class for outbound email providers."""

    @abstractmethod
    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends an email and returns delivery metadata:
        {
            "status": "SUCCESS" | "FAILED",
            "provider": str,
            "message_id": Optional[str],
            "event": str,
            "details": Dict[str, Any]
        }
        """
        pass
