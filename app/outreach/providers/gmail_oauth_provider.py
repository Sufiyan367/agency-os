import base64
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional, List
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.outreach.providers.base import BaseEmailProvider
from app.core.config import settings
from app.core.logging import logger

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPES = [GMAIL_SEND_SCOPE, GMAIL_READONLY_SCOPE]


def _sanitize_error(error: Exception) -> str:
    """Sanitizes exception messages to ensure tokens or secrets are never exposed."""
    msg = str(error)
    # Strip any potential sensitive token strings
    for secret in [
        getattr(settings, "GMAIL_CLIENT_SECRET", None),
        getattr(settings, "GMAIL_REFRESH_TOKEN", None),
        getattr(settings, "GMAIL_CLIENT_ID", None)
    ]:
        if secret and len(secret) > 4 and secret in msg:
            msg = msg.replace(secret, "[REDACTED]")
    return msg


class GmailOAuthEmailProvider(BaseEmailProvider):
    """
    Enterprise-grade Gmail API email provider using OAuth2.
    Uses strictly granular, least-privilege scopes:
    - https://www.googleapis.com/auth/gmail.send
    - https://www.googleapis.com/auth/gmail.readonly
    Never requests or stores user passwords. All failures fail closed.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        sender_email: Optional[str] = None
    ):
        self.client_id = client_id if client_id is not None else getattr(settings, "GMAIL_CLIENT_ID", None)
        self.client_secret = client_secret if client_secret is not None else getattr(settings, "GMAIL_CLIENT_SECRET", None)
        self.refresh_token = refresh_token if refresh_token is not None else getattr(settings, "GMAIL_REFRESH_TOKEN", None)
        self.sender_email = sender_email if sender_email is not None else (getattr(settings, "GMAIL_SENDER_EMAIL", None) or getattr(settings, "EMAIL_FROM", None))

    def _get_credentials(self) -> Credentials:
        """Constructs Google OAuth2 Credentials from configured refresh token."""
        if not self.client_id:
            raise ValueError("Gmail OAuth configuration incomplete: GMAIL_CLIENT_ID is missing.")
        if not self.client_secret:
            raise ValueError("Gmail OAuth configuration incomplete: GMAIL_CLIENT_SECRET is missing.")
        if not self.refresh_token:
            raise ValueError("Gmail OAuth configuration incomplete: GMAIL_REFRESH_TOKEN is missing.")

        return Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=GMAIL_SCOPES
        )

    def get_service(self):
        """Constructs the Gmail Resource service client."""
        creds = self._get_credentials()
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def check_auth_health(self) -> Dict[str, Any]:
        """
        Validates Gmail OAuth credentials, connectivity, and sender identity without sending messages.
        Fails closed on any error. Never leaks tokens or secrets.
        """
        if not self.client_id or not self.client_secret or not self.refresh_token:
            return {
                "status": "ERROR",
                "healthy": False,
                "error": "Missing Gmail OAuth credentials in configuration.",
                "authenticated_email": None
            }

        try:
            service = self.get_service()
            profile = service.users().getProfile(userId="me").execute()
            authenticated_email = profile.get("emailAddress", "").lower().strip()

            # Verify identity match if configured
            expected_email = (self.sender_email or "").lower().strip()
            if expected_email and authenticated_email != expected_email:
                return {
                    "status": "ERROR",
                    "healthy": False,
                    "error": f"Gmail identity mismatch: token authorized for '{authenticated_email}' but configured sender is '{expected_email}'.",
                    "authenticated_email": authenticated_email
                }

            return {
                "status": "OK",
                "healthy": True,
                "authenticated_email": authenticated_email,
                "messages_total": profile.get("messagesTotal", 0),
                "threads_total": profile.get("threadsTotal", 0)
            }
        except Exception as e:
            sanitized = _sanitize_error(e)
            logger.error(f"[GmailOAuthProvider] Auth health check failed: {sanitized}")
            return {
                "status": "ERROR",
                "healthy": False,
                "error": f"Gmail API authentication failure: {sanitized}",
                "authenticated_email": None
            }

    def build_mime_message(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None
    ) -> Dict[str, Any]:
        """Builds an RFC 2822 MIME message and returns the raw base64url encoded payload."""
        effective_from_email = from_email or self.sender_email or getattr(settings, "EMAIL_FROM", "me")
        
        if html_body:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")

        msg["To"] = to_email
        msg["Subject"] = subject

        if from_name:
            msg["From"] = f"{from_name} <{effective_from_email}>"
        else:
            msg["From"] = effective_from_email

        effective_reply_to = reply_to or getattr(settings, "EMAIL_REPLY_TO", None) or effective_from_email
        if effective_reply_to:
            msg["Reply-To"] = effective_reply_to

        # Generate unique Message-ID
        domain = effective_from_email.split("@")[-1] if "@" in effective_from_email else "gmail.com"
        msg_id_header = f"<{uuid.uuid4()}@{domain}>"
        msg["Message-ID"] = msg_id_header

        # Thread headers
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        raw_bytes = msg.as_bytes()
        encoded_raw = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

        payload = {"raw": encoded_raw}
        if thread_id:
            payload["threadId"] = thread_id

        return {
            "payload": payload,
            "message_id_header": msg_id_header,
            "from_email": effective_from_email
        }

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends an email via Gmail API users.messages.send.
        Supports thread continuation and returns delivery metadata.
        Fails closed with sanitized error reporting.
        """
        # Build MIME payload
        try:
            mime_info = self.build_mime_message(
                to_email=to_email,
                subject=subject,
                body=body,
                html_body=html_body,
                from_email=from_email,
                from_name=from_name,
                reply_to=reply_to,
                thread_id=thread_id,
                in_reply_to=in_reply_to,
                references=references
            )
        except Exception as e:
            return {
                "status": "FAILED",
                "provider": "gmail",
                "message_id": None,
                "event": "email_delivery_failed",
                "details": {"error": f"MIME encoding error: {_sanitize_error(e)}"}
            }

        try:
            service = self.get_service()
            result = service.users().messages().send(
                userId="me",
                body=mime_info["payload"]
            ).execute()

            gmail_msg_id = result.get("id")
            gmail_thread_id = result.get("threadId")

            return {
                "status": "SUCCESS",
                "provider": "gmail",
                "message_id": gmail_msg_id,
                "event": "email_dispatched",
                "details": {
                    "gmail_message_id": gmail_msg_id,
                    "gmail_thread_id": gmail_thread_id,
                    "message_id_header": mime_info["message_id_header"],
                    "to": to_email,
                    "subject": subject,
                    "from": mime_info["from_email"],
                    "label_ids": result.get("labelIds", [])
                }
            }
        except Exception as e:
            sanitized = _sanitize_error(e)
            logger.error(f"[GmailOAuthProvider] Message transmission failed: {sanitized}")
            return {
                "status": "FAILED",
                "provider": "gmail",
                "message_id": None,
                "event": "email_delivery_failed",
                "details": {"error": f"Gmail API error: {sanitized}"}
            }

    def list_unread_messages(self, max_results: int = 20) -> List[Dict[str, Any]]:
        """Lists unread incoming messages using Gmail API with readonly scope."""
        try:
            service = self.get_service()
            res = service.users().messages().list(
                userId="me",
                q="is:unread",
                maxResults=max_results
            ).execute()
            return res.get("messages", [])
        except Exception as e:
            logger.warning(f"[GmailOAuthProvider] list_unread_messages error: {_sanitize_error(e)}")
            return []

    def get_message_detail(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Fetches and parses a specific Gmail message."""
        try:
            service = self.get_service()
            msg = service.users().messages().get(
                userId="me",
                id=message_id,
                format="full"
            ).execute()
            return self.parse_gmail_message(msg)
        except Exception as e:
            logger.warning(f"[GmailOAuthProvider] get_message_detail error for {message_id}: {_sanitize_error(e)}")
            return None

    def get_thread_detail(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Fetches thread details to inspect all messages in a conversation."""
        try:
            service = self.get_service()
            thread = service.users().threads().get(
                userId="me",
                id=thread_id,
                format="full"
            ).execute()
            return thread
        except Exception as e:
            logger.warning(f"[GmailOAuthProvider] get_thread_detail error for {thread_id}: {_sanitize_error(e)}")
            return None

    @staticmethod
    def parse_gmail_message(msg: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts headers, sender, threadId, and text body from a Gmail API message resource."""
        headers_list = msg.get("payload", {}).get("headers", [])
        headers = {h.get("name", "").lower(): h.get("value", "") for h in headers_list}

        sender = headers.get("from", "")
        # Extract pure email
        import email.utils
        _, sender_email = email.utils.parseaddr(sender)

        # Body decoding
        body_text = ""
        payload = msg.get("payload", {})
        
        def _extract_body_parts(part):
            nonlocal body_text
            mime_type = part.get("mimeType", "")
            data = part.get("body", {}).get("data")
            if mime_type == "text/plain" and data:
                try:
                    body_text += base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                except Exception:
                    pass
            elif "parts" in part:
                for subpart in part["parts"]:
                    _extract_body_parts(subpart)

        _extract_body_parts(payload)

        return {
            "id": msg.get("id"),
            "threadId": msg.get("threadId"),
            "sender_email": sender_email.lower().strip(),
            "from_header": sender,
            "subject": headers.get("subject", ""),
            "message_id": headers.get("message-id", ""),
            "in_reply_to": headers.get("in-reply-to", ""),
            "references": headers.get("references", ""),
            "date": headers.get("date", ""),
            "body": body_text.strip(),
            "snippet": msg.get("snippet", "")
        }
