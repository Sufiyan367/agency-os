"""
Email Provider Abstractions.
Keeps DryRunEmailProvider as default. Zero live dispatches without explicit configuration.
"""
from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class EmailSendResult(BaseModel):
    success: bool
    message_id: str
    recipient: str
    dry_run: bool
    status_code: int = 200
    error: Optional[str] = None


class BaseEmailProvider(ABC):
    @abstractmethod
    async def send_email(self, recipient: str, subject: str, body: str) -> EmailSendResult:
        pass


class DryRunEmailProvider(BaseEmailProvider):
    async def send_email(self, recipient: str, subject: str, body: str) -> EmailSendResult:
        logger.info(f"[DRY-RUN EMAIL] To: {recipient} | Subject: {subject} | Length: {len(body)} chars")
        return EmailSendResult(
            success=True,
            message_id=f"dry_run_{recipient.split('@')[0]}",
            recipient=recipient,
            dry_run=True,
            status_code=200
        )
