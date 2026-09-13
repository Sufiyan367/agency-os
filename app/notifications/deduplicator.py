"""Notification Deduplicator for Agency OS CEO Mobile Notifications.

Guarantees idempotency and prevents alert fatigue by suppressing duplicate
events within a configurable sliding window (default 24 hours).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.database.models import Notification

logger = logging.getLogger("agency.notifications.deduplicator")


class NotificationDeduplicator:
    """Checks and manages event deduplication keys to ensure zero duplicate alerts."""

    DEFAULT_WINDOW_HOURS = 24

    @classmethod
    def check_duplicate(
        cls,
        db: Session,
        user_id: int,
        deduplication_key: str,
        window_hours: int = DEFAULT_WINDOW_HOURS,
    ) -> Tuple[bool, Optional[Notification]]:
        """Check if a notification with this deduplication key has already been issued to the user.
        
        Returns:
            (is_duplicate, existing_notification)
        """
        if not deduplication_key:
            return False, None

        cutoff = datetime.utcnow() - timedelta(hours=window_hours)
        existing = (
            db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.deduplication_key == deduplication_key,
                Notification.created_at >= cutoff,
            )
            .first()
        )

        if existing:
            logger.info(
                f"Duplicate notification suppressed for user {user_id} "
                f"with key '{deduplication_key}' (existing ID: {existing.id})"
            )
            return True, existing

        return False, None
