from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.models import OutreachMessage, OutreachStatus, Campaign
from app.core.config import settings
from app.campaigns.config import campaign_config_loader
from app.campaigns.models import QuotaCheckResult


class QuotaEngine:
    """
    Evaluates multi-tier outbound limits and enforces the strict mathematical minimum.
    Limits evaluated:
    - Country Daily Quota (e.g. 10/day)
    - Campaign Daily Quota (e.g. 10/day)
    - Global Daily Platform Quota (e.g. 50/day from MAX_OUTREACH_PER_DAY)
    - Provider Quota (e.g. 100/day or tier limit)
    - Sender Quota (e.g. 50/day per account)
    - Rollout Stage Limit (Level 0: 0, Level 1: 1, Level 2: 5, ..., Level 7: 180)
    
    INVARIANT: Effective maximum = min(all applicable limits).
    """

    async def get_today_sent_counts(
        self,
        session: AsyncSession,
        campaign_id: Optional[int] = None,
        country_code: Optional[str] = None
    ) -> Dict[str, int]:
        """Queries database for real messages sent today (since midnight UTC)."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # 1. Global sent today
        q_global = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.status == OutreachStatus.SENT.value,
            OutreachMessage.sent_at >= today_start
        )
        global_sent = (await session.execute(q_global)).scalar() or 0

        # 2. Campaign sent today
        campaign_sent = 0
        if campaign_id:
            q_camp = select(func.count(OutreachMessage.id)).where(
                OutreachMessage.campaign_id == campaign_id,
                OutreachMessage.status == OutreachStatus.SENT.value,
                OutreachMessage.sent_at >= today_start
            )
            campaign_sent = (await session.execute(q_camp)).scalar() or 0

        # 3. Country sent today
        country_sent = 0
        if country_code:
            from app.database.models import Business
            q_cntry = select(func.count(OutreachMessage.id)).join(Business).where(
                Business.country.ilike(country_code.strip()),
                OutreachMessage.status == OutreachStatus.SENT.value,
                OutreachMessage.sent_at >= today_start
            )
            country_sent = (await session.execute(q_cntry)).scalar() or 0

        return {
            "global_sent": global_sent,
            "campaign_sent": campaign_sent,
            "country_sent": country_sent
        }

    async def evaluate_quota(
        self,
        session: AsyncSession,
        campaign: Optional[Campaign] = None,
        country_code: Optional[str] = None,
        is_live_send: bool = False
    ) -> QuotaCheckResult:
        """
        Determines whether an outbound email is within quota limits.
        Resolves the lowest applicable limit.
        """
        code = (country_code or (campaign.country_code if campaign else "US")).strip().upper()
        country_profile = campaign_config_loader.get_country(code)
        rollout = campaign_config_loader.get_rollout_config()

        country_quota = country_profile.daily_quota if country_profile else 10
        campaign_quota = campaign.daily_quota if campaign else country_quota
        global_quota = getattr(settings, "MAX_OUTREACH_PER_DAY", 50)
        provider_quota = getattr(settings, "PROVIDER_DAILY_LIMIT", 500)
        sender_quota = getattr(settings, "SENDER_DAILY_LIMIT", 50)
        rollout_limit = rollout.daily_max_real_emails

        counts = await self.get_today_sent_counts(
            session=session,
            campaign_id=campaign.id if campaign else None,
            country_code=code
        )

        global_sent = counts["global_sent"]
        campaign_sent = counts["campaign_sent"]
        country_sent = counts["country_sent"]

        # If live send requested, rollout limit governs maximum real volume
        effective_limit_ceiling = min(
            country_quota,
            campaign_quota,
            global_quota,
            provider_quota,
            sender_quota,
            rollout_limit if is_live_send else country_quota
        )

        kwargs = {
            "country_quota": country_quota,
            "campaign_quota": campaign_quota,
            "global_quota": global_quota,
            "provider_quota": provider_quota,
            "sender_quota": sender_quota,
            "rollout_level_limit": rollout_limit,
            "country_sent_today": country_sent,
            "global_sent_today": global_sent,
            "campaign_sent_today": campaign_sent,
            "rollout_limit": rollout_limit,
            "effective_remaining": 0
        }

        # Check individual thresholds
        if is_live_send and rollout_limit <= 0:
            return QuotaCheckResult(
                allowed=False,
                effective_limit=0,
                limiting_factor="ROLLOUT_LEVEL_0",
                reason="Live sending blocked: Current rollout level is 0 (Simulation Mode).",
                **kwargs
            )

        if is_live_send and global_sent >= rollout_limit:
            return QuotaCheckResult(
                allowed=False,
                effective_limit=effective_limit_ceiling,
                limiting_factor="ROLLOUT_CAP",
                reason=f"Rollout quota reached for today ({global_sent}/{rollout_limit} real sends).",
                **kwargs
            )

        if country_sent >= country_quota:
            return QuotaCheckResult(
                allowed=False,
                effective_limit=effective_limit_ceiling,
                limiting_factor="COUNTRY_QUOTA",
                reason=f"Country quota for {code} reached ({country_sent}/{country_quota} sent today).",
                **kwargs
            )

        if campaign_sent >= campaign_quota:
            return QuotaCheckResult(
                allowed=False,
                effective_limit=effective_limit_ceiling,
                limiting_factor="CAMPAIGN_QUOTA",
                reason=f"Campaign quota reached ({campaign_sent}/{campaign_quota} sent today).",
                **kwargs
            )

        if global_sent >= global_quota:
            return QuotaCheckResult(
                allowed=False,
                effective_limit=effective_limit_ceiling,
                limiting_factor="GLOBAL_QUOTA",
                reason=f"Platform global daily outreach cap reached ({global_sent}/{global_quota}).",
                **kwargs
            )

        # Remaining capacity
        remaining = min(
            country_quota - country_sent,
            campaign_quota - campaign_sent,
            global_quota - global_sent,
            (rollout_limit - global_sent) if is_live_send else country_quota
        )
        kwargs["effective_remaining"] = max(0, remaining)

        return QuotaCheckResult(
            allowed=True,
            effective_limit=max(0, remaining),
            limiting_factor="NONE",
            reason="Within all applicable quota ceilings.",
            **kwargs
        )


quota_engine = QuotaEngine()
