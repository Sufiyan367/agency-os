"""
Multi-Channel Ingestion & Customer Boundary Enforcement — Mega Prompt 7.
Normalizes inbound support signals across Email, WhatsApp, Voice, and Web Portal,
and strictly enforces customer vs prospect identity boundaries.
"""
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Customer, Business

logger = logging.getLogger("agency.support.channels")


class NonCustomerException(PermissionError):
    """Raised when an entity that is solely a prospect attempts to access customer support."""
    pass


class InboundSupportEvent(BaseModel):
    event_id: str
    channel: str  # EMAIL, WHATSAPP, VOICE, WEB_PORTAL
    customer_id: Optional[int]
    sender_identifier: str  # email address, phone number, or session ID
    subject: str
    raw_payload: str
    correlation_id: str
    timestamp: datetime = datetime.utcnow()


class ChannelNormalizer:
    """
    Normalizes multi-channel support requests and validates commercial customer boundaries.
    """

    @classmethod
    async def resolve_and_validate_customer(
        cls,
        session: AsyncSession,
        customer_id: Optional[int],
        sender_email: Optional[str] = None
    ) -> Customer:
        """
        Guarantees that support is strictly granted to confirmed commercial customers.
        Prospects in the sales pipeline are rejected from customer support operations.
        """
        cust = None
        if customer_id:
            cust = await session.get(Customer, customer_id)

        if not cust and sender_email:
            stmt = select(Customer).where(Customer.contact_email == sender_email)
            cust = (await session.execute(stmt)).scalar_one_or_none()

        if not cust:
            # Check if this email belongs to a prospect business
            if sender_email:
                biz_stmt = select(Business).where(Business.public_email == sender_email)
                biz = (await session.execute(biz_stmt)).scalar_one_or_none()
                if biz:
                    raise NonCustomerException(
                        f"Sender '{sender_email}' is an active commercial prospect (Business #{biz.id}), "
                        f"not a paying customer. Support operations are isolated to delivered customers."
                    )
            raise NonCustomerException(
                f"Customer identifier could not be verified. Support access denied."
            )

        return cust

    @classmethod
    def normalize_event(
        cls,
        channel: str,
        sender: str,
        subject: str,
        body: str,
        customer_id: Optional[int] = None
    ) -> InboundSupportEvent:
        corr_id = f"CORR-{uuid.uuid4().hex[:8].upper()}"
        return InboundSupportEvent(
            event_id=f"EVT-{uuid.uuid4().hex[:6].upper()}",
            channel=channel.upper(),
            customer_id=customer_id,
            sender_identifier=sender,
            subject=subject,
            raw_payload=body,
            correlation_id=corr_id,
            timestamp=datetime.utcnow()
        )


channel_normalizer = ChannelNormalizer()
