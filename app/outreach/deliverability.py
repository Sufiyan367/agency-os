"""
Deliverability Protection & Monitoring Engine — Phase 1 & Deliverability Control.

Tracks:
- Dispatched emails (sent)
- Delivered confirmations / successful transfers
- Bounces (hard/soft)
- Send failures
- Total inbound replies
- Positive replies
- Negative / opt-out replies
- Unsubscribes
- Spam/complaint signals
- Provider authentication state

Enforces automatic protection:
- Rolling window calculations (default: 7 days)
- Throttles sending when bounce/unsub rates reach WARNING thresholds
- Pauses outbound immediately when bounce/complaint/failure rates cross CRITICAL thresholds
- Verifies provider authentication without sending test emails
"""

import smtplib
import ssl
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.config import settings
from app.core.logging import logger
from app.database.models import OutreachMessage, OutreachStatus, OutreachEvent, Reply, ReplyClassification


class DeliverabilityHealth(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    PAUSED = "PAUSED"


class DeliverabilityThresholds(BaseModel):
    # Industry-standard conservative thresholds (aligns with Google / Yahoo 2024+ sender guidelines)
    max_bounce_rate: float = Field(default=0.05, description="Bounce rate >= 5% triggers immediate outbound PAUSE")
    warn_bounce_rate: float = Field(default=0.03, description="Bounce rate >= 3% triggers WARNING & 50% throttle")
    max_complaint_rate: float = Field(default=0.001, description="Spam complaint rate >= 0.1% triggers immediate PAUSE")
    warn_unsubscribe_rate: float = Field(default=0.02, description="Unsubscribe rate >= 2% triggers WARNING")
    max_unsubscribe_rate: float = Field(default=0.04, description="Unsubscribe rate >= 4% triggers 50% throttle")
    max_failure_rate: float = Field(default=0.15, description="Send failure rate >= 15% triggers immediate PAUSE")
    min_sample_size: int = Field(default=10, description="Minimum emails in window before enforcing percentage thresholds")
    rolling_window_days: int = Field(default=7, description="Rolling calculation window in days")


class DeliverabilityMetrics(BaseModel):
    window_days: int
    sent_count: int = 0
    delivered_count: int = 0
    bounced_count: int = 0
    failed_count: int = 0
    replied_count: int = 0
    positive_replies_count: int = 0
    negative_replies_count: int = 0
    unsubscribe_count: int = 0
    complaint_count: int = 0
    
    # Calculated rates
    bounce_rate: float = 0.0
    complaint_rate: float = 0.0
    unsubscribe_rate: float = 0.0
    reply_rate: float = 0.0
    positive_conversion_rate: float = 0.0
    failure_rate: float = 0.0
    
    # Health & status
    health: DeliverabilityHealth = DeliverabilityHealth.HEALTHY
    provider_auth_state: str = "UNKNOWN"
    throttle_multiplier: float = 1.0  # 1.0 = normal, 0.5 = throttled, 0.0 = paused
    reasons: list[str] = Field(default_factory=list)


class DeliverabilityMonitor:
    """
    Monitors email deliverability telemetry and enforces automatic safeguards.
    """

    def __init__(self, thresholds: Optional[DeliverabilityThresholds] = None):
        self.thresholds = thresholds or DeliverabilityThresholds()

    async def calculate_metrics(self, session: AsyncSession) -> DeliverabilityMetrics:
        """
        Queries database for rolling window statistics and computes deliverability metrics.
        """
        cutoff = datetime.utcnow() - timedelta(days=self.thresholds.rolling_window_days)

        # 1. Outreach message dispatches and failures
        q_sent = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.status == OutreachStatus.SENT.value,
            OutreachMessage.sent_at >= cutoff
        )
        sent_count = (await session.execute(q_sent)).scalar() or 0

        q_failed = select(func.count(OutreachMessage.id)).where(
            OutreachMessage.status == OutreachStatus.FAILED.value,
            OutreachMessage.created_at >= cutoff
        )
        failed_count = (await session.execute(q_failed)).scalar() or 0

        # 2. Replies and classifications
        q_replies = select(Reply.classification, func.count(Reply.id)).where(
            Reply.received_at >= cutoff
        ).group_by(Reply.classification)
        reply_rows = (await session.execute(q_replies)).all()
        
        reply_counts: Dict[str, int] = {}
        for classification, count in reply_rows:
            reply_counts[str(classification).upper()] = count

        total_replies = sum(reply_counts.values())
        bounced_count = reply_counts.get(ReplyClassification.BOUNCE.value, 0)
        unsub_count = reply_counts.get(ReplyClassification.UNSUBSCRIBE.value, 0)
        negative_count = reply_counts.get(ReplyClassification.NEGATIVE.value, 0) + reply_counts.get("NOT_INTERESTED", 0)
        positive_count = (
            reply_counts.get(ReplyClassification.POSITIVE.value, 0) +
            reply_counts.get(ReplyClassification.INTERESTED.value, 0) +
            reply_counts.get(ReplyClassification.MEETING_REQUEST.value, 0) +
            reply_counts.get(ReplyClassification.DEMO_REQUEST.value, 0)
        )
        complaint_count = reply_counts.get("COMPLAINT", 0)

        # Derived delivered count
        delivered_count = max(0, sent_count - bounced_count)

        # 3. Compute rates with zero-division protection
        sample_size = max(1, sent_count)
        bounce_rate = round(bounced_count / sample_size, 4)
        complaint_rate = round(complaint_count / sample_size, 4)
        unsubscribe_rate = round(unsub_count / sample_size, 4)
        reply_rate = round(total_replies / sample_size, 4)
        pos_rate = round(positive_count / max(1, total_replies), 4)
        fail_rate = round(failed_count / max(1, sent_count + failed_count), 4)

        # 4. Check Provider Authentication State
        auth_state = self.check_provider_auth_state()

        # 5. Evaluate Health & Thresholds
        health = DeliverabilityHealth.HEALTHY
        throttle = 1.0
        reasons = []

        # Provider Authentication Check
        if auth_state == "MISSING_CREDENTIALS":
            health = DeliverabilityHealth.PAUSED
            throttle = 0.0
            reasons.append("Titan SMTP password not provisioned in environment. Outbound safely paused.")
        elif auth_state == "AUTH_FAILED":
            health = DeliverabilityHealth.PAUSED
            throttle = 0.0
            reasons.append("Titan SMTP authentication failed. Outbound safely paused.")

        # Rate checks only apply if sample size meets minimum
        if sent_count >= self.thresholds.min_sample_size:
            if bounce_rate >= self.thresholds.max_bounce_rate:
                health = DeliverabilityHealth.PAUSED
                throttle = 0.0
                reasons.append(f"Bounce rate ({bounce_rate*100:.1f}%) exceeds hard ceiling ({self.thresholds.max_bounce_rate*100:.1f}%).")
            elif bounce_rate >= self.thresholds.warn_bounce_rate:
                if health != DeliverabilityHealth.PAUSED:
                    health = DeliverabilityHealth.WARNING
                    throttle = min(throttle, 0.5)
                reasons.append(f"Bounce rate ({bounce_rate*100:.1f}%) exceeds warning threshold ({self.thresholds.warn_bounce_rate*100:.1f}%).")

            if complaint_rate >= self.thresholds.max_complaint_rate:
                health = DeliverabilityHealth.PAUSED
                throttle = 0.0
                reasons.append(f"Spam complaint rate ({complaint_rate*100:.2f}%) exceeds ceiling ({self.thresholds.max_complaint_rate*100:.2f}%).")

            if unsubscribe_rate >= self.thresholds.max_unsubscribe_rate:
                if health != DeliverabilityHealth.PAUSED:
                    health = DeliverabilityHealth.WARNING
                    throttle = min(throttle, 0.5)
                reasons.append(f"Unsubscribe rate ({unsubscribe_rate*100:.1f}%) exceeds throttle threshold.")
            elif unsubscribe_rate >= self.thresholds.warn_unsubscribe_rate:
                if health == DeliverabilityHealth.HEALTHY:
                    health = DeliverabilityHealth.WARNING
                reasons.append(f"Unsubscribe rate ({unsubscribe_rate*100:.1f}%) elevated.")

            if fail_rate >= self.thresholds.max_failure_rate:
                health = DeliverabilityHealth.PAUSED
                throttle = 0.0
                reasons.append(f"Send failure rate ({fail_rate*100:.1f}%) exceeds tolerance.")

        return DeliverabilityMetrics(
            window_days=self.thresholds.rolling_window_days,
            sent_count=sent_count,
            delivered_count=delivered_count,
            bounced_count=bounced_count,
            failed_count=failed_count,
            replied_count=total_replies,
            positive_replies_count=positive_count,
            negative_replies_count=negative_count,
            unsubscribe_count=unsub_count,
            complaint_count=complaint_count,
            bounce_rate=bounce_rate,
            complaint_rate=complaint_rate,
            unsubscribe_rate=unsubscribe_rate,
            reply_rate=reply_rate,
            positive_conversion_rate=pos_rate,
            failure_rate=fail_rate,
            health=health,
            provider_auth_state=auth_state,
            throttle_multiplier=throttle,
            reasons=reasons
        )

    def get_canonical_auth_readiness(self) -> Dict[str, Any]:
        """
        Single canonical source of truth for email outbound authorization status.
        Never exposes raw passwords or secrets in outputs or error strings.
        Returns:
            {
                "provider": "Titan Email",
                "address": "hello@automatedagencyos.tech",
                "auth_status": "READY" | "BLOCKED",
                "readiness": "READY" | "BLOCKED",
                "reason": Optional[str],
                "status_label": "TITAN / READY" | "TITAN / BLOCKED",
                "outbound_authorization": "READY" | "BLOCKED",
                "outbound_auth_blocker": Optional[str],
                "healthy": bool,
                "authenticated_email": Optional[str],
                "details": Dict[str, Any]
            }
        """
        provider_name = (getattr(settings, "PRIMARY_EMAIL_PROVIDER", None) or getattr(settings, "EMAIL_PROVIDER", None) or "titan").lower().strip()

        if provider_name in ("titan", "titan_smtp"):
            from app.outreach.providers.titan_provider import TitanEmailProvider
            tp = TitanEmailProvider()
            has_pw = bool(getattr(settings, "TITAN_SMTP_PASSWORD", None) or getattr(settings, "SMTP_PASSWORD", None))
            sender = getattr(settings, "TITAN_SMTP_USER", None) or getattr(settings, "SMTP_USER", None) or getattr(settings, "EMAIL_FROM", "hello@automatedagencyos.tech")
            if not has_pw:
                reason = "TITAN_SMTP_PASSWORD is missing in configuration"
                return {
                    "provider": "Titan Email",
                    "address": sender,
                    "auth_status": "BLOCKED",
                    "readiness": "BLOCKED",
                    "reason": reason,
                    "status_label": "TITAN / BLOCKED",
                    "outbound_authorization": "BLOCKED",
                    "outbound_auth_blocker": reason,
                    "healthy": False,
                    "authenticated_email": sender,
                    "details": {"status": "UNCONFIGURED", "error": reason}
                }
            auth_check = tp.check_auth_health()
            if auth_check.get("healthy"):
                authenticated_addr = auth_check.get("authenticated_email") or sender
                return {
                    "provider": "Titan Email",
                    "address": authenticated_addr,
                    "auth_status": "READY",
                    "readiness": "READY",
                    "reason": None,
                    "status_label": "TITAN / READY",
                    "outbound_authorization": "READY",
                    "outbound_auth_blocker": None,
                    "healthy": True,
                    "authenticated_email": authenticated_addr,
                    "details": auth_check
                }
            else:
                err_msg = auth_check.get("error") or "SMTP authentication check failed"
                return {
                    "provider": "Titan Email",
                    "address": sender,
                    "auth_status": "BLOCKED",
                    "readiness": "BLOCKED",
                    "reason": err_msg,
                    "status_label": "TITAN / BLOCKED",
                    "outbound_authorization": "BLOCKED",
                    "outbound_auth_blocker": err_msg,
                    "healthy": False,
                    "authenticated_email": sender,
                    "details": auth_check
                }

        elif provider_name in ("gmail", "gmail_oauth"):
            try:
                from app.outreach.providers.gmail_oauth_provider import GmailOAuthEmailProvider
                gp = GmailOAuthEmailProvider()
                g_check = gp.check_auth_health()
                sender = getattr(settings, "GMAIL_SENDER_EMAIL", None) or getattr(settings, "EMAIL_FROM", None) or ""
                if g_check.get("healthy"):
                    return {
                        "provider": "Gmail OAuth",
                        "address": sender,
                        "auth_status": "READY",
                        "readiness": "READY",
                        "reason": None,
                        "status_label": "GMAIL / READY",
                        "outbound_authorization": "READY",
                        "outbound_auth_blocker": None,
                        "healthy": True,
                        "authenticated_email": sender,
                        "details": g_check
                    }
                else:
                    err_msg = g_check.get("error", "Gmail OAuth verification failed")
                    return {
                        "provider": "Gmail OAuth",
                        "address": sender,
                        "auth_status": "BLOCKED",
                        "readiness": "BLOCKED",
                        "reason": err_msg,
                        "status_label": "GMAIL / BLOCKED",
                        "outbound_authorization": "BLOCKED",
                        "outbound_auth_blocker": err_msg,
                        "healthy": False,
                        "authenticated_email": sender,
                        "details": g_check
                    }
            except Exception as e:
                err_msg = str(e)
                return {
                    "provider": "Gmail OAuth",
                    "address": getattr(settings, "GMAIL_SENDER_EMAIL", None) or getattr(settings, "EMAIL_FROM", None) or "",
                    "auth_status": "BLOCKED",
                    "readiness": "BLOCKED",
                    "reason": err_msg,
                    "status_label": "GMAIL / BLOCKED",
                    "outbound_authorization": "BLOCKED",
                    "outbound_auth_blocker": err_msg,
                    "healthy": False,
                    "authenticated_email": None,
                    "details": {"error": err_msg}
                }

        else:
            is_dry_run = getattr(settings, "EMAIL_DRY_RUN", True)
            label_prefix = provider_name.upper()
            sender = getattr(settings, "EMAIL_FROM", "hello@automatedagencyos.tech")
            reason = "Configured in dry-run mode" if is_dry_run else None
            return {
                "provider": label_prefix,
                "address": sender,
                "auth_status": "READY" if not is_dry_run else "BLOCKED",
                "readiness": "READY" if not is_dry_run else "BLOCKED",
                "reason": reason,
                "status_label": f"{label_prefix} / {'READY' if not is_dry_run else 'DRY_RUN'}",
                "outbound_authorization": "READY" if not is_dry_run else "BLOCKED",
                "outbound_auth_blocker": reason,
                "healthy": not is_dry_run,
                "authenticated_email": sender,
                "details": {}
            }

    def check_provider_auth_state(self) -> str:
        """
        Safely checks email provider authentication state using canonical readiness.
        Returns: 'READY', 'MISSING_CREDENTIALS', 'AUTH_FAILED', or 'BLOCKED'
        """
        canon = self.get_canonical_auth_readiness()
        if canon["outbound_authorization"] == "READY":
            return "READY"
        blocker = (canon.get("outbound_auth_blocker") or "").lower()
        if "missing" in blocker or "not populated" in blocker:
            return "MISSING_CREDENTIALS"
        if "handshake" in blocker or "auth" in blocker or "failed" in blocker:
            return "AUTH_FAILED"
        return "BLOCKED"


deliverability_monitor = DeliverabilityMonitor()
