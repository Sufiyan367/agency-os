"""Notification Policy Engine for Agency OS CEO Mobile Notifications.

Evaluates normalized notification events against recipient preferences,
priority classifications, and timezone-aware quiet hours rules.
CRITICAL alerts, security incidents, payment anomalies, and SEV-1 events
ALWAYS bypass quiet hours and preference suppressions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from app.database.models import NotificationPreference
from app.notifications.models import (
    NotificationCategory,
    NotificationEventPayload,
    NotificationPriority,
)

logger = logging.getLogger("agency.notifications.policy")


@dataclass
class PolicyDecision:
    """Outcome of policy evaluation for an event against a recipient's preferences."""
    should_record_in_app: bool
    should_push: bool
    bypass_quiet_hours: bool
    reason: str


class NotificationPolicyEngine:
    """Evaluates business events against notification delivery policies."""

    @staticmethod
    def is_in_quiet_hours(
        pref: NotificationPreference,
        target_dt: Optional[datetime] = None,
    ) -> bool:
        """Check if target datetime falls within user's configured quiet hours."""
        if not pref.quiet_hours_enabled:
            return False

        tz_str = pref.timezone or "UTC"
        try:
            user_tz = ZoneInfo(tz_str)
        except Exception:
            user_tz = ZoneInfo("UTC")

        now = target_dt or datetime.now(user_tz)
        if now.tzinfo is None:
            now = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(user_tz)
        else:
            now = now.astimezone(user_tz)

        try:
            start_h, start_m = map(int, (pref.quiet_hours_start or "22:00").split(":"))
            end_h, end_m = map(int, (pref.quiet_hours_end or "08:00").split(":"))
            start_time = time(start_h, start_m)
            end_time = time(end_h, end_m)
        except Exception as e:
            logger.warning(f"Error parsing quiet hours '{pref.quiet_hours_start}-{pref.quiet_hours_end}': {e}")
            return False

        current_time = now.time()

        if start_time <= end_time:
            # e.g., 01:00 to 06:00 (same day)
            return start_time <= current_time <= end_time
        else:
            # e.g., 22:00 to 08:00 (spans midnight)
            return current_time >= start_time or current_time <= end_time

    @classmethod
    def evaluate(
        cls,
        payload: NotificationEventPayload,
        pref: Optional[NotificationPreference],
        target_dt: Optional[datetime] = None,
    ) -> PolicyDecision:
        """Evaluate whether a normalized notification should be recorded in-app and pushed to devices.
        
        CRITICAL alerts, security incidents, compliance halts, SEV-1 incidents,
        and payment anomalies strictly bypass quiet hours and priority suppression.
        """
        # Default policy if no user preference is stored: default enabled, no quiet hours
        if pref is None:
            return PolicyDecision(
                should_record_in_app=True,
                should_push=True,
                bypass_quiet_hours=False,
                reason="DEFAULT_ALLOW",
            )

        priority = payload.priority
        category = payload.category

        # Invariant: CRITICAL priority and extreme categories ALWAYS bypass quiet hours & cannot be disabled
        is_critical_bypass = (
            priority == NotificationPriority.CRITICAL
            or category in (NotificationCategory.SECURITY, NotificationCategory.COMPLIANCE)
            or payload.severity == "SEV-1"
            or "ANOMALY" in payload.event_type.upper()
        )

        if is_critical_bypass:
            return PolicyDecision(
                should_record_in_app=True,
                should_push=True,
                bypass_quiet_hours=True,
                reason="CRITICAL_BYPASS",
            )

        # 1. Check category preference
        if category == NotificationCategory.FINANCIAL and pref.payment_alerts is False:
            return PolicyDecision(
                should_record_in_app=True,
                should_push=False,
                bypass_quiet_hours=False,
                reason="SUPPRESSED_CATEGORY_FINANCIAL",
            )
        if category == NotificationCategory.SALES and pref.sales_alerts is False:
            return PolicyDecision(
                should_record_in_app=True,
                should_push=False,
                bypass_quiet_hours=False,
                reason="SUPPRESSED_CATEGORY_SALES",
            )
        if category == NotificationCategory.DELIVERY and pref.delivery_alerts is False:
            return PolicyDecision(
                should_record_in_app=True,
                should_push=False,
                bypass_quiet_hours=False,
                reason="SUPPRESSED_CATEGORY_DELIVERY",
            )
        if category == NotificationCategory.SUPPORT and pref.support_alerts is False:
            return PolicyDecision(
                should_record_in_app=True,
                should_push=False,
                bypass_quiet_hours=False,
                reason="SUPPRESSED_CATEGORY_SUPPORT",
            )

        # 2. Check quiet hours
        if cls.is_in_quiet_hours(pref, target_dt=target_dt):
            # Normal and Low priority push notifications are suppressed during quiet hours
            if priority in (NotificationPriority.NORMAL, NotificationPriority.LOW):
                return PolicyDecision(
                    should_record_in_app=True,
                    should_push=False,
                    bypass_quiet_hours=False,
                    reason="SUPPRESSED_QUIET_HOURS",
                )

        # 3. Check priority preference
        if priority == NotificationPriority.HIGH and pref.high_enabled is False:
            return PolicyDecision(
                should_record_in_app=True,
                should_push=False,
                bypass_quiet_hours=False,
                reason="SUPPRESSED_PRIORITY_HIGH",
            )
        if priority == NotificationPriority.NORMAL and pref.normal_enabled is False:
            return PolicyDecision(
                should_record_in_app=True,
                should_push=False,
                bypass_quiet_hours=False,
                reason="SUPPRESSED_PRIORITY_NORMAL",
            )
        if priority == NotificationPriority.LOW and (pref.low_enabled is False or pref.low_enabled is None):
            return PolicyDecision(
                should_record_in_app=True,
                should_push=False,
                bypass_quiet_hours=False,
                reason="SUPPRESSED_PRIORITY_LOW",
            )

        return PolicyDecision(
            should_record_in_app=True,
            should_push=True,
            bypass_quiet_hours=False,
            reason="ALLOW",
        )
