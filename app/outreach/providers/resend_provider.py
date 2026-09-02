from typing import Dict, Any, Optional
import httpx
from app.outreach.providers.base import BaseEmailProvider
from app.core.config import settings
from app.core.retry import async_retry
from app.core.logging import logger

class ResendEmailProvider(BaseEmailProvider):
    """
    Transmits emails via Resend REST API (https://resend.com).
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.RESEND_API_KEY
        self.api_url = "https://api.resend.com/emails"

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
            raise ValueError("RESEND_API_KEY is not configured in .env")

        sender_addr = from_email or settings.OUTREACH_FROM_EMAIL
        sender_name = from_name or settings.OUTREACH_FROM_NAME
        from_header = f"{sender_name} <{sender_addr}>"

        payload = {
            "from": from_header,
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        if html_body:
            payload["html"] = html_body

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.api_url, json=payload, headers=headers)
            if resp.status_code not in (200, 201):
                logger.error(f"[Resend] API error {resp.status_code}: {resp.text}")
                raise httpx.HTTPStatusError(
                    f"Resend error: {resp.status_code}", request=resp.request, response=resp
                )

            data = resp.json()
            message_id = data.get("id")
            logger.info(f"[Resend] Email sent successfully to {to_email} (ID: {message_id})")

            return {
                "status": "SUCCESS",
                "provider": "resend",
                "message_id": message_id,
                "event": "resend_delivered",
                "details": data
            }
