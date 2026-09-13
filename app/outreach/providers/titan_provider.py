import asyncio
import smtplib
import imaplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from app.outreach.providers.base import BaseEmailProvider
from app.core.config import settings
from app.core.logging import logger

def _sanitize_error(error: Exception, secret_strings: Optional[list] = None) -> str:
    """Sanitizes exception messages to ensure passwords and credentials are never exposed in logs or UI."""
    msg = str(error)
    secrets = secret_strings or [
        getattr(settings, "TITAN_SMTP_PASSWORD", None),
        getattr(settings, "TITAN_IMAP_PASSWORD", None),
        getattr(settings, "SMTP_PASSWORD", None),
        getattr(settings, "IMAP_PASSWORD", None)
    ]
    for s in secrets:
        if s and len(s) > 2 and s in msg:
            msg = msg.replace(s, "[REDACTED]")
    return msg

class TitanEmailProvider(BaseEmailProvider):
    """
    Dedicated Titan Business Email Provider.
    Supports secure transactional dispatch via Titan SMTP:
    - Port 465 (SSL/TLS direct)
    - Port 587 (STARTTLS)
    And IMAP inbox health auditing (Port 993 SSL).
    Never logs or leaks credentials.
    """

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        imap_host: Optional[str] = None,
        imap_port: Optional[int] = None,
        imap_user: Optional[str] = None,
        imap_password: Optional[str] = None
    ):
        self.smtp_host = smtp_host or getattr(settings, "TITAN_SMTP_HOST", "smtp.titan.email") or getattr(settings, "SMTP_HOST", "smtp.titan.email")
        self.smtp_port = smtp_port or getattr(settings, "TITAN_SMTP_PORT", 465) or getattr(settings, "SMTP_PORT", 465)
        self.smtp_user = smtp_user or getattr(settings, "TITAN_SMTP_USER", None) or getattr(settings, "SMTP_USER", None)
        self.smtp_password = smtp_password or getattr(settings, "TITAN_SMTP_PASSWORD", None) or getattr(settings, "SMTP_PASSWORD", None)

        self.imap_host = imap_host or getattr(settings, "TITAN_IMAP_HOST", "imap.titan.email") or getattr(settings, "IMAP_HOST", "imap.titan.email")
        self.imap_port = imap_port or getattr(settings, "TITAN_IMAP_PORT", 993) or getattr(settings, "IMAP_PORT", 993)
        self.imap_user = imap_user or getattr(settings, "TITAN_IMAP_USER", None) or getattr(settings, "IMAP_USER", None)
        self.imap_password = imap_password or getattr(settings, "TITAN_IMAP_PASSWORD", None) or getattr(settings, "IMAP_PASSWORD", None)

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
        if not self.smtp_host or not self.smtp_user or not self.smtp_password:
            raise ValueError("Titan SMTP configuration incomplete: Host, user, or password missing in configuration.")

        sender_addr = from_email or self.smtp_user or settings.EMAIL_FROM
        sender_name = from_name or settings.OUTREACH_FROM_NAME
        reply_to_addr = reply_to or self.smtp_user or settings.EMAIL_REPLY_TO

        if html_body:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")

        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{sender_addr}>"
        msg["To"] = to_email
        msg["Reply-To"] = reply_to_addr

        def _sync_send():
            if int(self.smtp_port) == 465:
                with smtplib.SMTP_SSL(self.smtp_host, int(self.smtp_port), timeout=12) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_host, int(self.smtp_port), timeout=12) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)

        try:
            await asyncio.to_thread(_sync_send)
        except Exception as e:
            safe_err = _sanitize_error(e, [self.smtp_password])
            logger.error(f"[TitanEmailProvider] Delivery failed to {to_email}: {safe_err}")
            raise RuntimeError(f"Titan SMTP delivery error: {safe_err}")

        logger.info(f"[TitanEmailProvider] Email successfully delivered to {to_email} via {self.smtp_host}:{self.smtp_port}")
        return {
            "status": "SUCCESS",
            "provider": "titan",
            "message_id": f"titan_{to_email}_{subject[:12]}",
            "event": "email_dispatched",
            "details": {
                "host": self.smtp_host,
                "port": self.smtp_port,
                "sender": sender_addr,
                "recipient": to_email
            }
        }

    def check_auth_health(self) -> Dict[str, Any]:
        """Validates Titan SMTP credentials and socket handshake without sending an email."""
        if not self.smtp_host or not self.smtp_user or not self.smtp_password:
            return {
                "status": "UNCONFIGURED",
                "healthy": False,
                "error": "Titan SMTP credentials not populated in configuration.",
                "authenticated_email": None
            }

        try:
            if int(self.smtp_port) == 465:
                with smtplib.SMTP_SSL(self.smtp_host, int(self.smtp_port), timeout=8) as server:
                    server.login(self.smtp_user, self.smtp_password)
            else:
                with smtplib.SMTP(self.smtp_host, int(self.smtp_port), timeout=8) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
            return {
                "status": "OK",
                "healthy": True,
                "authenticated_email": self.smtp_user,
                "host": self.smtp_host,
                "port": self.smtp_port
            }
        except Exception as e:
            safe_err = _sanitize_error(e, [self.smtp_password])
            return {
                "status": "ERROR",
                "healthy": False,
                "error": safe_err,
                "authenticated_email": self.smtp_user
            }

    def check_imap_health(self) -> Dict[str, Any]:
        """Validates Titan IMAP credentials and inbox read capability."""
        imap_user = self.imap_user or self.smtp_user
        imap_pass = self.imap_password or self.smtp_password
        if not self.imap_host or not imap_user or not imap_pass:
            return {
                "status": "UNCONFIGURED",
                "healthy": False,
                "error": "Titan IMAP credentials not configured.",
                "authenticated_email": None
            }

        try:
            with imaplib.IMAP4_SSL(self.imap_host, int(self.imap_port), timeout=8) as mail:
                mail.login(imap_user, imap_pass)
                stat, count = mail.select("INBOX", readonly=True)
                total_msgs = int(count[0]) if count and count[0] else 0
                return {
                    "status": "OK",
                    "healthy": True,
                    "authenticated_email": imap_user,
                    "inbox_messages_total": total_msgs
                }
        except Exception as e:
            safe_err = _sanitize_error(e, [imap_pass])
            return {
                "status": "ERROR",
                "healthy": False,
                "error": safe_err,
                "authenticated_email": imap_user
            }
