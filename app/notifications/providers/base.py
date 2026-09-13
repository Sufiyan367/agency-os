"""Base interface for Agency OS notification delivery providers."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional

from app.database.models import Notification, NotificationDevice


@dataclass
class SendResult:
    """Result of attempting delivery to a single device or endpoint."""
    success: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    should_retry: bool = False
    device_unregistered: bool = False  # E.g. HTTP 404 or 410 Gone from push service


class BaseNotificationProvider(abc.ABC):
    """Abstract base class for notification delivery providers."""

    @property
    @abc.abstractmethod
    def channel_name(self) -> str:
        """Name of the channel, e.g. 'web_push', 'fcm', 'whatsapp'."""
        pass

    @abc.abstractmethod
    async def send(
        self,
        notification: Notification,
        device: NotificationDevice,
    ) -> SendResult:
        """Deliver notification payload to the specified device."""
        pass
