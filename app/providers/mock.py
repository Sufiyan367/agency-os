import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.providers.base import BaseMessageProvider
from app.providers.schemas import MessageDeliveryResult

logger = logging.getLogger(__name__)

class MockMessageProvider(BaseMessageProvider):
    """
    Zero-cost mock messaging provider.
    Simulates outbound outreach and follow-ups without touching any real external email or SMS API.
    Records full metadata, timestamps, and delivery logs.
    """

    def __init__(self):
        self._sent_log: List[MessageDeliveryResult] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    async def send_message(
        self,
        recipient: str,
        subject: str,
        body: str,
        lead_id: int,
        channel: str = "EMAIL",
        metadata: Optional[Dict[str, Any]] = None
    ) -> MessageDeliveryResult:
        msg_id = f"mock-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()

        result = MessageDeliveryResult(
            message_id=msg_id,
            recipient=recipient,
            channel=channel,
            status="MOCKED_SENT",
            sent_at=now,
            is_mocked=True,
            metadata={
                "lead_id": lead_id,
                "subject": subject,
                "body_preview": body[:120] + "...",
                **(metadata or {})
            }
        )

        self._sent_log.append(result)

        print(f"\n[MOCK MESSAGE OUTBOUND] ---------------------------------------------")
        print(f"Channel: {channel} | Recipient: {recipient} | Lead ID: {lead_id}")
        print(f"Subject: {subject}")
        print(f"Timestamp: {now.isoformat()}Z | Message ID: {msg_id}")
        print(f"Body:\n{body}")
        print(f"---------------------------------------------------------------------\n")

        logger.info(f"Mock message sent to {recipient} (ID: {msg_id})")
        return result

    async def get_sent_messages(self, lead_id: Optional[int] = None) -> List[MessageDeliveryResult]:
        if lead_id is not None:
            return [m for m in self._sent_log if m.metadata.get("lead_id") == lead_id]
        return list(self._sent_log)
