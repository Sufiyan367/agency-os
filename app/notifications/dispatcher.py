"""Notification Dispatcher for Agency OS CEO Mobile Notifications.

Manages delivery of notifications across active registered devices.
Implements bounded async retries with exponential backoff, records
audit trails in NotificationDelivery, and deactivates expired subscriptions.
Guaranteed non-blocking: push failures never affect business logic.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.database.connection import SyncSessionLocal
from app.database.models import Notification, NotificationDelivery, NotificationDevice
from app.notifications.providers.base import BaseNotificationProvider, SendResult
from app.notifications.providers.web_push import WebPushNotificationProvider

logger = logging.getLogger("agency.notifications.dispatcher")


class NotificationDispatcher:
    """Dispatches notifications to registered devices with bounded retry logic."""

    def __init__(
        self,
        providers: Optional[Dict[str, BaseNotificationProvider]] = None,
        max_attempts: int = 3,
        initial_backoff_seconds: float = 1.0,
    ):
        self._providers: Dict[str, BaseNotificationProvider] = providers or {
            "web_push": WebPushNotificationProvider(),
        }
        self.max_attempts = max_attempts
        self.initial_backoff_seconds = initial_backoff_seconds

    def get_provider(self, channel: str) -> Optional[BaseNotificationProvider]:
        return self._providers.get(channel)

    def register_provider(self, provider: BaseNotificationProvider):
        self._providers[provider.channel_name] = provider

    async def dispatch_to_device(
        self,
        notification_id: int,
        device_id: int,
        channel: str = "web_push",
    ) -> bool:
        """Attempt delivery to a single device with bounded exponential backoff."""
        provider = self.get_provider(channel)
        if not provider:
            logger.warning(f"No provider registered for channel '{channel}'")
            return False

        with SyncSessionLocal() as db:
            notification = db.query(Notification).filter(Notification.id == notification_id).first()
            device = db.query(NotificationDevice).filter(NotificationDevice.id == device_id).first()

            if not notification or not device:
                logger.warning(f"Notification {notification_id} or Device {device_id} not found")
                return False

            if not device.is_active:
                logger.info(f"Skipping inactive device {device_id} ({device.device_name})")
                return False

            # Create or fetch delivery record
            delivery = (
                db.query(NotificationDelivery)
                .filter(
                    NotificationDelivery.notification_id == notification_id,
                    NotificationDelivery.device_id == device_id,
                    NotificationDelivery.channel == channel,
                )
                .first()
            )
            if not delivery:
                delivery = NotificationDelivery(
                    notification_id=notification_id,
                    device_id=device_id,
                    channel=channel,
                    status="PENDING",
                    attempts=0,
                    max_attempts=self.max_attempts,
                )
                db.add(delivery)
                db.commit()
                db.refresh(delivery)

            # Detach notification and device snapshots for async network call
            notif_copy = notification
            dev_copy = device

        # Retry loop outside DB transaction to prevent lock holding
        attempt = 0
        last_error: Optional[str] = None
        current_delay = self.initial_backoff_seconds

        while attempt < self.max_attempts:
            attempt += 1
            try:
                result: SendResult = await provider.send(notif_copy, dev_copy)
            except Exception as e:
                result = SendResult(
                    success=False,
                    error=f"Uncaught provider error: {str(e)}",
                    should_retry=True,
                )

            last_error = result.error

            if result.success:
                with SyncSessionLocal() as db:
                    deliv = db.query(NotificationDelivery).filter(
                        NotificationDelivery.id == delivery.id
                    ).first()
                    dev = db.query(NotificationDevice).filter(
                        NotificationDevice.id == device_id
                    ).first()
                    if deliv:
                        deliv.status = "DELIVERED"
                        deliv.attempts = attempt
                        deliv.delivered_at = datetime.utcnow()
                        deliv.last_error = None
                    if dev:
                        dev.last_seen_at = datetime.utcnow()
                    db.commit()
                logger.info(
                    f"Successfully pushed notification {notification_id} to device {device_id} "
                    f"({dev_copy.device_name}) on attempt {attempt}"
                )
                return True

            if result.device_unregistered:
                with SyncSessionLocal() as db:
                    deliv = db.query(NotificationDelivery).filter(
                        NotificationDelivery.id == delivery.id
                    ).first()
                    dev = db.query(NotificationDevice).filter(
                        NotificationDevice.id == device_id
                    ).first()
                    if deliv:
                        deliv.status = "UNREGISTERED"
                        deliv.attempts = attempt
                        deliv.last_error = result.error or "Endpoint unsubscribed"
                    if dev:
                        dev.is_active = False
                    db.commit()
                logger.info(
                    f"Device {device_id} ({dev_copy.device_name}) unsubscribed or expired (404/410). Deactivated."
                )
                return False

            if not result.should_retry or attempt >= self.max_attempts:
                break

            # Exponential backoff before next attempt
            await asyncio.sleep(current_delay)
            current_delay *= 2.0

        # Mark delivery failed
        with SyncSessionLocal() as db:
            deliv = db.query(NotificationDelivery).filter(
                NotificationDelivery.id == delivery.id
            ).first()
            if deliv:
                deliv.status = "FAILED"
                deliv.attempts = attempt
                deliv.last_error = last_error or "Exhausted retry attempts"
            db.commit()

        logger.warning(
            f"Failed delivering notification {notification_id} to device {device_id} "
            f"after {attempt} attempts: {last_error}"
        )
        return False

    async def dispatch_notification(self, notification_id: int) -> List[bool]:
        """Dispatch notification to all active devices registered for the notification's user."""
        active_devices: List[int] = []

        with SyncSessionLocal() as db:
            notification = db.query(Notification).filter(Notification.id == notification_id).first()
            if not notification:
                logger.warning(f"Notification {notification_id} not found for dispatch")
                return []

            devices = (
                db.query(NotificationDevice)
                .filter(
                    NotificationDevice.user_id == notification.user_id,
                    NotificationDevice.is_active == True,  # noqa: E712
                )
                .all()
            )
            active_devices = [d.id for d in devices]

        if not active_devices:
            logger.info(f"No active devices registered for notification {notification_id}")
            return []

        tasks = [
            self.dispatch_to_device(notification_id, dev_id, channel="web_push")
            for dev_id in active_devices
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)
