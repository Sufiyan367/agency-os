from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.models import SuppressionList, OutreachMessage, OutreachStatus
from app.core.config import settings
from app.core.security import normalize_domain

class ComplianceGuard:
    """
    Ensures strict adherence to email compliance:
    - Checks suppression list (bounced, unsubscribed, spam reports)
    - Enforces daily outreach limits (MAX_OUTREACH_PER_DAY)
    - Appends legally compliant B2B identification and opt-out footer
    """
    async def is_suppressed(self, session: AsyncSession, email: str) -> bool:
        if not email:
            return True
        email_clean = email.strip().lower()
        domain = normalize_domain(email_clean.split("@")[-1])

        q = select(SuppressionList).where(
            (SuppressionList.email == email_clean) | (SuppressionList.domain == domain)
        )
        result = await session.execute(q)
        return result.scalar_one_or_none() is not None

    async def add_to_suppression(self, session: AsyncSession, email: str, reason: str = "UNSUBSCRIBE"):
        email_clean = email.strip().lower()
        domain = normalize_domain(email_clean.split("@")[-1])
        
        q = select(SuppressionList).where(SuppressionList.email == email_clean)
        existing = (await session.execute(q)).scalar_one_or_none()
        if not existing:
            item = SuppressionList(email=email_clean, domain=domain, reason=reason)
            session.add(item)
            await session.commit()

    async def can_send_today(self, session: AsyncSession) -> bool:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        q = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.status == OutreachStatus.SENT.value,
            OutreachMessage.sent_at >= today_start
        )
        count = (await session.execute(q)).scalar() or 0
        return count < settings.MAX_OUTREACH_PER_DAY

    def format_compliance_footer(self, business_name: str, recipient_email: str) -> str:
        return (
            f"\n\n---\n"
            f"Sent by {settings.OUTREACH_FROM_NAME} on behalf of digital engineering advisory.\n"
            f"We contacted this public address ({recipient_email}) regarding public web infrastructure for {business_name}.\n"
            f"If you prefer not to receive future technical suggestions, simply reply 'unsubscribe' or 'opt out' to be permanently excluded."
        )

compliance_guard = ComplianceGuard()
