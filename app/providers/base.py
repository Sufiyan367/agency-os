from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from app.providers.schemas import MessageDeliveryResult

class BaseMessageProvider(ABC):
    """
    Abstract Messaging Provider interface.
    Supports email, SMS, WhatsApp or local simulation.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns provider identifier."""
        pass

    @abstractmethod
    async def send_message(
        self,
        recipient: str,
        subject: str,
        body: str,
        lead_id: int,
        channel: str = "EMAIL",
        metadata: Optional[Dict[str, Any]] = None
    ) -> MessageDeliveryResult:
        """Dispatches an outbound message to a recipient."""
        pass

    @abstractmethod
    async def get_sent_messages(self, lead_id: Optional[int] = None) -> List[MessageDeliveryResult]:
        """Retrieves history of sent messages."""
        pass
