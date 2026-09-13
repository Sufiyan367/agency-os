import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.app import app
from app.database.connection import get_db
from app.database.models import Business, OutreachMessage, OutreachStatus
from app.core.security import create_session_token

@pytest.mark.asyncio
async def test_approve_outreach_json_body_parsing(db_session: AsyncSession):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        # Setup test business & message
        biz = Business(name="Test Corp", domain="testcorp123.com", country="US", niche="Technology Services")
        db_session.add(biz)
        await db_session.flush()

        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email="ceo@testcorp123.com",
            subject="Audit",
            body="Audit body content with unsubscribe notice.",
            status=OutreachStatus.PENDING_APPROVAL.value
        )
        db_session.add(msg)
        await db_session.commit()

        token = create_session_token("admin", "admin")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Test POST with JSON body {"force_live": true, "auto_send": false}
            resp = await ac.post(
                f"/api/queue/{msg.id}/approve",
                json={"force_live": True, "auto_send": False, "actor": "HUMAN"},
                headers={"Cookie": f"agency_session={token}"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "APPROVED"
            assert data["message_id"] == msg.id
            assert data["actor"] == "HUMAN"
    finally:
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_approve_outreach_query_param_parsing(db_session: AsyncSession):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        biz = Business(name="Query Test LLC", domain="querytestllc.com", country="US", niche="Technology Services")
        db_session.add(biz)
        await db_session.flush()

        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email="ops@querytestllc.com",
            subject="Audit Query",
            body="Audit body content with unsubscribe footer.",
            status=OutreachStatus.PENDING_APPROVAL.value
        )
        db_session.add(msg)
        await db_session.commit()

        token = create_session_token("admin", "admin")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Test POST with query parameters ?auto_send=false&force_live=true
            resp = await ac.post(
                f"/api/queue/{msg.id}/approve?auto_send=false&force_live=true",
                headers={"Cookie": f"agency_session={token}"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "APPROVED"
    finally:
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_deliverability_readiness_endpoint(db_session: AsyncSession):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_session_token("admin", "admin")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/email/deliverability-readiness",
                headers={"Cookie": f"agency_session={token}"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "active_provider" in data
            assert "compliance" in data
            assert "daily_cap" in data
            assert "outreach_lock" in data
    finally:
        app.dependency_overrides.clear()

