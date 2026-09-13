"""Notification Service Facade for Agency OS CEO Mobile Notifications.

Coordinates the end-to-end notification lifecycle:
1. Subscribes to UnifiedEventBus (as an observer only).
2. Normalizes canonical business lifecycle events.
3. Sanitizes all content (zero secret/credential leakage).
4. Evaluates recipient preferences, priorities, and quiet hours.
5. Deduplicates events with idempotent keys.
6. Persists in-app notifications and manages unread state.
7. Dispatches non-blocking Web Push alerts to active user devices.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.event_bus import AgencyEvent, event_bus
from app.database.connection import SyncSessionLocal
from app.database.models import (
    Notification,
    NotificationDevice,
    NotificationPreference,
    User,
)
from app.notifications.deduplicator import NotificationDeduplicator
from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.models import (
    DeviceDTO,
    DeviceRegistrationRequest,
    NotificationCategory,
    NotificationDTO,
    NotificationEventPayload,
    NotificationListResponse,
    NotificationPriority,
    PreferenceDTO,
    PreferenceUpdateRequest,
    TestNotificationRequest,
)
from app.notifications.normalizer import NotificationNormalizer
from app.notifications.policy import NotificationPolicyEngine

logger = logging.getLogger("agency.notifications.service")


class NotificationService:
    """Central notification management engine."""

    def __init__(
        self,
        dispatcher: Optional[NotificationDispatcher] = None,
    ):
        self.dispatcher = dispatcher or NotificationDispatcher()
        self._is_hooked_to_event_bus = False

    def hook_event_bus(self):
        """Hook subscriber into the global event bus."""
        if not self._is_hooked_to_event_bus:
            event_bus.subscribe("*", self.handle_event)
            self._is_hooked_to_event_bus = True
            logger.info("NotificationService successfully subscribed to event bus wildcard '*'.")

    async def handle_event(self, event: AgencyEvent) -> None:
        """Observer callback for lifecycle events from the UnifiedEventBus.
        
        Strict Invariant: Notifications are OBSERVERS ONLY.
        This handler never mutates business entities or cancels transactions.
        """
        try:
            payload = NotificationNormalizer.normalize_event(event)
            if not payload:
                # Event is not notifiable or routine background chatter
                return

            await self.process_payload(payload)

        except Exception as e:
            # Under no circumstances may a notification failure disrupt event processing
            logger.error(f"[NotificationService] Unexpected error processing event {event.event_type}: {e}", exc_info=True)

    async def process_payload(
        self,
        payload: NotificationEventPayload,
        target_user_id: Optional[int] = None,
    ) -> List[int]:
        """Process a normalized notification payload for recipient(s).
        
        Returns list of created notification IDs.
        """
        created_notif_ids: List[int] = []

        with SyncSessionLocal() as db:
            recipients = self._resolve_recipients(db, payload, target_user_id)
            if not recipients:
                logger.debug(f"No recipient users found for event {payload.event_type}")
                return []

            for user in recipients:
                # 1. Deduplication check
                is_dup, existing = NotificationDeduplicator.check_duplicate(
                    db, user.id, payload.deduplication_key
                )
                if is_dup and existing:
                    continue

                # 2. Preference lookup
                pref = db.query(NotificationPreference).filter_by(user_id=user.id).first()
                if not pref:
                    # Create default preferences
                    pref = NotificationPreference(user_id=user.id)
                    db.add(pref)
                    db.commit()
                    db.refresh(pref)

                # 3. Policy evaluation
                decision = NotificationPolicyEngine.evaluate(payload, pref)

                if not decision.should_record_in_app:
                    logger.info(f"Notification suppressed by policy: {decision.reason}")
                    continue

                # 4. In-App persistence
                notif = Notification(
                    user_id=user.id,
                    event_id=payload.event_id,
                    deduplication_key=payload.deduplication_key,
                    event_type=payload.event_type,
                    category=payload.category.value if hasattr(payload.category, "value") else str(payload.category),
                    priority=payload.priority.value if hasattr(payload.priority, "value") else str(payload.priority),
                    severity=payload.severity,
                    title=payload.title,
                    body=payload.body,
                    deep_link=payload.deep_link,
                    action_required=payload.action_required,
                    action_url=payload.action_url,
                    business_id=payload.business_id,
                    customer_id=payload.customer_id,
                    project_id=payload.project_id,
                    incident_id=payload.incident_id,
                    payment_id=payload.payment_id,
                    is_read=False,
                    metadata_safe=payload.metadata_safe,
                    created_at=payload.created_at or datetime.utcnow(),
                )
                db.add(notif)
                db.commit()
                db.refresh(notif)
                created_notif_ids.append(notif.id)

                # 5. Device dispatch (Web Push)
                if decision.should_push:
                    # Non-blocking async dispatch
                    asyncio.create_task(self.dispatcher.dispatch_notification(notif.id))
                else:
                    logger.info(
                        f"Push skipped for notification {notif.id} (reason: {decision.reason})"
                    )

        return created_notif_ids

    def _resolve_recipients(
        self,
        db: Session,
        payload: NotificationEventPayload,
        target_user_id: Optional[int] = None,
    ) -> List[User]:
        """Resolve recipient users (CEO, Admins, Operators)."""
        if target_user_id is not None:
            user = db.query(User).filter_by(id=target_user_id).first()
            return [user] if user else []

        # Find CEO / Admin / Owner users who oversee business operations
        admins = (
            db.query(User)
            .filter(
                User.role.in_(["owner", "admin", "ceo"]),
                User.customer_id.is_(None),
            )
            .all()
        )

        if admins:
            return admins

        # Fallback to any active non-client user or first user
        fallback = db.query(User).filter(User.customer_id.is_(None)).first()
        if fallback:
            return [fallback]

        first_user = db.query(User).first()
        return [first_user] if first_user else []

    # =========================================================================
    # Device Registration & Management
    # =========================================================================

    def register_device(
        self,
        user_id: int,
        req: DeviceRegistrationRequest,
    ) -> NotificationDevice:
        """Register or update a user's browser / mobile device for push notifications."""
        with SyncSessionLocal() as db:
            # Check if this endpoint is already registered
            device = (
                db.query(NotificationDevice)
                .filter(NotificationDevice.endpoint == req.endpoint)
                .first()
            )

            if device:
                # Update existing device subscription
                device.user_id = user_id
                device.device_name = req.device_name
                device.device_type = req.device_type
                device.p256dh = req.p256dh
                device.auth_token = req.auth_token
                device.is_active = True
                device.last_seen_at = datetime.utcnow()
                db.commit()
                db.refresh(device)
                logger.info(f"Updated push registration for device {device.id} (user {user_id})")
                return device

            # Register new device
            device = NotificationDevice(
                user_id=user_id,
                device_name=req.device_name,
                device_type=req.device_type,
                endpoint=req.endpoint,
                p256dh=req.p256dh,
                auth_token=req.auth_token,
                is_active=True,
                last_seen_at=datetime.utcnow(),
            )
            db.add(device)
            db.commit()
            db.refresh(device)
            logger.info(f"Registered new push device {device.id} for user {user_id}")
            return device

    def list_devices(self, user_id: int) -> List[DeviceDTO]:
        """List registered devices for a user."""
        with SyncSessionLocal() as db:
            devices = (
                db.query(NotificationDevice)
                .filter(NotificationDevice.user_id == user_id)
                .order_by(desc(NotificationDevice.last_seen_at))
                .all()
            )
            return [DeviceDTO.model_validate(d) for d in devices]

    def unregister_device(self, user_id: int, device_id: int) -> bool:
        """Deactivate or remove a device registration."""
        with SyncSessionLocal() as db:
            device = (
                db.query(NotificationDevice)
                .filter(
                    NotificationDevice.id == device_id,
                    NotificationDevice.user_id == user_id,
                )
                .first()
            )
            if not device:
                return False

            device.is_active = False
            db.commit()
            return True

    # =========================================================================
    # User Preferences Management
    # =========================================================================

    def get_preferences(self, user_id: int) -> PreferenceDTO:
        """Get or initialize user notification preferences."""
        with SyncSessionLocal() as db:
            pref = db.query(NotificationPreference).filter_by(user_id=user_id).first()
            if not pref:
                pref = NotificationPreference(user_id=user_id)
                db.add(pref)
                db.commit()
                db.refresh(pref)
            return PreferenceDTO.model_validate(pref)

    def update_preferences(
        self,
        user_id: int,
        req: PreferenceUpdateRequest,
    ) -> PreferenceDTO:
        """Update user notification preferences. Critical alerts remain non-disableable."""
        with SyncSessionLocal() as db:
            pref = db.query(NotificationPreference).filter_by(user_id=user_id).first()
            if not pref:
                pref = NotificationPreference(user_id=user_id)
                db.add(pref)

            # Invariant: Critical alerts cannot be turned off
            pref.critical_enabled = True

            if req.high_enabled is not None:
                pref.high_enabled = req.high_enabled
            if req.normal_enabled is not None:
                pref.normal_enabled = req.normal_enabled
            if req.low_enabled is not None:
                pref.low_enabled = req.low_enabled
            if req.payment_alerts is not None:
                pref.payment_alerts = req.payment_alerts
            if req.sales_alerts is not None:
                pref.sales_alerts = req.sales_alerts
            if req.delivery_alerts is not None:
                pref.delivery_alerts = req.delivery_alerts
            if req.support_alerts is not None:
                pref.support_alerts = req.support_alerts
            if req.quiet_hours_enabled is not None:
                pref.quiet_hours_enabled = req.quiet_hours_enabled
            if req.quiet_hours_start is not None:
                pref.quiet_hours_start = req.quiet_hours_start
            if req.quiet_hours_end is not None:
                pref.quiet_hours_end = req.quiet_hours_end
            if req.timezone is not None:
                pref.timezone = req.timezone

            pref.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(pref)
            return PreferenceDTO.model_validate(pref)

    # =========================================================================
    # In-App Notification Center Feed & Reads
    # =========================================================================

    def list_notifications(
        self,
        user_id: int,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> NotificationListResponse:
        """Retrieve paginated notification feed for user with filtering."""
        with SyncSessionLocal() as db:
            query = db.query(Notification).filter(Notification.user_id == user_id)

            if category and category.upper() != "ALL":
                query = query.filter(Notification.category == category.upper())
            if priority and priority.upper() != "ALL":
                query = query.filter(Notification.priority == priority.upper())
            if unread_only:
                query = query.filter(Notification.is_read == False)  # noqa: E712

            total = query.count()
            unread_count = (
                db.query(Notification)
                .filter(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
                .count()
            )

            offset = max(0, (page - 1) * page_size)
            items = (
                query.order_by(desc(Notification.created_at))
                .offset(offset)
                .limit(page_size)
                .all()
            )

            return NotificationListResponse(
                items=[NotificationDTO.model_validate(item) for item in items],
                total=total,
                unread_count=unread_count,
                page=page,
                page_size=page_size,
            )

    def get_unread_count(self, user_id: int) -> int:
        """Get number of unread notifications for user badge."""
        with SyncSessionLocal() as db:
            return (
                db.query(Notification)
                .filter(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
                .count()
            )

    def mark_read(self, user_id: int, notification_id: int) -> bool:
        """Mark single notification as read."""
        with SyncSessionLocal() as db:
            notif = (
                db.query(Notification)
                .filter(Notification.id == notification_id, Notification.user_id == user_id)
                .first()
            )
            if not notif:
                return False

            if not notif.is_read:
                notif.is_read = True
                notif.read_at = datetime.utcnow()
                db.commit()
            return True

    def mark_all_read(self, user_id: int) -> int:
        """Mark all unread notifications for user as read."""
        with SyncSessionLocal() as db:
            unread_notifs = (
                db.query(Notification)
                .filter(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
                .all()
            )
            count = len(unread_notifs)
            now = datetime.utcnow()
            for n in unread_notifs:
                n.is_read = True
                n.read_at = now
            db.commit()
            return count

    # =========================================================================
    # Controlled Test Event Trigger
    # =========================================================================

    async def trigger_test_event(
        self,
        user_id: int,
        req: TestNotificationRequest,
    ) -> Optional[NotificationDTO]:
        """Trigger an internal controlled test event (tagged is_test=True)."""
        # Map test event type to simulated payload
        test_type = req.event_type.upper()
        now_str = datetime.utcnow().strftime("%H:%M:%S")

        category = NotificationCategory.SYSTEM
        priority = NotificationPriority.NORMAL
        severity = None
        title = req.title or f"Test Notification ({test_type})"
        body = req.body or f"Internal verification test event dispatched at {now_str}."
        action_required = False
        action_url = None
        deep_link = "/?tab=notifications"

        if "PAYMENT" in test_type:
            category = NotificationCategory.FINANCIAL
            priority = NotificationPriority.HIGH
            title = req.title or "Payment Received: $2,500.00"
            body = req.body or "Advance payment verified from Apex Dental Care via Razorpay."
            deep_link = "/?tab=payments"
        elif "SEV1" in test_type or "CRITICAL" in test_type:
            category = NotificationCategory.PRODUCTION
            priority = NotificationPriority.CRITICAL
            severity = "SEV-1"
            title = req.title or "CRITICAL: Database Primary Degraded"
            body = req.body or "Connection pool latency exceeded 5000ms threshold."
            deep_link = "/?tab=support"
            action_required = True
            action_url = "/?tab=support"
        elif "REPLY" in test_type or "POSITIVE" in test_type:
            category = NotificationCategory.SALES
            priority = NotificationPriority.HIGH
            title = req.title or "Hot Lead: Positive Reply Received"
            body = req.body or "Dr. Robert Smith replied: 'Interested in seeing your booking engine demo'."
            deep_link = "/?tab=conversations"
        elif "DELIVERY" in test_type or "DEPLOY" in test_type:
            category = NotificationCategory.DELIVERY
            priority = NotificationPriority.NORMAL
            title = req.title or "Deployment Verified"
            body = req.body or "Staging release v2.4.1 deployed and verified healthy."
            deep_link = "/?tab=delivery"

        if req.priority:
            try:
                priority = NotificationPriority(req.priority.upper())
            except Exception:
                pass
        if req.category:
            try:
                category = NotificationCategory(req.category.upper())
            except Exception:
                pass

        test_payload = NotificationEventPayload(
            event_id=f"TEST-EVT-{datetime.utcnow().timestamp()}",
            event_type=test_type,
            category=category,
            priority=priority,
            severity=severity,
            title=title,
            body=body,
            deep_link=deep_link,
            action_required=action_required,
            action_url=action_url,
            business_id=req.business_id,
            deduplication_key=f"test:{user_id}:{datetime.utcnow().timestamp()}",
            metadata_safe={"is_test": True, "triggered_by_user": user_id},
        )

        notif_ids = await self.process_payload(test_payload, target_user_id=user_id)
        if not notif_ids:
            return None

        with SyncSessionLocal() as db:
            created = db.query(Notification).filter_by(id=notif_ids[0]).first()
            return NotificationDTO.model_validate(created) if created else None

    def get_vapid_public_key(self) -> str:
        """Return the VAPID public key for Web Push client subscription."""
        provider = self.dispatcher.get_provider("web_push")
        if isinstance(provider, NotificationService):
            pass
        from app.notifications.providers.web_push import WebPushNotificationProvider
        if isinstance(provider, WebPushNotificationProvider):
            return provider.public_key
        return ""


# Global singleton instance
notification_service = NotificationService()
