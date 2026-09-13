"""
WhatsApp Business Platform (Cloud API) Adapter.

Integrates with Meta's official WhatsApp Business Platform Cloud API schema.
Follows strict compliance guards:
1. Public phone numbers alone NEVER confer marketing consent.
2. Unsolicited outbound messages are strictly prohibited.
3. Cold outreach is blocked unless explicit opt-in consent is verified.
4. Handles delivery status webhooks (sent, delivered, read, failed) and incoming messages.
5. Inbound opt-out keywords (STOP, UNSUBSCRIBE, CANCEL) trigger automatic suppression.
6. Zero real outbound messages in test or unconfigured environments (DRY_RUN safe).
"""
import os
import re
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import logger
from app.outreach.whatsapp_compliance import (
    evaluate_whatsapp_eligibility,
    can_dispatch_whatsapp,
    WhatsAppEligibilityStatus
)
from app.database.models import (
    ChannelType,
    EventDirection,
    ConversationEventType
)


class WhatsAppDispatchResult(BaseModel):
    success: bool
    message_id: str
    recipient_phone: str
    status: str
    dry_run: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WhatsAppAdapter:
    """
    Adapter for WhatsApp Business Platform / Cloud API.
    Enforces compliance gates before dispatching.
    Normalizes provider webhooks and status callbacks into ConversationEvents.
    """

    def __init__(
        self,
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
        verify_token: Optional[str] = None,
        business_account_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        api_version: str = "v18.0",
        dry_run: Optional[bool] = None
    ):
        self.phone_number_id = phone_number_id or getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "") or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.access_token = access_token or getattr(settings, "WHATSAPP_ACCESS_TOKEN", "") or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        self.verify_token = verify_token or getattr(settings, "WHATSAPP_VERIFY_TOKEN", "agency_os_wa_verify_token")
        self.business_account_id = business_account_id or getattr(settings, "WHATSAPP_BUSINESS_ACCOUNT_ID", "") or os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
        self.app_secret = app_secret or getattr(settings, "WHATSAPP_APP_SECRET", "") or os.getenv("WHATSAPP_APP_SECRET", "")
        self.api_version = api_version
        self.dry_run = dry_run if dry_run is not None else getattr(settings, "WHATSAPP_DRY_RUN", True)

    def verify_webhook(
        self,
        mode: Optional[str],
        token: Optional[str],
        challenge: Optional[str]
    ) -> Optional[str]:
        """
        Handles Meta WhatsApp Webhook verification handshake (hub.mode, hub.verify_token, hub.challenge).
        """
        if mode == "subscribe" and token == self.verify_token:
            return challenge
        return None

    def verify_signature(self, payload_bytes: bytes, signature_header: Optional[str]) -> bool:
        """
        Validates Meta WhatsApp Cloud API X-Hub-Signature-256 header using app secret.
        Format: sha256=<hex_digest>
        """
        if not self.app_secret:
            # If no secret configured in dry-run mode, permit for mock testing
            return True if self.dry_run else False

        if not signature_header or not signature_header.startswith("sha256="):
            return False

        expected_hash = hmac.new(
            self.app_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        provided_hash = signature_header[7:].strip()
        return hmac.compare_digest(expected_hash, provided_hash)

    def validate_webhook_payload(self, payload: Any) -> Tuple[bool, Optional[str]]:
        """
        Validates structural integrity of an incoming WhatsApp Cloud API webhook JSON payload.
        Returns (is_valid, error_reason).
        """
        if not isinstance(payload, dict):
            return False, "Payload must be a JSON object"

        object_type = payload.get("object")
        if object_type != "whatsapp_business_account":
            return False, f"Invalid object type '{object_type}'; expected 'whatsapp_business_account'"

        entries = payload.get("entry")
        if not isinstance(entries, list) or len(entries) == 0:
            return False, "Malformed payload: 'entry' must be a non-empty array"

        return True, None

    def _clean_phone(self, phone: str) -> str:
        """Strips non-digit characters for WhatsApp international format."""
        return re.sub(r"[^\d]", "", (phone or "").strip())

    async def send_template(
        self,
        recipient_phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List[Dict[str, Any]]] = None,
        business: Optional[Any] = None,
        contact: Optional[Any] = None
    ) -> WhatsAppDispatchResult:
        """
        Dispatches a pre-approved WhatsApp Business Platform message template.
        Strictly requires verified opt-in consent.
        """
        cleaned_phone = self._clean_phone(recipient_phone)
        if not cleaned_phone:
            return WhatsAppDispatchResult(
                success=False,
                message_id="",
                recipient_phone=recipient_phone,
                status="FAILED",
                error="Recipient phone number is invalid or empty."
            )

        # Compliance gate: check business or contact consent
        target = contact or business
        if not can_dispatch_whatsapp(target):
            reason = "Blocked by WhatsApp Compliance Guard: No explicit opt-in consent recorded."
            logger.warning(f"[WhatsAppAdapter] {reason} (phone: {cleaned_phone})")
            return WhatsAppDispatchResult(
                success=False,
                message_id="",
                recipient_phone=cleaned_phone,
                status="BLOCKED_NO_CONSENT",
                dry_run=self.dry_run,
                error=reason
            )

        # Simulated message ID for idempotency and tracking
        sim_id = f"wamid.HBgL{cleaned_phone[-6:]}{int(datetime.utcnow().timestamp())}"

        if self.dry_run or not self.phone_number_id or not self.access_token:
            logger.info(
                f"[WhatsAppAdapter] [SIMULATED TEMPLATE] To: {cleaned_phone} | Template: {template_name} | "
                f"Lang: {language_code} | Components: {len(components or [])}"
            )
            return WhatsAppDispatchResult(
                success=True,
                message_id=sim_id,
                recipient_phone=cleaned_phone,
                status="SENT",
                dry_run=True,
                metadata={
                    "type": "template",
                    "template_name": template_name,
                    "language_code": language_code,
                    "components": components or []
                }
            )

        # Live Meta Cloud API dispatch
        import httpx
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": cleaned_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components or []
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    msg_id = data.get("messages", [{}])[0].get("id", sim_id)
                    return WhatsAppDispatchResult(
                        success=True,
                        message_id=msg_id,
                        recipient_phone=cleaned_phone,
                        status="SENT",
                        dry_run=False,
                        metadata=data
                    )
                else:
                    return WhatsAppDispatchResult(
                        success=False,
                        message_id="",
                        recipient_phone=cleaned_phone,
                        status="FAILED",
                        dry_run=False,
                        error=f"WhatsApp Cloud API error {resp.status_code}: {resp.text}"
                    )
        except Exception as e:
            logger.error(f"[WhatsAppAdapter] Dispatch error: {e}")
            return WhatsAppDispatchResult(
                success=False,
                message_id="",
                recipient_phone=cleaned_phone,
                status="FAILED",
                dry_run=False,
                error=str(e)
            )

    async def send_message(
        self,
        recipient_phone: str,
        text: str,
        business: Optional[Any] = None,
        contact: Optional[Any] = None
    ) -> WhatsAppDispatchResult:
        """
        Sends a free-form WhatsApp session message (only valid within 24-hour customer service window).
        """
        cleaned_phone = self._clean_phone(recipient_phone)
        if not cleaned_phone:
            return WhatsAppDispatchResult(
                success=False,
                message_id="",
                recipient_phone=recipient_phone,
                status="FAILED",
                error="Invalid recipient phone."
            )

        target = contact or business
        if not can_dispatch_whatsapp(target):
            return WhatsAppDispatchResult(
                success=False,
                message_id="",
                recipient_phone=cleaned_phone,
                status="BLOCKED_NO_CONSENT",
                dry_run=self.dry_run,
                error="Blocked: Contact lacks verified WhatsApp opt-in consent."
            )

        sim_id = f"wamid.HBgL{cleaned_phone[-6:]}{int(datetime.utcnow().timestamp())}"

        if self.dry_run or not self.phone_number_id or not self.access_token:
            logger.info(f"[WhatsAppAdapter] [SIMULATED MESSAGE] To: {cleaned_phone} | Body: {text[:60]}...")
            return WhatsAppDispatchResult(
                success=True,
                message_id=sim_id,
                recipient_phone=cleaned_phone,
                status="SENT",
                dry_run=True,
                metadata={"type": "text", "body_preview": text[:100]}
            )

        import httpx
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": cleaned_phone,
            "type": "text",
            "text": {"body": text}
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    msg_id = data.get("messages", [{}])[0].get("id", sim_id)
                    return WhatsAppDispatchResult(
                        success=True,
                        message_id=msg_id,
                        recipient_phone=cleaned_phone,
                        status="SENT",
                        dry_run=False,
                        metadata=data
                    )
                else:
                    return WhatsAppDispatchResult(
                        success=False,
                        message_id="",
                        recipient_phone=cleaned_phone,
                        status="FAILED",
                        dry_run=False,
                        error=f"WhatsApp Cloud API error {resp.status_code}: {resp.text}"
                    )
        except Exception as e:
            return WhatsAppDispatchResult(
                success=False,
                message_id="",
                recipient_phone=cleaned_phone,
                status="FAILED",
                dry_run=False,
                error=str(e)
            )

    def parse_webhook_payload(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parses standard Meta WhatsApp Cloud API webhook JSON into a list of normalized events.
        Handles both message delivery status callbacks and incoming user messages.
        """
        events = []
        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                
                # 1. Process Status Updates (sent, delivered, read, failed)
                statuses = value.get("statuses", [])
                for status_item in statuses:
                    msg_id = status_item.get("id", "")
                    raw_status = (status_item.get("status") or "").lower()
                    recipient = status_item.get("recipient_id", "")
                    timestamp_str = status_item.get("timestamp", "")
                    errors = status_item.get("errors", [])

                    event_type = ConversationEventType.SENT.value
                    if raw_status == "delivered":
                        event_type = ConversationEventType.DELIVERED.value
                    elif raw_status == "read":
                        event_type = ConversationEventType.READ.value
                    elif raw_status == "failed":
                        event_type = ConversationEventType.FAILED.value

                    idempotency_key = f"wa_status_{msg_id}_{raw_status}"

                    events.append({
                        "channel": ChannelType.WHATSAPP.value,
                        "direction": EventDirection.OUTBOUND.value,
                        "event_type": event_type,
                        "provider": "whatsapp_cloud",
                        "provider_event_id": msg_id,
                        "idempotency_key": idempotency_key,
                        "recipient": recipient,
                        "content": f"WhatsApp message {msg_id} status: {raw_status}",
                        "metadata_json": {
                            "raw_status": raw_status,
                            "timestamp": timestamp_str,
                            "errors": errors,
                            "raw_payload": status_item
                        }
                    })

                # 2. Process Incoming Messages
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])
                sender_name = contacts[0].get("profile", {}).get("name", "") if contacts else ""

                for msg_item in messages:
                    msg_id = msg_item.get("id", "")
                    from_phone = msg_item.get("from", "")
                    msg_type = msg_item.get("type", "text")
                    timestamp_str = msg_item.get("timestamp", "")

                    body = ""
                    if msg_type == "text":
                        body = msg_item.get("text", {}).get("body", "")
                    elif msg_type == "button":
                        body = msg_item.get("button", {}).get("text", "")
                    elif msg_type == "interactive":
                        interactive = msg_item.get("interactive", {})
                        body = interactive.get("button_reply", {}).get("title") or interactive.get("list_reply", {}).get("title", "")

                    # Check for opt-out keywords
                    is_opt_out = bool(re.search(r"\b(stop|unsubscribe|cancel|quit|arret)\b", body.lower()))
                    idempotency_key = f"wa_inbound_{msg_id}"

                    events.append({
                        "channel": ChannelType.WHATSAPP.value,
                        "direction": EventDirection.INBOUND.value,
                        "event_type": ConversationEventType.RECEIVED.value,
                        "provider": "whatsapp_cloud",
                        "provider_event_id": msg_id,
                        "idempotency_key": idempotency_key,
                        "sender": from_phone,
                        "sender_name": sender_name,
                        "content": body,
                        "metadata_json": {
                            "message_type": msg_type,
                            "timestamp": timestamp_str,
                            "is_opt_out": is_opt_out,
                            "raw_payload": msg_item
                        }
                    })

        return events


# Global singleton instance
whatsapp_adapter = WhatsAppAdapter()
