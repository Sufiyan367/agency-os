"""Comprehensive Automated Test Suite for CEO Mobile Notification & Event Alert System.

Covers all 25 Core Verification Specifications:
1. Normalizer creates correct payload for PAYMENT_VERIFIED
2. Normalizer creates correct payload for PAYMENT_ANOMALY
3. Normalizer creates correct payload for SECURITY_INCIDENT
4. Normalizer creates correct payload for SEV1_INCIDENT
5. Normalizer creates correct payload for DEPLOYMENT_FAILED
6. Normalizer creates correct payload for OUTREACH_BLOCKED
7. Normalizer creates correct payload for POSITIVE_REPLY
8. Normalizer creates correct payload for PROPOSAL_ACCEPTED
9. Normalizer creates correct payload for APPROVAL_REQUIRED
10. Secret redaction removes API keys and bearer tokens
11. Secret redaction strips stack traces
12. Policy engine assigns correct priorities to critical events
13. Policy engine respects quiet hours for NORMAL alerts
14. Policy engine bypasses quiet hours for CRITICAL alerts
15. Policy engine enforces timezone correctness
16. Policy engine respects category enable/disable preferences
17. Deduplicator prevents duplicate notification within window
18. Deduplicator allows different event types for same entity
19. Device registration creates and activates device
20. Device unregistration deactivates device
21. Multi-device delivery sends to all active devices
22. Dispatcher records delivery audit log
23. Dispatcher handles provider failure gracefully without raising
24. Expired subscription (410) deactivates device
25. Test notification endpoint creates verified test alert
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient, ASGITransport

from app.api.app import app
from app.core.event_bus import AgencyEvent, UnifiedEventBus
from app.database.connection import SyncSessionLocal
from app.database.models import (
    Notification,
    NotificationDelivery,
    NotificationDevice,
    NotificationPreference,
    User,
)
from app.notifications.deduplicator import NotificationDeduplicator
from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.models import (
    DeviceRegistrationRequest,
    NotificationCategory,
    NotificationEventPayload,
    NotificationPriority,
    PreferenceUpdateRequest,
    TestNotificationRequest,
)
from app.notifications.normalizer import NotificationNormalizer, sanitize_metadata, sanitize_text
from app.notifications.policy import NotificationPolicyEngine
from app.notifications.providers.base import BaseNotificationProvider, SendResult
from app.notifications.service import NotificationService


@pytest.fixture
def sync_db():
    with SyncSessionLocal() as session:
        yield session


@pytest.fixture
def sample_user(sync_db):
    user = sync_db.query(User).filter_by(username="test_ceo_user").first()
    if not user:
        user = User(
            username="test_ceo_user",
            password_hash="test_hash_val_2026",
            role="owner",
            customer_id=None,
            is_setup_completed=True,
        )
        sync_db.add(user)
        sync_db.commit()
        sync_db.refresh(user)
    return user


# =============================================================================
# 1-9: Normalizer Canonical Mapping Tests
# =============================================================================

def test_01_normalizer_payment_verified():
    event = AgencyEvent(
        event_type="PAYMENT_VERIFIED",
        entity_type="payment",
        entity_id=101,
        payload={
            "amount_usd": 3500.0,
            "payer_name": "Apex Dental",
            "business_id": 12,
            "deal_id": 45,
        },
    )
    payload = NotificationNormalizer.normalize_event(event)
    assert payload is not None
    assert payload.category == NotificationCategory.FINANCIAL
    assert payload.priority == NotificationPriority.HIGH
    assert "$3,500.00" in payload.title or "$3,500.00" in payload.body
    assert "/dashboard#pipeline" in payload.deep_link
    assert "pay_verified_101" in payload.deduplication_key


def test_02_normalizer_payment_anomaly():
    event = AgencyEvent(
        event_type="PAYMENT_ANOMALY",
        entity_type="payment",
        entity_id=102,
        payload={
            "reason": "Duplicate transaction hash detected",
            "risk_score": 98,
        },
    )
    payload = NotificationNormalizer.normalize_event(event)
    assert payload is not None
    assert payload.category == NotificationCategory.FINANCIAL
    assert payload.priority == NotificationPriority.CRITICAL
    assert payload.action_required is True
    assert "Anomaly" in payload.title
    assert "/dashboard#pipeline" in payload.deep_link


def test_03_normalizer_security_incident():
    event = AgencyEvent(
        event_type="SECURITY_INCIDENT",
        entity_type="security",
        entity_id=501,
        payload={
            "description": "Suspicious login attempt from blocked IP",
            "ip": "198.51.100.24",
        },
    )
    payload = NotificationNormalizer.normalize_event(event)
    assert payload is not None
    assert payload.category == NotificationCategory.SECURITY
    assert payload.priority == NotificationPriority.CRITICAL
    assert payload.action_required is True
    assert "/dashboard#security" in payload.deep_link


def test_04_normalizer_sev1_incident():
    event = AgencyEvent(
        event_type="SEV1_INCIDENT",
        entity_type="incident",
        entity_id=999,
        payload={
            "title": "Primary Database Unreachable",
            "severity": "SEV-1",
            "service": "database",
        },
    )
    payload = NotificationNormalizer.normalize_event(event)
    assert payload is not None
    assert payload.category == NotificationCategory.PRODUCTION
    assert payload.priority == NotificationPriority.CRITICAL
    assert payload.severity == "SEV-1"
    assert payload.action_required is True
    assert "SEV-1" in payload.title


def test_05_normalizer_deployment_failed():
    event = AgencyEvent(
        event_type="DEPLOYMENT_FAILED",
        entity_type="project",
        entity_id=77,
        payload={
            "project_name": "Dr. Smile Portal",
            "error": "Health check 502 Bad Gateway",
        },
    )
    payload = NotificationNormalizer.normalize_event(event)
    assert payload is not None
    assert payload.category == NotificationCategory.DELIVERY
    assert payload.priority == NotificationPriority.CRITICAL
    assert payload.action_required is True
    assert payload.project_id == 77
    assert "/dashboard#delivery" in payload.deep_link


def test_06_normalizer_outreach_blocked():
    event = AgencyEvent(
        event_type="OUTREACH_BLOCKED",
        entity_type="campaign",
        entity_id=88,
        payload={
            "reason": "Bounce threshold exceeded 3.0%",
            "campaign_id": 88,
        },
    )
    payload = NotificationNormalizer.normalize_event(event)
    assert payload is not None
    assert payload.category == NotificationCategory.COMPLIANCE
    assert payload.priority in (NotificationPriority.HIGH, NotificationPriority.CRITICAL)
    assert "Outreach Blocked" in payload.title


def test_07_normalizer_positive_reply():
    event = AgencyEvent(
        event_type="POSITIVE_REPLY",
        entity_type="lead",
        entity_id=202,
        payload={
            "lead_name": "Dr. Sarah Connor",
            "snippet": "We are ready to look at your proposal tomorrow.",
            "business_id": 34,
        },
    )
    payload = NotificationNormalizer.normalize_event(event)
    assert payload is not None
    assert payload.category == NotificationCategory.SALES
    assert payload.priority == NotificationPriority.HIGH
    assert "/dashboard#conversations" in payload.deep_link
    assert payload.business_id == 202 or payload.business_id == 34


def test_08_normalizer_proposal_accepted():
    event = AgencyEvent(
        event_type="PROPOSAL_ACCEPTED",
        entity_type="deal",
        entity_id=303,
        payload={
            "deal_id": 303,
            "deal_value": 7500.0,
            "prospect_name": "Metropolis Legal",
        },
    )
    payload = NotificationNormalizer.normalize_event(event)
    assert payload is not None
    assert payload.category == NotificationCategory.SALES
    assert payload.priority == NotificationPriority.HIGH
    assert "$7,500.00" in payload.body
    assert "/dashboard#pipeline" in payload.deep_link


def test_09_normalizer_approval_required():
    event = AgencyEvent(
        event_type="APPROVAL_REQUIRED",
        entity_type="outreach",
        entity_id=404,
        payload={
            "action_name": "Send Outreach Sequence",
            "target_name": "Apex Holdings CEO",
            "risk_level": "High-impact",
        },
    )
    payload = NotificationNormalizer.normalize_event(event)
    assert payload is not None
    assert payload.priority in (NotificationPriority.HIGH, NotificationPriority.CRITICAL)
    assert payload.action_required is True
    assert "/dashboard#queue" in payload.action_url


# =============================================================================
# 10-11: Secret & Credential Redaction Tests
# =============================================================================

def test_10_secret_redaction_removes_api_keys_and_bearer_tokens():
    leak_text = (
        "Sending email failed with API key sk_live_51M0abcdef1234567890XYZ "
        "and header Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.secret "
        "and token ghp_ABCDEF1234567890abcdef1234567890ABCD"
    )
    sanitized = sanitize_text(leak_text)
    assert "sk_live_" not in sanitized
    assert "ghp_" not in sanitized
    assert "[REDACTED]" in sanitized

    meta = {
        "api_key": "sk_test_1234567890secretkeyhere",
        "nested": {"client_secret": "my_super_secret_password_123"},
        "clean": "public_data",
    }
    cleaned_meta = sanitize_metadata(meta)
    assert cleaned_meta["api_key"] == "[REDACTED]"
    assert cleaned_meta["nested"]["client_secret"] == "[REDACTED]"
    assert cleaned_meta["clean"] == "public_data"


def test_11_secret_redaction_strips_stack_traces():
    raw_stack = (
        "Internal server error:\n"
        "Traceback (most recent call last):\n"
        '  File "/opt/agency/app/core/db.py", line 42, in connect\n'
        "    raise ConnectionError('Failed to bind to 10.0.0.1:5432')\n"
        "ConnectionError: Failed to bind"
    )
    sanitized = sanitize_text(raw_stack)
    assert "Traceback" not in sanitized
    assert "File \"/opt/agency" not in sanitized
    assert "[STACK TRACE REMOVED]" in sanitized


# =============================================================================
# 12-16: Policy Engine & Quiet Hours Tests
# =============================================================================

def test_12_policy_engine_assigns_correct_priorities():
    pref = NotificationPreference(user_id=1, quiet_hours_enabled=False)

    crit_payload = NotificationEventPayload(
        event_id="e1",
        event_type="SEV1_INCIDENT",
        priority=NotificationPriority.CRITICAL,
        category=NotificationCategory.PRODUCTION,
        severity="SEV-1",
        title="SEV-1 Alert",
        body="Core DB down",
        deduplication_key="sev1:1",
    )
    decision = NotificationPolicyEngine.evaluate(crit_payload, pref)
    assert decision.should_record_in_app is True
    assert decision.should_push is True
    assert decision.bypass_quiet_hours is True


def test_13_policy_engine_respects_quiet_hours_for_normal():
    # User quiet hours 22:00 to 08:00
    pref = NotificationPreference(
        user_id=1,
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="08:00",
        timezone="UTC",
    )

    # Time: 23:30 (inside quiet hours)
    target_time = datetime(2026, 9, 14, 23, 30, tzinfo=ZoneInfo("UTC"))

    normal_payload = NotificationEventPayload(
        event_id="e2",
        event_type="DEPLOYMENT_COMPLETED",
        priority=NotificationPriority.NORMAL,
        category=NotificationCategory.DELIVERY,
        title="Deployment Complete",
        body="Version 1.2 deployed",
        deduplication_key="dep:1",
    )
    decision = NotificationPolicyEngine.evaluate(normal_payload, pref, target_dt=target_time)
    assert decision.should_record_in_app is True
    assert decision.should_push is False
    assert decision.reason == "SUPPRESSED_QUIET_HOURS"


def test_14_policy_engine_bypasses_quiet_hours_for_critical():
    pref = NotificationPreference(
        user_id=1,
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="08:00",
        timezone="UTC",
    )
    # Time: 03:00 AM (inside quiet hours)
    target_time = datetime(2026, 9, 14, 3, 0, tzinfo=ZoneInfo("UTC"))

    crit_payload = NotificationEventPayload(
        event_id="e3",
        event_type="PAYMENT_ANOMALY",
        priority=NotificationPriority.CRITICAL,
        category=NotificationCategory.FINANCIAL,
        title="Payment Anomaly Detected",
        body="Suspicious duplicate card usage",
        deduplication_key="anom:1",
    )
    decision = NotificationPolicyEngine.evaluate(crit_payload, pref, target_dt=target_time)
    assert decision.should_record_in_app is True
    assert decision.should_push is True
    assert decision.bypass_quiet_hours is True
    assert decision.reason == "CRITICAL_BYPASS"


def test_15_policy_engine_enforces_timezone_correctness():
    # User in New York (UTC-4 in EDT)
    # 02:00 UTC is 22:00 EDT (10 PM) in New York
    pref = NotificationPreference(
        user_id=1,
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="08:00",
        timezone="America/New_York",
    )

    # 02:30 UTC = 22:30 NY time (inside quiet hours)
    ny_target = datetime(2026, 9, 14, 2, 30, tzinfo=ZoneInfo("UTC"))
    is_quiet = NotificationPolicyEngine.is_in_quiet_hours(pref, target_dt=ny_target)
    assert is_quiet is True

    # 18:00 UTC = 14:00 NY time (outside quiet hours)
    day_target = datetime(2026, 9, 14, 18, 0, tzinfo=ZoneInfo("UTC"))
    assert NotificationPolicyEngine.is_in_quiet_hours(pref, target_dt=day_target) is False


def test_16_policy_engine_respects_category_preferences():
    pref = NotificationPreference(
        user_id=1,
        quiet_hours_enabled=False,
        sales_alerts=False,  # Disabled by user
        payment_alerts=True,
    )

    sales_payload = NotificationEventPayload(
        event_id="e4",
        event_type="POSITIVE_REPLY",
        priority=NotificationPriority.HIGH,
        category=NotificationCategory.SALES,
        title="Hot Lead",
        body="Call me tomorrow",
        deduplication_key="sales:1",
    )
    decision = NotificationPolicyEngine.evaluate(sales_payload, pref)
    assert decision.should_record_in_app is True
    assert decision.should_push is False
    assert decision.reason == "SUPPRESSED_CATEGORY_SALES"


# =============================================================================
# 17-18: Deduplication Tests
# =============================================================================

def test_17_deduplicator_prevents_duplicate_within_window(sync_db, sample_user):
    key = f"payment_verified:test_{datetime.utcnow().timestamp()}"

    # First check: not duplicate
    is_dup, _ = NotificationDeduplicator.check_duplicate(sync_db, sample_user.id, key)
    assert is_dup is False

    # Insert notification
    notif = Notification(
        user_id=sample_user.id,
        event_id="evt_test_dedupe",
        deduplication_key=key,
        event_type="PAYMENT_VERIFIED",
        category="FINANCIAL",
        priority="HIGH",
        title="Payment Verified",
        body="$100 received",
        is_read=False,
    )
    sync_db.add(notif)
    sync_db.commit()

    # Second check: duplicate detected!
    is_dup, existing = NotificationDeduplicator.check_duplicate(sync_db, sample_user.id, key)
    assert is_dup is True
    assert existing is not None
    assert existing.id == notif.id


def test_18_deduplicator_allows_different_event_types_for_same_entity(sync_db, sample_user):
    entity_id = 888
    key_proposal = f"proposal_sent:{entity_id}"
    key_won = f"deal_won:{entity_id}"

    notif = Notification(
        user_id=sample_user.id,
        event_id="evt_prop_1",
        deduplication_key=key_proposal,
        event_type="PROPOSAL_SENT",
        category="SALES",
        priority="NORMAL",
        title="Proposal Sent",
        body="Sent proposal",
        is_read=False,
    )
    sync_db.add(notif)
    sync_db.commit()

    # Different event type key should NOT be duplicate
    is_dup, _ = NotificationDeduplicator.check_duplicate(sync_db, sample_user.id, key_won)
    assert is_dup is False


# =============================================================================
# 19-20: Device Registration & Management Tests
# =============================================================================

def test_19_device_registration_creates_and_activates_device(sync_db, sample_user):
    service = NotificationService()
    req = DeviceRegistrationRequest(
        device_name="CEO Pixel 9 Pro",
        device_type="mobile_android",
        endpoint="https://fcm.googleapis.com/fcm/send/test-endpoint-19",
        p256dh="test_p256dh_key_base64",
        auth_token="test_auth_secret_token",
    )

    device = service.register_device(sample_user.id, req)
    assert device.id is not None
    assert device.user_id == sample_user.id
    assert device.device_name == "CEO Pixel 9 Pro"
    assert device.is_active is True

    # Refresh / update same endpoint
    req_updated = DeviceRegistrationRequest(
        device_name="CEO Pixel 9 Pro (Updated)",
        device_type="mobile_android",
        endpoint="https://fcm.googleapis.com/fcm/send/test-endpoint-19",
        p256dh="test_p256dh_key_base64_v2",
        auth_token="test_auth_secret_token_v2",
    )
    updated_device = service.register_device(sample_user.id, req_updated)
    assert updated_device.id == device.id
    assert updated_device.device_name == "CEO Pixel 9 Pro (Updated)"
    assert updated_device.is_active is True


def test_20_device_unregistration_deactivates_device(sync_db, sample_user):
    service = NotificationService()
    req = DeviceRegistrationRequest(
        device_name="Old Tablet",
        device_type="tablet",
        endpoint="https://fcm.googleapis.com/fcm/send/test-endpoint-20",
        p256dh="test_key_20",
        auth_token="test_auth_20",
    )
    dev = service.register_device(sample_user.id, req)
    assert dev.is_active is True

    unreg_success = service.unregister_device(sample_user.id, dev.id)
    assert unreg_success is True

    deactivated = sync_db.query(NotificationDevice).filter_by(id=dev.id).first()
    assert deactivated.is_active is False


# =============================================================================
# 21-24: Multi-Device Delivery & Dispatcher Tests
# =============================================================================

@pytest.mark.asyncio
async def test_21_multi_device_delivery_sends_to_all_active_devices(sync_db, sample_user):
    # Setup 3 devices: Laptop, Phone, Tablet
    devices = []
    for i, name in enumerate(["MacBook Pro", "Android Phone", "iPad Pro"]):
        dev = NotificationDevice(
            user_id=sample_user.id,
            device_name=name,
            device_type="device",
            endpoint=f"mock://push.service.com/dev_{i}_{datetime.utcnow().timestamp()}",
            p256dh="test_p256",
            auth_token="test_auth",
            is_active=True,
        )
        sync_db.add(dev)
        devices.append(dev)
    sync_db.commit()

    # Create notification
    notif = Notification(
        user_id=sample_user.id,
        event_id="evt_multi_dev",
        deduplication_key=f"multi_dev:{datetime.utcnow().timestamp()}",
        event_type="PAYMENT_VERIFIED",
        category="FINANCIAL",
        priority="HIGH",
        title="High Value Deal Closed",
        body="$10,000 received",
        is_read=False,
    )
    sync_db.add(notif)
    sync_db.commit()

    mock_provider = MagicMock(spec=BaseNotificationProvider)
    mock_provider.channel_name = "web_push"
    mock_provider.send = AsyncMock(return_value=SendResult(success=True, status_code=201))

    dispatcher = NotificationDispatcher(providers={"web_push": mock_provider})
    results = await dispatcher.dispatch_notification(notif.id)

    # Provider should have been called for all active devices
    assert len(results) >= 3
    assert all(r is True for r in results)
    assert mock_provider.send.call_count >= 3


@pytest.mark.asyncio
async def test_22_dispatcher_records_delivery_audit_log(sync_db, sample_user):
    dev = NotificationDevice(
        user_id=sample_user.id,
        device_name="Audit Device",
        device_type="mobile",
        endpoint="mock://push.service.com/audit_device",
        p256dh="p256",
        auth_token="auth",
        is_active=True,
    )
    sync_db.add(dev)

    notif = Notification(
        user_id=sample_user.id,
        event_id="evt_audit",
        deduplication_key=f"audit:{datetime.utcnow().timestamp()}",
        event_type="SEV1_INCIDENT",
        category="PRODUCTION",
        priority="CRITICAL",
        title="SEV-1 Audit Alert",
        body="Testing audit log recording",
        is_read=False,
    )
    sync_db.add(notif)
    sync_db.commit()

    mock_provider = MagicMock(spec=BaseNotificationProvider)
    mock_provider.channel_name = "web_push"
    mock_provider.send = AsyncMock(return_value=SendResult(success=True, status_code=201))

    dispatcher = NotificationDispatcher(providers={"web_push": mock_provider})
    await dispatcher.dispatch_to_device(notif.id, dev.id, channel="web_push")

    # Check NotificationDelivery row in database
    delivery = (
        sync_db.query(NotificationDelivery)
        .filter_by(notification_id=notif.id, device_id=dev.id)
        .first()
    )
    assert delivery is not None
    assert delivery.status == "DELIVERED"
    assert delivery.attempts == 1
    assert delivery.delivered_at is not None


@pytest.mark.asyncio
async def test_23_dispatcher_handles_provider_failure_gracefully(sync_db, sample_user):
    dev = NotificationDevice(
        user_id=sample_user.id,
        device_name="Failing Device",
        device_type="mobile",
        endpoint="mock://push.service.com/failing_device",
        p256dh="p256",
        auth_token="auth",
        is_active=True,
    )
    sync_db.add(dev)

    notif = Notification(
        user_id=sample_user.id,
        event_id="evt_fail",
        deduplication_key=f"fail:{datetime.utcnow().timestamp()}",
        event_type="TEST_FAIL",
        category="SYSTEM",
        priority="NORMAL",
        title="Test Failure Alert",
        body="Simulating push network drop",
        is_read=False,
    )
    sync_db.add(notif)
    sync_db.commit()

    # Provider raises network exception
    mock_provider = MagicMock(spec=BaseNotificationProvider)
    mock_provider.channel_name = "web_push"
    mock_provider.send = AsyncMock(side_effect=ConnectionResetError("Socket reset by peer"))

    dispatcher = NotificationDispatcher(
        providers={"web_push": mock_provider},
        max_attempts=2,
        initial_backoff_seconds=0.01,
    )

    # Invariant: Dispatcher MUST NOT raise exceptions to caller
    success = await dispatcher.dispatch_to_device(notif.id, dev.id, channel="web_push")
    assert success is False

    delivery = (
        sync_db.query(NotificationDelivery)
        .filter_by(notification_id=notif.id, device_id=dev.id)
        .first()
    )
    assert delivery is not None
    assert delivery.status == "FAILED"
    assert "Socket reset" in (delivery.last_error or "")


@pytest.mark.asyncio
async def test_24_expired_subscription_deactivates_device(sync_db, sample_user):
    dev = NotificationDevice(
        user_id=sample_user.id,
        device_name="Expired Mobile",
        device_type="mobile_android",
        endpoint="https://fcm.googleapis.com/fcm/send/expired_token",
        p256dh="p256",
        auth_token="auth",
        is_active=True,
    )
    sync_db.add(dev)

    notif = Notification(
        user_id=sample_user.id,
        event_id="evt_expired",
        deduplication_key=f"exp:{datetime.utcnow().timestamp()}",
        event_type="PROPOSAL_SENT",
        category="SALES",
        priority="NORMAL",
        title="Proposal Notification",
        body="Testing 410 Gone handling",
        is_read=False,
    )
    sync_db.add(notif)
    sync_db.commit()

    mock_provider = MagicMock(spec=BaseNotificationProvider)
    mock_provider.channel_name = "web_push"
    mock_provider.send = AsyncMock(
        return_value=SendResult(
            success=False,
            status_code=410,
            error="Subscription has expired",
            device_unregistered=True,
        )
    )

    dispatcher = NotificationDispatcher(providers={"web_push": mock_provider})
    await dispatcher.dispatch_to_device(notif.id, dev.id, channel="web_push")

    # Verify device was deactivated
    sync_db.refresh(dev)
    assert dev.is_active is False

    deliv = (
        sync_db.query(NotificationDelivery)
        .filter_by(notification_id=notif.id, device_id=dev.id)
        .first()
    )
    assert deliv.status == "UNREGISTERED"


# =============================================================================
# 25: Test Notification Endpoint Verification
# =============================================================================

@pytest.mark.asyncio
async def test_25_test_notification_endpoint_creates_verified_alert(sample_user):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Trigger test payment notification
        resp = await client.post(
            "/api/notifications/test-event",
            json={
                "event_type": "TEST_PAYMENT_VERIFIED",
                "title": "Verified Advance: $5,000.00",
                "body": "Advance received from Bright Horizons Dental via Titan Mailbox.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        notif = data["notification"]
        assert notif["event_type"] == "TEST_PAYMENT_VERIFIED"
        assert notif["priority"] == "HIGH"
        assert notif["metadata_safe"]["is_test"] is True
        assert notif["is_read"] is False

        # Verify unread count endpoint
        count_resp = await client.get("/api/notifications/unread-count")
        assert count_resp.status_code == 200
        assert count_resp.json()["unread_count"] >= 1

        # Mark read endpoint
        read_resp = await client.post(f"/api/notifications/{notif['id']}/read")
        assert read_resp.status_code == 200
        assert read_resp.json()["success"] is True

        # Check VAPID public key endpoint
        vapid_resp = await client.get("/api/notifications/vapid-public-key")
        assert vapid_resp.status_code == 200
        assert len(vapid_resp.json()["public_key"]) > 20
