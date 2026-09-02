import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from app.outreach.providers.base import BaseEmailProvider
from app.core.config import settings
from app.core.logging import logger

class SMTPEmailProvider(BaseEmailProvider):
    """
    Standard SMTP/TLS email provider supporting custom mail servers, Postmark, Mailgun, and AWS SES.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.host = host or settings.SMTP_HOST
        self.port = port or settings.SMTP_PORT
        self.user = user or settings.SMTP_USER
        self.password = password or settings.SMTP_PASSWORD

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.host or not self.user:
            raise ValueError("SMTP_HOST and SMTP_USER must be configured in .env for SMTP delivery.")

        sender_addr = from_email or settings.OUTREACH_FROM_EMAIL
        sender_name = from_name or settings.OUTREACH_FROM_NAME

        if html_body:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")

        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{sender_addr}>"
        msg["To"] = to_email

        def _sync_send():
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.send_message(msg)

        # Run synchronous socket I/O in worker thread to avoid blocking async event loop
        await asyncio.to_thread(_sync_send)
        logger.info(f"[SMTP] Email delivered to {to_email} via {self.host}:{self.port}")

        return {
            "status": "SUCCESS",
            "provider": "smtp",
            "message_id": f"smtp_{to_email}_{subject[:10]}",
            "event": "smtp_delivered",
            "details": {"host": self.host, "port": self.port, "to": to_email}
        }
