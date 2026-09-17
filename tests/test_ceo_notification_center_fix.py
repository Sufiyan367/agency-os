import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.config import settings

@pytest.mark.asyncio
async def test_notification_center_and_mobile_dom_elements(monkeypatch):
    """Verify notification drawer, dynamic badges, 5-item mobile nav, and More sheet render in /dashboard."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/dashboard")
        assert r.status_code == 200
        html = r.text

        # 1. Topbar Bell & Badge
        assert 'id="btn-notification-center"' in html
        assert 'id="notif-badge"' in html
        assert 'onclick="toggleNotificationCenter()"' not in html  # Cleanly bound via JS, no inline double-firing

        # 2. Notification Center Drawer & Controls
        assert 'id="notification-drawer"' in html
        assert 'id="notification-drawer-backdrop"' in html
        assert 'id="btn-close-notif-drawer"' in html
        assert 'id="btn-mark-all-read"' in html
        assert 'id="btn-enable-push"' in html
        assert 'id="notification-list-items"' in html
        assert '/static/notification_center.js' in html

        # 3. Mobile Bottom Navigation (5 items: Home, Activity, Sales, Alerts, More)
        assert 'class="mobile-bottom-nav"' in html
        assert 'data-view="overview"' in html
        assert 'data-view="queue"' in html
        assert 'data-view="pipeline"' in html
        assert 'id="mobile-bottom-notif-btn"' in html
        assert 'id="mobile-bottom-notif-badge"' in html
        assert 'id="btn-mobile-more"' in html

        # 4. Mobile "More" Slide-up Sheet
        assert 'id="mobile-more-sheet"' in html
        assert 'id="mobile-more-backdrop"' in html
        assert 'All Operating Domains' in html
        assert 'toggleMobileMoreSheet' in html

@pytest.mark.asyncio
async def test_pwa_manifest_endpoints():
    """Verify both /manifest.json and /manifest.webmanifest serve valid PWA configuration."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # /manifest.json
        r_json = await client.get("/manifest.json")
        assert r_json.status_code == 200
        data_json = r_json.json()
        assert data_json.get("start_url") == "/dashboard"
        assert data_json.get("display") == "standalone"

        # /manifest.webmanifest
        r_web = await client.get("/manifest.webmanifest")
        assert r_web.status_code == 200
        data_web = r_web.json()
        assert data_web.get("start_url") == "/dashboard"
        assert data_web.get("display") == "standalone"

@pytest.mark.asyncio
async def test_service_worker_serving():
    """Verify /sw.js is served with proper headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/sw.js")
        assert r.status_code == 200
        assert "ServiceWorker" in r.text or "push" in r.text
        assert r.headers.get("service-worker-allowed") == "/"

@pytest.mark.asyncio
async def test_notification_api_lifecycle(monkeypatch):
    """Verify notification unread count, list, mark read, mark all read, and test event."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unread count
        r_count = await client.get("/api/notifications/unread-count")
        assert r_count.status_code == 200
        assert "unread_count" in r_count.json()

        # 2. Trigger test event
        r_test = await client.post(
            "/api/notifications/test-event",
            json={"event_type": "TEST_PAYMENT_VERIFIED"},
        )
        assert r_test.status_code == 200
        test_data = r_test.json()
        assert test_data.get("success") is True
        notif = test_data.get("notification")
        assert notif is not None
        notif_id = notif.get("id")

        # 3. List notifications
        r_list = await client.get("/api/notifications?page_size=10")
        assert r_list.status_code == 200
        items = r_list.json().get("items", [])
        assert len(items) > 0
        assert any(item["id"] == notif_id for item in items)

        # 4. Mark single read
        r_mark = await client.post(f"/api/notifications/{notif_id}/read")
        assert r_mark.status_code == 200
        assert r_mark.json().get("success") is True

        # 5. Mark all read
        r_read_all = await client.post("/api/notifications/read-all")
        assert r_read_all.status_code == 200
        assert r_read_all.json().get("success") is True

        # Unread count should now be 0
        r_count_after = await client.get("/api/notifications/unread-count")
        assert r_count_after.status_code == 200
        assert r_count_after.json().get("unread_count") == 0

@pytest.mark.asyncio
async def test_device_registration_and_revocation(monkeypatch):
    """Verify registering a device, listing it, and revoking it."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg_payload = {
            "device_name": "Test iPhone 14",
            "device_type": "mobile_ios",
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-unique-123",
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcPP313T59P2O_EQU3UajYnUMxWbspC9qWodPtYY-5G20",
            "auth_token": "tBHItJI5svbpez7KI4CCXg",
        }
        r_reg = await client.post("/api/notifications/devices", json=reg_payload)
        assert r_reg.status_code == 200
        dev_data = r_reg.json()
        assert dev_data.get("device_name") == "Test iPhone 14"
        dev_id = dev_data.get("id")
        assert dev_id is not None

        # List devices
        r_list = await client.get("/api/notifications/devices")
        assert r_list.status_code == 200
        devices = r_list.json()
        assert any(d["id"] == dev_id for d in devices)

        # Revoke device
        r_del = await client.delete(f"/api/notifications/devices/{dev_id}")
        assert r_del.status_code == 200
        assert r_del.json().get("success") is True

@pytest.mark.asyncio
async def test_unauthenticated_notification_api_rejection(monkeypatch):
    """Verify that unauthenticated calls to notification APIs return 401 when auth is enabled."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        endpoints = [
            ("GET", "/api/notifications"),
            ("GET", "/api/notifications/unread-count"),
            ("POST", "/api/notifications/1/read"),
            ("POST", "/api/notifications/read-all"),
            ("GET", "/api/notifications/devices"),
            ("POST", "/api/notifications/devices"),
            ("POST", "/api/notifications/test-event"),
            ("GET", "/api/notifications/health"),
        ]
        for method, ep in endpoints:
            if method == "GET":
                r = await client.get(ep, headers={"Accept": "application/json"})
            else:
                r = await client.post(ep, json={}, headers={"Accept": "application/json"})
            assert r.status_code == 401, f"Expected 401 for {method} {ep}, got {r.status_code}"
