from datetime import datetime
import uuid
from typing import Dict, Any, Optional
from app.outreach.providers.base import BaseEmailProvider
from app.core.config import settings
from app.core.logging import logger

class DryRunEmailProvider(BaseEmailProvider):
    """
    Safe simulated email delivery provider.
    Logs realistic transmission records without opening external network sockets.
    """

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
        simulated_id = f"dry_run_{uuid.uuid4().hex[:12]}"
        logger.info(f"[DRY_RUN SENDER] Simulated email transmission to {to_email} | Subject: '{subject[:40]}...'")
        return {
            "status": "SUCCESS",
            "provider": "dry_run",
            "message_id": simulated_id,
            "event": "dry_run_simulated",
            "details": {
                "dry_run": True,
                "simulated_at": datetime.utcnow().isoformat(),
                "to": to_email,
                "from": from_email,
                "from_name": from_name,
                "reply_to": reply_to or settings.EMAIL_REPLY_TO,
                "subject": subject
            }
        }

class MockEmailProvider(DryRunEmailProvider):
    """Alias for DryRunEmailProvider adhering to MockEmailProvider naming specification."""
    pass
