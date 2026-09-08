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
            else:
                target_status = "ACTIVE" if c.enabled else "PAUSED"
                if existing.enabled != c.enabled or existing.status != target_status:
                    existing.enabled = c.enabled
                    existing.status = target_status
                    logger.info(f"[CampaignService] Synced campaign '{existing.name}' ({c.code}): enabled={c.enabled}, status={target_status}")
                campaigns.append(existing)

        await session.commit()
        return campaigns

    def get_rollout_status(self) -> RolloutConfigDTO:
        """Returns the current rollout status and configuration."""
        return campaign_config_loader.get_rollout_config()

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
        """Calculates complete executive campaign & rollout telemetry for CEO overview."""
        from app.database.models import Business, PipelineStage, OutreachEvent
        campaigns = await self.list_campaigns(session)
        total_campaigns = len(campaigns)
        active_campaigns = sum(1 for c in campaigns if c.status == "ACTIVE" and c.enabled)
        total_daily_quota = sum(c.daily_quota for c in campaigns)
        today_sent_total = sum(c.today_sent for c in campaigns)
        today_remaining_total = sum(c.today_remaining for c in campaigns)
        total_replies = sum(c.replies_count for c in campaigns)
        total_interested = sum(c.interested_count for c in campaigns)
        total_bounces = sum(c.bounces_count for c in campaigns)

        rollout = campaign_config_loader.get_rollout_config()
        sender_cap = await sender_registry.get_sender_capacity_summary(session)

        # 1. Qualified prospects discovered
        q_qualified = select(func.count(Business.id)).where(
            Business.verification_status == "VERIFIED",
            Business.pipeline_stage.in_([
                PipelineStage.APPROVAL.value,
                PipelineStage.OUTREACH_READY.value,
                PipelineStage.CONTACTED.value,
                PipelineStage.REPLIED.value,
                PipelineStage.MEETING.value,
                PipelineStage.PROPOSAL.value,
                PipelineStage.WON.value
            ])
        )
        qualified_discovered = (await session.execute(q_qualified)).scalar() or 0

        # 2. Auto-rejected (<$500 floor or verification failure)
        q_rejected = select(func.count(Business.id)).where(
            Business.pipeline_stage == PipelineStage.REJECTED.value
        )
        auto_rejected = (await session.execute(q_rejected)).scalar() or 0

        # 3. Auto-approved (deals >= $500 passing compliance and risk gates)
        q_approved = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.status.in_([OutreachStatus.APPROVED.value, OutreachStatus.SENT.value])
        )
        auto_approved = (await session.execute(q_approved)).scalar() or 0

        # 4. Queued (messages waiting in PENDING_APPROVAL or APPROVED awaiting sender capacity)
        q_queued = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.status.in_([OutreachStatus.PENDING_APPROVAL.value, OutreachStatus.APPROVED.value])
        )
        queued = (await session.execute(q_queued)).scalar() or 0

        # 5. Sent
        q_sent_all = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.status == OutreachStatus.SENT.value
        )
        total_sent = (await session.execute(q_sent_all)).scalar() or 0

        # 6. Delivery failures & bounces
        q_fails = select(func.count(OutreachEvent.id)).where(
            OutreachEvent.event_type.in_(["email_delivery_failed", "email_bounced", "outreach_failed"])
        )
        failures = (await session.execute(q_fails)).scalar() or 0
        delivery_failures_bounces = failures + total_bounces

        # 7. CEO Exceptions (failures, escalations, or manual reviews required)
        q_exceptions = select(func.count(Reply.id)).where(
            Reply.is_handled == False,
            Reply.classification.in_(["HUMAN_REVIEW_REQUIRED", "UNKNOWN", "ESCALATED"])
        )
        try:
            ceo_exceptions = (await session.execute(q_exceptions)).scalar() or 0
        except Exception:
            ceo_exceptions = 0

        # Signal-based advancement eligibility
        advancement_eval = await self.evaluate_rollout_advancement(session)

        # 11 Specific Dashboard Telemetry Metrics
        today_discovery_target = active_campaigns * 10
        bounce_rate_val = advancement_eval.get("bounce_rate_pct", 0.0)
        reply_rate_val = round((total_replies / total_sent * 100) if total_sent > 0 else 0.0, 2)
        remaining_sends_to_advance = max(0, advancement_eval.get("required_sends", 1) - advancement_eval.get("live_sends", 0))
        estimated_days = 0 if advancement_eval.get("eligible", False) else max(1, remaining_sends_to_advance)

        return {
            # 11 Telemetry Metrics
            "current_rollout_stage": rollout.current_level,
            "rollout_stage_name": rollout.current_level_name,
            "today_discovery_target": today_discovery_target,
            "today_discovery_actual": qualified_discovered,
            "today_outbound_limit": rollout.daily_max_real_emails,
            "today_outbound_actual": today_sent_total,
            "active_countries_count": active_campaigns,
            "paused_countries_count": total_campaigns - active_campaigns,
            "total_qualified_leads_in_queue": queued,
            "bounce_rate": bounce_rate_val,
            "reply_rate": reply_rate_val,
            "sender_accounts_active": sender_cap.get("configured_senders_count", 1),
            "estimated_days_to_next_stage": estimated_days,

            # General Metrics
            "countries_active": active_campaigns,
            "total_countries_configured": total_campaigns,
            "qualified_prospects_discovered": qualified_discovered,
            "auto_rejected": auto_rejected,
            "auto_approved": auto_approved,
            "available_sender_capacity": sender_cap["available_capacity"],
            "sender_capacity_summary": sender_cap,
            "queued": queued,
            "sent": total_sent,
            "today_sent": today_sent_total,
            "delivery_failures_bounces": delivery_failures_bounces,
            "replies": total_replies,
            "interested_leads": total_interested,
            "ceo_exceptions": ceo_exceptions,
            "rollout_level": rollout.current_level,
            "rollout_level_name": rollout.current_level_name,
            "daily_max_real_emails": rollout.daily_max_real_emails,
            "is_simulation": rollout.is_simulation,
            "rollout_advancement": advancement_eval,
            "total_daily_target_capacity": total_daily_quota,
            "campaigns": [c.dict() for c in campaigns[:6]]
        }

    async def evaluate_rollout_advancement(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Evaluates whether real-world delivery, reputation, and compliance signals
        warrant advancing to the next progressive rollout stage.
        Advancement depends on proven performance, not simply time:
        - Stage 1 (1/day): Requires >=1 verified live send with 0 bounces and 0 complaints.
        - Stage 2 (5/day): Requires >=5 successful sends with <5% bounce rate.
        - Stage 3 (10/day): Requires >=10 successful sends with <5% bounce rate.
        - Stage 4 (20/day): Requires >=20 successful sends with <3% bounce rate.
        - Stage 5 (50/day): Requires >=50 successful sends with <2% bounce rate.
        - Stage 6 (100/day): Requires >=100 successful sends with <2% bounce rate.
        """
        from app.database.models import OutreachEvent
        rollout = campaign_config_loader.get_rollout_config()
        current_lvl = rollout.current_level

        # Query total live sends
        q_live = select(func.count(OutreachEvent.id)).where(
            OutreachEvent.event_type == "email_dispatched"
        )
        live_sends = (await session.execute(q_live)).scalar() or 0

        # Query total bounces
        q_bnc = select(func.count(Reply.id)).where(Reply.classification == "BOUNCE")
        bounces = (await session.execute(q_bnc)).scalar() or 0

        bounce_rate = (bounces / live_sends * 100) if live_sends > 0 else 0.0

        stage_requirements = {
            0: {"min_sends": 0, "max_bounce_pct": 0.0, "next": 1},
            1: {"min_sends": 1, "max_bounce_pct": 0.0, "next": 2},
            2: {"min_sends": 5, "max_bounce_pct": 5.0, "next": 3},
            3: {"min_sends": 10, "max_bounce_pct": 5.0, "next": 4},
            4: {"min_sends": 20, "max_bounce_pct": 3.0, "next": 5},
            5: {"min_sends": 5, "max_bounce_pct": 2.0, "next": 6},
            6: {"min_sends": 100, "max_bounce_pct": 2.0, "next": 7},
            7: {"min_sends": 180, "max_bounce_pct": 2.0, "next": 7}
        }

        req = stage_requirements.get(current_lvl, {"min_sends": 999, "max_bounce_pct": 0.0, "next": current_lvl})
        has_sufficient_volume = live_sends >= req["min_sends"]
        reputation_healthy = bounce_rate <= req["max_bounce_pct"]
        is_eligible = has_sufficient_volume and reputation_healthy and current_lvl < 7

        reason = (
            f"Stage {current_lvl} verified: {live_sends}/{req['min_sends']} sends completed with {bounce_rate:.1f}% bounce rate (max {req['max_bounce_pct']}%). Eligible to advance to Stage {req['next']}."
            if is_eligible
            else f"Current stage {current_lvl}: {live_sends}/{req['min_sends']} sends completed (bounce rate: {bounce_rate:.1f}%)."
        )

        return {
            "current_stage": current_lvl,
            "current_stage_name": rollout.current_level_name,
            "current_daily_cap": rollout.daily_max_real_emails,
            "eligible_for_advancement": is_eligible,
            "next_stage": req["next"],
            "live_sends_completed": live_sends,
            "bounces_recorded": bounces,
            "bounce_rate_pct": round(bounce_rate, 2),
            "reputation_healthy": reputation_healthy,
            "reason": reason
        }

    async def advance_rollout_if_eligible(self, session: AsyncSession) -> Dict[str, Any]:
        """Advances rollout stage only when real-world delivery and reputation signals pass."""
        eval_res = await self.evaluate_rollout_advancement(session)
        if not eval_res["eligible_for_advancement"]:
            return {"advanced": False, "reason": eval_res["reason"], "status": eval_res}

        next_lvl = eval_res["next_stage"]
        new_config = campaign_config_loader.set_rollout_level(next_lvl, allow_bulk=True)
        return {
            "advanced": True,
            "previous_stage": eval_res["current_stage"],
            "new_stage": next_lvl,
            "new_stage_name": new_config.current_level_name,
            "new_daily_cap": new_config.daily_max_real_emails,
            "reason": eval_res["reason"]
        }

    def set_rollout_level(self, level: int, allow_bulk: bool = False) -> RolloutConfigDTO:
        """Sets the active progressive rollout level."""
        return campaign_config_loader.set_rollout_level(level, allow_bulk=allow_bulk)

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

    async def get_middle_east_summary(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Computes targeted operational telemetry for the 7 Middle East Phase 1 focus markets:
        UAE, Saudi Arabia, Qatar, Kuwait, Oman, Bahrain, Jordan.
        """
        from app.database.models import Business, Contact, Offer, PipelineStage, Proposal
        from app.campaigns.scheduler import campaign_scheduler

        me_codes = ["AE", "SA", "QA", "KW", "OM", "BH", "JO"]
        await self.ensure_campaigns_seeded(session)

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # 1. Market Details
        markets = []
        for code in me_codes:
            camp = await self.get_campaign_by_country(session, code)
            c_prof = campaign_config_loader.get_country(code)
            in_win = False
            local_time_str = "—"
            sent_today = 0
            sent_total = 0
            if camp:
                in_win, local_dt, hour, tz_name = campaign_scheduler.is_within_sending_window(
                    country_code=camp.country_code,
                    timezone_str=camp.timezone,
                    window_start=camp.sending_window_start,
                    window_end=camp.sending_window_end
                )
                local_time_str = f"{local_dt.strftime('%H:%M')} ({tz_name})"

                q_sent_today = select(func.count(OutreachMessage.id)).where(
                    OutreachMessage.campaign_id == camp.id,
                    OutreachMessage.status == OutreachStatus.SENT.value,
                    OutreachMessage.sent_at >= today_start
                )
                sent_today = (await session.execute(q_sent_today)).scalar() or 0

                q_sent_total = select(func.count(OutreachMessage.id)).where(
                    OutreachMessage.campaign_id == camp.id,
                    OutreachMessage.status == OutreachStatus.SENT.value
                )
                sent_total = (await session.execute(q_sent_total)).scalar() or 0

            markets.append({
                "code": code,
                "name": c_prof.name if c_prof else code,
                "currency": c_prof.currency if c_prof else "USD",
                "timezone": camp.timezone if camp else "UTC",
                "daily_target": 10,
                "enabled": True,
                "status": "ACTIVE" if (camp and camp.status == "ACTIVE") else "ACTIVE",
                "is_in_sending_window": in_win,
                "local_time_formatted": local_time_str,
                "today_sent": sent_today,
                "total_sent": sent_total
            })

        # 2. Qualified prospects by country
        q_by_country = await session.execute(
            select(Business.country, func.count(Business.id))
            .where(
                Business.country.in_(me_codes),
                Business.verification_status == "VERIFIED"
            )
            .group_by(Business.country)
        )
        qualified_by_country = {code: 0 for code in me_codes}
        for c_code, count in q_by_country.all():
            if c_code in qualified_by_country:
                qualified_by_country[c_code] = count

        # 3. Qualified prospects by niche
        q_by_niche = await session.execute(
            select(Business.niche, func.count(Business.id))
            .where(
                Business.country.in_(me_codes),
                Business.verification_status == "VERIFIED"
            )
            .group_by(Business.niche)
        )
        qualified_by_niche = {niche: count for niche, count in q_by_niche.all() if niche}

        # 4. Email queue count for Middle East
        q_email_queue = await session.execute(
            select(func.count(OutreachMessage.id))
            .join(Business, OutreachMessage.business_id == Business.id)
            .where(
                Business.country.in_(me_codes),
                OutreachMessage.status.in_([OutreachStatus.PENDING_APPROVAL.value, OutreachStatus.APPROVED.value])
            )
        )
        email_queue_count = q_email_queue.scalar() or 0

        # 5. WhatsApp eligibility metrics
        q_wa_eligible = await session.execute(
            select(func.count(Contact.id))
            .join(Business, Contact.business_id == Business.id)
            .where(
                Business.country.in_(me_codes),
                Contact.whatsapp_eligible == True
            )
        )
        whatsapp_eligible_count = q_wa_eligible.scalar() or 0

        q_wa_ineligible = await session.execute(
            select(func.count(Contact.id))
            .join(Business, Contact.business_id == Business.id)
            .where(
                Business.country.in_(me_codes),
                Contact.whatsapp_eligible == False
            )
        )
        whatsapp_ineligible_count = q_wa_ineligible.scalar() or 0

        # 6. Sender capacity
        sender_cap = await sender_registry.get_sender_capacity_summary(session)
        rollout = campaign_config_loader.get_rollout_config()

        # 7. Sent, Bounced, Replies, Interested in ME
        q_me_sent = await session.execute(
            select(func.count(OutreachMessage.id))
            .join(Business, OutreachMessage.business_id == Business.id)
            .where(
                Business.country.in_(me_codes),
                OutreachMessage.status == OutreachStatus.SENT.value
            )
        )
        me_sent_count = q_me_sent.scalar() or 0

        q_me_replies = await session.execute(
            select(func.count(Reply.id))
            .join(Business, Reply.business_id == Business.id)
            .where(Business.country.in_(me_codes))
        )
        me_replies_count = q_me_replies.scalar() or 0

        q_me_interested = await session.execute(
            select(func.count(Reply.id))
            .join(Business, Reply.business_id == Business.id)
            .where(
                Business.country.in_(me_codes),
                Reply.classification == "INTERESTED"
            )
        )
        me_interested_count = q_me_interested.scalar() or 0

        q_me_bounces = await session.execute(
            select(func.count(Reply.id))
            .join(Business, Reply.business_id == Business.id)
            .where(
                Business.country.in_(me_codes),
                Reply.classification == "BOUNCE"
            )
        )
        me_bounces_count = q_me_bounces.scalar() or 0

        # 8. Pipeline value
        q_pipeline_val = await session.execute(
            select(func.sum(Offer.recommended_price))
            .join(Business, Offer.business_id == Business.id)
            .where(
                Business.country.in_(me_codes),
                Business.pipeline_stage.notin_([PipelineStage.REJECTED.value, PipelineStage.LOST.value])
            )
        )
        pipeline_val = float(q_pipeline_val.scalar() or 0.0)

        # 9. CEO exceptions
        q_exceptions = await session.execute(
            select(func.count(Reply.id))
            .join(Business, Reply.business_id == Business.id)
            .where(
                Business.country.in_(me_codes),
                Reply.is_handled == False,
                Reply.classification.in_(["HUMAN_REVIEW_REQUIRED", "UNKNOWN", "ESCALATED"])
            )
        )
        ceo_exceptions = q_exceptions.scalar() or 0

        return {
            "region": "Middle East (Phase 1 Acquisition Focus)",
            "active_markets": markets,
            "markets_count": len(markets),
            "target_per_country_per_day": 10,
            "total_daily_discovery_target": 70,
            "qualified_by_country": qualified_by_country,
            "qualified_by_niche": qualified_by_niche,
            "email_queue_count": email_queue_count,
            "whatsapp_eligible_count": whatsapp_eligible_count,
            "whatsapp_ineligible_count": whatsapp_ineligible_count,
            "whatsapp_consent_enforcement": "Strict opt-in consent required; public phones stored as ineligible",
            "sender_capacity": {
                "rollout_stage": rollout.current_level,
                "rollout_stage_name": rollout.current_level_name,
                "daily_max_real_emails": rollout.daily_max_real_emails,
                "available_capacity": sender_cap.get("available_capacity", 0),
                "today_sent": sender_cap.get("today_sent", 0)
            },
            "sent_count": me_sent_count,
            "bounced_count": me_bounces_count,
            "replies_count": me_replies_count,
            "interested_count": me_interested_count,
            "pipeline_value_usd": pipeline_val,
            "ceo_exceptions_count": ceo_exceptions,
            "revenue_collected_usd": 0.0,
            "payments_status": "DISABLED (DRY RUN)"
        }


campaign_service = CampaignService()
