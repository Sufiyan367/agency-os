"""
Email Channel Adapter.

Bridges modular email providers (DryRun, Gmail OAuth, SMTP, Resend, SendGrid)
and incoming reply handlers into the unified ConversationEvent stream.
Handles:
1. Outbound dispatch normalization (SENT, FAILED).
2. Incoming prospect reply normalization (REPLIED).
3. Provider webhook parsing for delivery statuses (DELIVERED, BOUNCED, FAILED).
"""
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.database.models import (
    ChannelType,
    EventDirection,
    ConversationEventType,
    OutreachMessage,
    Reply
)
from app.core.logging import logger


class EmailAdapter:
    """
    Adapter bridging email dispatches, incoming replies, and provider delivery webhooks
    into unified ConversationEvents.
    """

    def normalize_outreach_send(
        self,
        msg: OutreachMessage,
        provider_name: str = "outreach_sender",
        provider_msg_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates normalized event dictionary for an outbound email send.
        """
        msg_id_str = str(provider_msg_id or msg.provider_message_id or f"msg_{msg.id}")
        idempotency_key = f"email_send_{msg.id}_{msg_id_str}"

        return {
            "channel": ChannelType.EMAIL.value,
            "direction": EventDirection.OUTBOUND.value,
            "event_type": ConversationEventType.SENT.value,
            "provider": provider_name,
            "provider_event_id": msg_id_str,
            "idempotency_key": idempotency_key,
            "recipient": msg.recipient_email,
            "content": f"Subject: {msg.subject}\n\n{msg.body}",
            "metadata_json": {
                "outreach_message_id": msg.id,
                "recipient_email": msg.recipient_email,
                "subject": msg.subject,
                "sent_at": msg.sent_at.isoformat() if msg.sent_at else datetime.utcnow().isoformat()
            }
        }

    def normalize_incoming_reply(
        self,
        reply: Reply,
        provider_name: str = "inbound_email"
    ) -> Dict[str, Any]:
        """
        Creates normalized event dictionary for an incoming prospect reply.
        """
        reply_id_str = str(reply.id or hashlib.md5(f"{reply.business_id}_{reply.sender_email}_{reply.created_at}".encode()).hexdigest()[:16])
        idempotency_key = f"email_reply_{reply_id_str}"

        return {
            "channel": ChannelType.EMAIL.value,
            "direction": EventDirection.INBOUND.value,
            "event_type": ConversationEventType.REPLIED.value,
            "provider": provider_name,
            "provider_event_id": reply_id_str,
            "idempotency_key": idempotency_key,
            "sender": reply.sender_email,
            "content": reply.raw_body,
            "metadata_json": {
                "reply_id": reply.id,
                "outreach_message_id": reply.outreach_message_id,
                "sender_email": reply.sender_email,
                "classification": reply.classification,
                "confidence": reply.confidence,
                "suggested_response": reply.suggested_response
            }
        }

    def parse_provider_webhook(
        self,
        provider: str,
        payload: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Parses delivery webhooks from providers like Resend, SendGrid, or generic SMTP callbacks.
        """
        events = []
        p_lower = provider.lower()

        if "resend" in p_lower:
            # Resend webhook format: {"type": "email.delivered", "data": {"email_id": "...", "to": [...]}}
            evt_type_raw = payload.get("type", "")
            data = payload.get("data", {})
            email_id = data.get("email_id", "")
            recipients = data.get("to", [])

            mapped_type = ConversationEventType.SENT.value
            if "delivered" in evt_type_raw:
                mapped_type = ConversationEventType.DELIVERED.value
            elif "bounced" in evt_type_raw:
                mapped_type = ConversationEventType.BOUNCED.value
            elif "complained" in evt_type_raw:
                mapped_type = ConversationEventType.BOUNCED.value

            idempotency_key = f"resend_{email_id}_{evt_type_raw}"
            events.append({
                "channel": ChannelType.EMAIL.value,
                "direction": EventDirection.OUTBOUND.value,
                "event_type": mapped_type,
                "provider": "resend",
                "provider_event_id": email_id,
                "idempotency_key": idempotency_key,
                "recipient": recipients[0] if recipients else "",
                "content": f"Resend email {email_id} event: {evt_type_raw}",
                "metadata_json": payload
            })

        elif "sendgrid" in p_lower:
            # SendGrid webhook format is an array of events
            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                sg_event = item.get("event", "")
                sg_msg_id = item.get("sg_message_id", "")
                email = item.get("email", "")

                mapped_type = ConversationEventType.SENT.value
                if sg_event == "delivered":
                    mapped_type = ConversationEventType.DELIVERED.value
                elif sg_event in ("bounce", "dropped"):
                    mapped_type = ConversationEventType.BOUNCED.value
                elif sg_event in ("deferred",):
                    mapped_type = ConversationEventType.FAILED.value

                idempotency_key = f"sendgrid_{sg_msg_id}_{sg_event}"
                events.append({
                    "channel": ChannelType.EMAIL.value,
                    "direction": EventDirection.OUTBOUND.value,
                    "event_type": mapped_type,
                    "provider": "sendgrid",
                    "provider_event_id": sg_msg_id,
                    "idempotency_key": idempotency_key,
                    "recipient": email,
                    "content": f"SendGrid email event: {sg_event}",
                    "metadata_json": item
                })
        else:
            # Generic webhook
            evt_id = payload.get("id") or payload.get("message_id") or "generic_evt"
            raw_status = payload.get("status", "sent")
            events.append({
                "channel": ChannelType.EMAIL.value,
                "direction": EventDirection.OUTBOUND.value,
                "event_type": ConversationEventType.DELIVERED.value if raw_status == "delivered" else ConversationEventType.SENT.value,
                "provider": provider,
                "provider_event_id": str(evt_id),
                "idempotency_key": f"{provider}_{evt_id}_{raw_status}",
                "content": f"Email event: {raw_status}",
                "metadata_json": payload
            })

        return events


# Global singleton instance
email_adapter = EmailAdapter()
