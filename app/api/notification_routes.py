"""FastAPI Route Handlers for CEO Mobile Notifications & Web Push.

Provides endpoints for:
- VAPID public key retrieval
- Multi-device push registration and listing
- In-app notification feed, filtering, and unread counters
- Mark read / Mark all read operations
- User alert preferences (priority, quiet hours, categories)
- Controlled internal test event triggering
- Subsystem health and delivery telemetry
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.routes import get_current_user_info
from app.core.config import settings
from app.database.connection import SyncSessionLocal
from app.database.models import Notification, NotificationDelivery, NotificationDevice, User
from app.notifications.models import (
    DeviceDTO,
    DeviceRegistrationRequest,
    NotificationDTO,
    NotificationListResponse,
    PreferenceDTO,
    PreferenceUpdateRequest,
    TestNotificationRequest,
)
from app.notifications.service import notification_service

logger = logging.getLogger("agency.api.notifications")

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def resolve_current_user_id(request: Request) -> int:
    """Resolve database user ID from session or fallback to admin user."""
    try:
        user_info = get_current_user_info(request)
        username = user_info.get("username", "admin")
    except Exception:
        if not settings.AUTH_ENABLED:
            username = "admin"
        else:
            raise HTTPException(status_code=401, detail="Authentication required.")

    with SyncSessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        if user:
            return user.id
        fallback = db.query(User).first()
        return fallback.id if fallback else 1


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """Retrieve VAPID public key for browser PushManager subscription."""
    key = notification_service.get_vapid_public_key()
    return {"public_key": key, "status": "active" if key else "unconfigured"}


@router.post("/devices", response_model=DeviceDTO)
async def register_device(
    req: DeviceRegistrationRequest,
    request: Request,
):
    """Register or refresh client device for push notifications."""
    user_id = resolve_current_user_id(request)
    device = notification_service.register_device(user_id, req)
    return DeviceDTO.model_validate(device)


@router.get("/devices", response_model=List[DeviceDTO])
async def list_devices(request: Request):
    """List all registered devices for the authenticated user."""
    user_id = resolve_current_user_id(request)
    return notification_service.list_devices(user_id)


@router.delete("/devices/{device_id}")
async def unregister_device(
    device_id: int,
    request: Request,
):
    """Unregister/deactivate a push notification device."""
    user_id = resolve_current_user_id(request)
    success = notification_service.unregister_device(user_id, device_id)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found or not owned by user.")
    return {"success": True, "device_id": device_id}


@router.get("", response_model=NotificationListResponse)
@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    request: Request,
    category: Optional[str] = Query(None, description="Category filter (SECURITY, FINANCIAL, etc.)"),
    priority: Optional[str] = Query(None, description="Priority filter (CRITICAL, HIGH, NORMAL, LOW)"),
    unread_only: bool = Query(False, description="Filter for unread alerts only"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """Retrieve paginated notifications feed with priority/category filters."""
    user_id = resolve_current_user_id(request)
    return notification_service.list_notifications(
        user_id=user_id,
        category=category,
        priority=priority,
        unread_only=unread_only,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count")
async def get_unread_count(request: Request):
    """Get total unread notification count for dashboard / mobile badge."""
    user_id = resolve_current_user_id(request)
    count = notification_service.get_unread_count(user_id)
    return {"unread_count": count}


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    request: Request,
):
    """Mark a specific notification as read."""
    user_id = resolve_current_user_id(request)
    success = notification_service.mark_read(user_id, notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return {"success": True, "notification_id": notification_id}


@router.post("/read-all")
async def mark_all_notifications_read(request: Request):
    """Mark all unread notifications for authenticated user as read."""
    user_id = resolve_current_user_id(request)
    count = notification_service.mark_all_read(user_id)
    return {"success": True, "marked_count": count}


@router.get("/preferences", response_model=PreferenceDTO)
async def get_preferences(request: Request):
    """Get authenticated user's notification preferences."""
    user_id = resolve_current_user_id(request)
    return notification_service.get_preferences(user_id)


@router.put("/preferences", response_model=PreferenceDTO)
async def update_preferences(
    req: PreferenceUpdateRequest,
    request: Request,
):
    """Update notification preferences (quiet hours, categories, priorities)."""
    user_id = resolve_current_user_id(request)
    return notification_service.update_preferences(user_id, req)


@router.post("/test-event")
async def trigger_test_event(
    req: TestNotificationRequest,
    request: Request,
):
    """Trigger a controlled test notification (marked is_test=True)."""
    user_id = resolve_current_user_id(request)
    notif = await notification_service.trigger_test_event(user_id, req)
    if not notif:
        raise HTTPException(status_code=500, detail="Failed generating test notification.")
    return {"success": True, "notification": notif}


@router.get("/health")
async def get_notification_health(request: Request):
    """Diagnostic telemetry on notification subsystem health."""
    user_id = resolve_current_user_id(request)
    key = notification_service.get_vapid_public_key()

    with SyncSessionLocal() as db:
        active_devices = db.query(NotificationDevice).filter(
            NotificationDevice.user_id == user_id,
            NotificationDevice.is_active == True,  # noqa: E712
        ).count()
        total_notifs = db.query(Notification).filter(Notification.user_id == user_id).count()
        unread_notifs = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        ).count()
        recent_deliveries = (
            db.query(NotificationDelivery)
            .order_by(NotificationDelivery.created_at.desc())
            .limit(5)
            .all()
        )
        deliveries_summary = [
            {
                "id": d.id,
                "channel": d.channel,
                "status": d.status,
                "attempts": d.attempts,
                "error": d.last_error,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in recent_deliveries
        ]

    return {
        "status": "HEALTHY",
        "vapid_configured": bool(key),
        "public_key_preview": f"{key[:8]}...{key[-6:]}" if key else None,
        "user_id": user_id,
        "active_devices": active_devices,
        "total_notifications": total_notifs,
        "unread_notifications": unread_notifs,
        "recent_deliveries": deliveries_summary,
    }
