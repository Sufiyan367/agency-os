from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.database.models import Campaign, CampaignEvent, OutreachMessage, OutreachStatus, Reply, Business
from app.campaigns.models import CampaignDTO, CountryProfileDTO, RolloutConfigDTO
from app.campaigns.config import campaign_config_loader
from app.campaigns.scheduler import campaign_scheduler
from app.campaigns.sender_registry import sender_registry
from app.core.logging import logger


class CampaignService:
    """Coordinates international campaigns, database persistence, and CEO metrics."""

    async def ensure_campaigns_seeded(self, session: AsyncSession) -> List[Campaign]:
        """Ensures all 18 configured international campaigns exist in the database."""
        countries = campaign_config_loader.list_countries()
        campaigns: List[Campaign] = []

        for c in countries:
            q = select(Campaign).where(Campaign.country_code == c.code.upper())
            existing = (await session.execute(q)).scalars().first()

            if not existing:
                camp = Campaign(
                    name=f"{c.name} Outbound Corridor",
                    country_code=c.code.upper(),
                    status="ACTIVE" if c.enabled else "PAUSED",
                    timezone=c.timezone,
                    daily_quota=c.daily_quota,
                    service_type="web_turnaround",
                    sender_identity=None,
                    sender_name=None,
                    reply_to=None,
                    postal_address=sender_registry.DEFAULT_POSTAL_ADDRESS,
                    sending_window_start=c.sending_window_start,
                    sending_window_end=c.sending_window_end,
                    approval_policy="MANUAL_CEO_APPROVAL",
                    enabled=c.enabled
                )
                session.add(camp)
                await session.flush()
                campaigns.append(camp)
                logger.info(f"[CampaignService] Seeded campaign '{camp.name}' ({c.code})")
            else:
                campaigns.append(existing)

        await session.commit()
        return campaigns

    async def list_campaigns(self, session: AsyncSession, include_stats: bool = True) -> List[CampaignDTO]:
        """Lists all campaigns enriched with today's quota, sent counts, and replies."""
        await self.ensure_campaigns_seeded(session)
        q = select(Campaign).order_by(Campaign.country_code.asc())
        records = (await session.execute(q)).scalars().all()

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        dtos: List[CampaignDTO] = []

        for camp in records:
            # Query stats
            q_sent_today = select(func.count(OutreachMessage.id)).where(
                OutreachMessage.campaign_id == camp.id,
                OutreachMessage.status == OutreachStatus.SENT.value,
                OutreachMessage.sent_at >= today_start
            )
            sent_today = (await session.execute(q_sent_today)).scalar() or 0

            q_total_sent = select(func.count(OutreachMessage.id)).where(
                OutreachMessage.campaign_id == camp.id,
                OutreachMessage.status == OutreachStatus.SENT.value
            )
            total_sent = (await session.execute(q_total_sent)).scalar() or 0

            # Replies via messages in this campaign
            q_replies = select(func.count(Reply.id)).join(OutreachMessage, Reply.outreach_message_id == OutreachMessage.id).where(
                OutreachMessage.campaign_id == camp.id
            )
            replies_cnt = (await session.execute(q_replies)).scalar() or 0

            q_interested = select(func.count(Reply.id)).join(OutreachMessage, Reply.outreach_message_id == OutreachMessage.id).where(
                OutreachMessage.campaign_id == camp.id,
                Reply.classification == "INTERESTED"
            )
            interested_cnt = (await session.execute(q_interested)).scalar() or 0

            # Bounces
            q_bounces = select(func.count(Reply.id)).join(OutreachMessage, Reply.outreach_message_id == OutreachMessage.id).where(
                OutreachMessage.campaign_id == camp.id,
                Reply.classification == "BOUNCE"
            )
            bounces_cnt = (await session.execute(q_bounces)).scalar() or 0
            bounce_rate = round((bounces_cnt / total_sent * 100), 1) if total_sent > 0 else 0.0

            # Timezone sending window check
            in_win, local_dt, hour, tz_name = campaign_scheduler.is_within_sending_window(
                country_code=camp.country_code,
                timezone_str=camp.timezone,
                window_start=camp.sending_window_start,
                window_end=camp.sending_window_end
            )

            c_prof = campaign_config_loader.get_country(camp.country_code)

            dtos.append(CampaignDTO(
                id=camp.id,
                name=camp.name,
                country_code=camp.country_code,
                country_name=c_prof.name if c_prof else camp.country_code,
                status=camp.status,
                timezone=camp.timezone,
                daily_quota=camp.daily_quota,
                service_type=camp.service_type,
                sender_identity=camp.sender_identity,
                sender_name=camp.sender_name,
                reply_to=camp.reply_to,
                postal_address=camp.postal_address,
                sending_window_start=camp.sending_window_start,
                sending_window_end=camp.sending_window_end,
                approval_policy=camp.approval_policy,
                enabled=camp.enabled,
                today_sent=sent_today,
                today_remaining=max(0, camp.daily_quota - sent_today),
                total_sent=total_sent,
                replies_count=replies_cnt,
                interested_count=interested_cnt,
                bounces_count=bounces_cnt,
                bounce_rate=bounce_rate,
                is_in_sending_window=in_win,
                local_time_formatted=f"{local_dt.strftime('%H:%M')} ({tz_name})",
                created_at=camp.created_at,
                updated_at=camp.updated_at
            ))

        return dtos

    async def get_campaign_by_country(self, session: AsyncSession, country_code: str) -> Optional[Campaign]:
        """Resolves campaign matching a business country."""
        await self.ensure_campaigns_seeded(session)
        code = (country_code or "US").strip().upper()
        q = select(Campaign).where(Campaign.country_code == code)
        return (await session.execute(q)).scalars().first()

    async def update_campaign(
        self,
        session: AsyncSession,
        campaign_id: int,
        updates: Dict[str, Any]
    ) -> Campaign:
        """Updates campaign configuration safely."""
        camp = await session.get(Campaign, campaign_id)
        if not camp:
            raise ValueError(f"Campaign #{campaign_id} not found.")

        for key in ["name", "status", "daily_quota", "timezone", "service_type", "sender_identity",
                    "sender_name", "reply_to", "postal_address", "sending_window_start",
                    "sending_window_end", "approval_policy", "enabled"]:
            if key in updates:
                setattr(camp, key, updates[key])

        camp.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(camp)
        return camp

    async def get_overview_summary(self, session: AsyncSession) -> Dict[str, Any]:
        """Calculates executive campaign telemetry for CEO overview."""
        campaigns = await self.list_campaigns(session)
        total_campaigns = len(campaigns)
        active_campaigns = sum(1 for c in campaigns if c.status == "ACTIVE" and c.enabled)
        total_daily_quota = sum(c.daily_quota for c in campaigns)
        today_sent_total = sum(c.today_sent for c in campaigns)
        today_remaining_total = sum(c.today_remaining for c in campaigns)
        total_replies = sum(c.replies_count for c in campaigns)
        total_interested = sum(c.interested_count for c in campaigns)

        rollout = campaign_config_loader.get_rollout_config()

        return {
            "total_campaigns": total_campaigns,
            "active_campaigns": active_campaigns,
            "total_daily_target_capacity": total_daily_quota,
            "today_sent": today_sent_total,
            "today_remaining": today_remaining_total,
            "total_replies": total_replies,
            "total_interested": total_interested,
            "rollout_level": rollout.current_level,
            "rollout_level_name": rollout.current_level_name,
            "daily_max_real_emails": rollout.daily_max_real_emails,
            "is_simulation": rollout.is_simulation,
            "campaigns": [c.dict() for c in campaigns[:6]]  # top corridors for overview
        }


    def get_rollout_status(self) -> RolloutConfigDTO:
        """Returns the current rollout status and levels."""
        return campaign_config_loader.get_rollout_config()

    def set_rollout_level(self, level: int) -> RolloutConfigDTO:
        """Sets the active progressive rollout level."""
        return campaign_config_loader.set_rollout_level(level)

    async def get_campaign_dto(self, session: AsyncSession, camp: Campaign) -> CampaignDTO:
        """Enriches a single campaign record into CampaignDTO."""
        dtos = await self.list_campaigns(session)
        for d in dtos:
            if d.id == camp.id:
                return d
        return CampaignDTO(
            id=camp.id,
            name=camp.name,
            country_code=camp.country_code,
            country_name=camp.name,
            status=camp.status,
            timezone=camp.timezone,
            daily_quota=camp.daily_quota,
            service_type=camp.service_type,
            approval_policy=camp.approval_policy,
            enabled=camp.enabled
        )


campaign_service = CampaignService()
