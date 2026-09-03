from datetime import datetime, date
from typing import Optional
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
    async def is_suppressed(
        self,
        session: AsyncSession,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        domain: Optional[str] = None
    ) -> bool:
        from sqlalchemy import or_
        from app.communications.voice_provider import format_e164_phone
        clauses = []
        if email:
            email_clean = email.strip().lower()
            dom = normalize_domain(email_clean.split("@")[-1])
            clauses.extend([SuppressionList.email == email_clean, SuppressionList.domain == dom])
        if domain:
            clauses.append(SuppressionList.domain == normalize_domain(domain))
        if phone:
            norm_phone = format_e164_phone(phone)
            if norm_phone:
                clauses.append(SuppressionList.phone == norm_phone)

        if not clauses:
            return False

        q = select(SuppressionList.id).where(or_(*clauses)).limit(1)
        result = await session.execute(q)
        return result.first() is not None

    async def add_to_suppression(
        self,
        session: AsyncSession,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        domain: Optional[str] = None,
        reason: str = "UNSUBSCRIBE"
    ):
        from app.communications.voice_provider import format_e164_phone
        email_clean = email.strip().lower() if email else None
        dom = domain or (normalize_domain(email_clean.split("@")[-1]) if email_clean else None)
        norm_phone = format_e164_phone(phone) if phone else None

        # Check existing
        is_supp = await self.is_suppressed(session, email=email_clean, phone=norm_phone, domain=dom)
        if not is_supp:
            item = SuppressionList(email=email_clean, phone=norm_phone, domain=dom, reason=reason)
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
