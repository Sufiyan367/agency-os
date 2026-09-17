from datetime import datetime, date
from typing import Optional, Any
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
            safe_email = email_clean or (f"phone_suppressed_{norm_phone.replace('+', '')}@suppressed.local" if norm_phone else "suppressed@suppressed.local")
            item = SuppressionList(email=safe_email, phone=norm_phone, domain=dom, reason=reason)
            session.add(item)
            await session.commit()

    async def can_send_today(self, session: AsyncSession) -> bool:
        from app.core.config import get_today_window_start
        today_start = get_today_window_start()
        q = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.status == OutreachStatus.SENT.value,
            OutreachMessage.sent_at >= today_start
        )
        count = (await session.execute(q)).scalar() or 0
        return count < settings.MAX_OUTREACH_PER_DAY

    KNOWN_PLACEHOLDERS = [
        "100 innovation way",
        "100 congress ave",
        "wilmington, de",
        "austin, tx",
        "al faisaliah",
        "digital strategy advisory",
        "riyadh 12212",
        "riyadh",
        "controllable business mailing address",
        "placeholder",
        "suite 2000",
        "anytown",
    ]

    def is_placeholder_address(self, addr: Optional[str]) -> bool:
        if not addr:
            return True
        addr_lower = addr.lower().strip()
        return any(p in addr_lower for p in self.KNOWN_PLACEHOLDERS)

    def is_postal_address_valid(self, postal_address: Optional[str] = None) -> bool:
        addr = (postal_address or getattr(settings, "PHYSICAL_POSTAL_ADDRESS", None) or getattr(settings, "CAN_SPAM_POSTAL_ADDRESS", None) or "").strip()
        if not addr or len(addr) < 10:
            return False
        if self.is_placeholder_address(addr):
            return False
        return True

    def format_compliance_footer(
        self,
        business_name: Optional[str] = None,
        recipient_email: Optional[str] = None,
        postal_address: Optional[str] = None,
        profile: Optional[Any] = None,
        force: bool = False
    ) -> str:
        """
        Renders compliance footer based on an explicit ComplianceProfile or campaign policy.
        If compliance profile is not enabled and force is False, returns empty string (signature only).
        Never exposes internal technical descriptions or unconfigured personas.
        """
        if profile is not None:
            if not getattr(profile, "enabled", False):
                return ""
            return profile.render_footer()

        # If no explicit profile passed, check settings toggle or forced campaign mandate
        if not force and not getattr(settings, "COMPLIANCE_PROFILE_ENABLED", False):
            return ""

        candidate_addr = postal_address
        if candidate_addr and self.is_placeholder_address(candidate_addr):
            candidate_addr = None

        env_addr = getattr(settings, "PHYSICAL_POSTAL_ADDRESS", None) or getattr(settings, "CAN_SPAM_POSTAL_ADDRESS", None)
        if env_addr and self.is_placeholder_address(env_addr):
            env_addr = None

        addr = (candidate_addr or env_addr or "").strip()
        parts = []
        if addr and not self.is_placeholder_address(addr):
            parts.append(f"Mailing Address: {addr}")
        parts.append("To opt out of future communications, reply 'unsubscribe'.")
        return "\n\n---\n" + "\n".join(parts)

compliance_guard = ComplianceGuard()
