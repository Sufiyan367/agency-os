from typing import Dict, Any, Optional
import httpx
from app.outreach.providers.base import BaseEmailProvider
from app.core.config import settings
from app.core.retry import async_retry
from app.core.logging import logger

class SendGridEmailProvider(BaseEmailProvider):
    """
    Transmits emails via SendGrid v3 Mail Send API.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.SENDGRID_API_KEY
        self.api_url = "https://api.sendgrid.com/v3/mail/send"

    @async_retry(max_retries=3, base_delay=1.0, exceptions=(httpx.HTTPError,))
    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("SENDGRID_API_KEY is not configured in .env")

        sender_addr = from_email or settings.OUTREACH_FROM_EMAIL
        sender_name = from_name or settings.OUTREACH_FROM_NAME

        content = [{"type": "text/plain", "value": body}]
        if html_body:
            content.append({"type": "text/html", "value": html_body})

        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": sender_addr, "name": sender_name},
            "subject": subject,
            "content": content
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.api_url, json=payload, headers=headers)
            if resp.status_code not in (200, 202):
                logger.error(f"[SendGrid] API error {resp.status_code}: {resp.text}")
                raise httpx.HTTPStatusError(
                    f"SendGrid error: {resp.status_code}", request=resp.request, response=resp
                )

            sg_msg_id = resp.headers.get("X-Message-Id", "sg_accepted")
            logger.info(f"[SendGrid] Email queued successfully to {to_email} (Msg ID: {sg_msg_id})")

            return {
                "status": "SUCCESS",
                "provider": "sendgrid",
                "message_id": sg_msg_id,
                "event": "sendgrid_delivered",
                "details": {"status_code": resp.status_code, "headers": dict(resp.headers)}
            }
