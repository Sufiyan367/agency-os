from app.outreach.providers.base import BaseEmailProvider
from app.outreach.providers.dry_run import DryRunEmailProvider
from app.outreach.providers.resend_provider import ResendEmailProvider
from app.outreach.providers.sendgrid_provider import SendGridEmailProvider
from app.outreach.providers.smtp_provider import SMTPEmailProvider
from app.core.config import settings
from app.core.logging import logger

def get_email_provider() -> BaseEmailProvider:
    """
    Resolves the active email provider based on settings.
    Respects EMAIL_DRY_RUN / DRY_RUN safety invariant:
    If EMAIL_DRY_RUN or DRY_RUN is True, always returns DryRunEmailProvider.
    """
    if settings.EMAIL_DRY_RUN or settings.DRY_RUN or settings.EMAIL_PROVIDER == "dry_run":
        return DryRunEmailProvider()

    provider_name = settings.EMAIL_PROVIDER.lower().strip()

    if provider_name == "resend":
        return ResendEmailProvider()
    elif provider_name == "sendgrid":
        return SendGridEmailProvider()
    elif provider_name == "smtp":
        return SMTPEmailProvider()
    else:
        logger.warning(f"Unknown EMAIL_PROVIDER '{provider_name}'. Falling back to DryRunEmailProvider.")
        return DryRunEmailProvider()
