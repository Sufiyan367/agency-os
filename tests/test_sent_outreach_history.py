import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.app import app
from app.database.models import (
    Base, Business, Offer, OutreachMessage, OutreachStatus, Reply, FollowupSequence, FollowupStatus
)
from app.database.connection import get_db

from app.api.routes import classify_outreach_record


@pytest.fixture
def mock_messages():
    # 1. Real external message
    biz_ext = Business(
        id=101,
        name="Apex Plumbing Ltd",
        domain="apexplumbing.co.uk",
        country="UK",
        city="London",
        niche="Plumbing",
        pipeline_stage="OUTREACH_SENT"
    )
    msg_ext = OutreachMessage(
        id=1,
        business_id=101,
        recipient_email="service@apexplumbing.co.uk",
        subject="Question regarding apexplumbing.co.uk",
        body="Hi Apex team, noticed your website needs optimization.",
        status=OutreachStatus.SENT.value,
        provider="titan",
        provider_message_id="msg_live_12345",
        sent_at=datetime(2026, 9, 16, 12, 0, 0)
    )

    # 2. Canary message (internal domain)
    biz_can = Business(
        id=102,
        name="Canary Test Co",
        domain="automatedagencyos.tech",
        country="US",
        city="San Francisco",
        niche="Tech",
        pipeline_stage="OUTREACH_SENT"
    )
    msg_can = OutreachMessage(
        id=2,
        business_id=102,
        recipient_email="hello@automatedagencyos.tech",
        subject="Canary verification email",
        body="Verifying live SMTP transport pipeline.",
        status=OutreachStatus.SENT.value,
        provider="titan",
        provider_message_id="canary_9999",
        sent_at=datetime(2026, 9, 17, 1, 0, 0)
    )

    # 3. Test / mock message
    biz_test = Business(
        id=103,
        name="Test Fixture Biz",
        domain="fixture.example.com",
        country="US",
        city="Austin",
        niche="HVAC",
        pipeline_stage="OUTREACH_SENT"
    )
    msg_test = OutreachMessage(
        id=3,
        business_id=103,
        recipient_email="info@fixture.example.com",
        subject="Mock outreach",
        body="Mock body text",
        status="MOCKED_SENT",
        provider="mock",
        sent_at=datetime(2026, 9, 16, 14, 0, 0)
    )

    # 4. Historical dev message (pre-Sept 15, no provider)
    biz_hist = Business(
        id=104,
        name="Historical Roofing",
        domain="historicalroofing.com",
        country="US",
        city="Chicago",
        niche="Roofing",
        pipeline_stage="OUTREACH_SENT"
    )
    msg_hist = OutreachMessage(
        id=4,
        business_id=104,
        recipient_email="contact@historicalroofing.com",
        subject="Early scaffolding outreach",
        body="Historical pre-live message",
        status=OutreachStatus.SENT.value,
        provider=None,
        sent_at=datetime(2026, 9, 12, 10, 0, 0)
    )

    return [
        (msg_ext, biz_ext),
        (msg_can, biz_can),
        (msg_test, biz_test),
        (msg_hist, biz_hist)
    ]


def test_sent_record_classification(mock_messages):
    (msg_ext, biz_ext), (msg_can, biz_can), (msg_test, biz_test), (msg_hist, biz_hist) = mock_messages
    
    assert classify_outreach_record(msg_ext, biz_ext) == "REAL_EXTERNAL"
    assert classify_outreach_record(msg_can, biz_can) == "CANARY"
    assert classify_outreach_record(msg_test, biz_test) == "TEST"
    assert classify_outreach_record(msg_hist, biz_hist) == "HISTORICAL"


@pytest.mark.asyncio
async def test_sent_history_api_integration():
    # Setup in-memory SQLite DB
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # Seed test data
        b1 = Business(
            id=1, name="Vanquish Real Estate", domain="vanquishrealestate.com",
            country="UK", city="London", niche="Real Estate", pipeline_stage="OUTREACH_SENT"
        )
        b2 = Business(
            id=2, name="Canary Test Operations", domain="automatedagencyos.tech",
            country="US", city="San Francisco", niche="Software", pipeline_stage="OUTREACH_SENT"
        )
        b3 = Business(
            id=3, name="Historical Agency Corp", domain="historicalagency.com",
            country="IE", city="Dublin", niche="Legal", pipeline_stage="OUTREACH_SENT"
        )
        session.add_all([b1, b2, b3])
        await session.flush()

        off = Offer(
            id=1, business_id=1, service_type="WEBSITE_TURNAROUND",
            title="Website Turnaround", recommended_price=650.0
        )
        session.add(off)
        await session.flush()

        m1 = OutreachMessage(
            id=1, business_id=1, offer_id=1, recipient_email="info@vanquishrealestate.com",
            subject="Question regarding vanquishrealestate.com",
            body="Hi Vanquish team, reviewing your property portal...",
            status="SENT", provider="titan", provider_message_id="titan_real_1",
            sent_at=datetime(2026, 9, 16, 21, 33, 0)
        )
        m2 = OutreachMessage(
            id=2, business_id=2, recipient_email="hello@automatedagencyos.tech",
            subject="Canary delivery probe",
            body="Canary probe body",
            status="SENT", provider="titan", provider_message_id="canary_id_2",
            sent_at=datetime(2026, 9, 17, 1, 0, 0)
        )
        m3 = OutreachMessage(
            id=3, business_id=3, recipient_email="info@historicalagency.com",
            subject="Historical scaffolding send",
            body="Historical pre-live body",
            status="SENT", provider=None,
            sent_at=datetime(2026, 9, 12, 10, 0, 0)
        )
        session.add_all([m1, m2, m3])
        await session.flush()

        # Add reply for m1
        rep = Reply(
            id=1, business_id=1, outreach_message_id=1, sender_email="info@vanquishrealestate.com",
            raw_body="Thanks for the note, can you share more details?",
            classification="INTERESTED", is_handled=False
        )
        # Add follow-up for m1
        fu = FollowupSequence(
            id=1, initial_message_id=1, step_number=2, scheduled_for=datetime.utcnow() + timedelta(days=3),
            subject="Follow-up regarding vanquishrealestate.com", body="Following up...",
            status=FollowupStatus.SCHEDULED.value
        )
        session.add_all([rep, fu])
        await session.commit()

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test Default Category: real_external
        resp = await client.get("/api/outreach/sent?category=real_external")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matching"] == 1
        assert data["category_counts"]["real_external"] == 1
        assert data["category_counts"]["canary"] == 1
        assert data["category_counts"]["historical_test"] == 1
        assert data["category_counts"]["all"] == 3

        item = data["items"][0]
        assert item["message_id"] == 1
        assert item["business_name"] == "Vanquish Real Estate"
        assert item["recipient"] == "info@vanquishrealestate.com"
        assert item["record_type"] == "REAL_EXTERNAL"
        assert item["has_reply"] is True
        assert item["reply_status"] == "INTERESTED"
        assert item["followup_status"] == "SCHEDULED"

        # 2. Test Category: canary
        resp_can = await client.get("/api/outreach/sent?category=canary")
        assert resp_can.status_code == 200
        can_data = resp_can.json()
        assert can_data["total_matching"] == 1
        assert can_data["items"][0]["recipient"] == "hello@automatedagencyos.tech"
        assert can_data["items"][0]["record_type"] == "CANARY"

        # 3. Test Category: all
        resp_all = await client.get("/api/outreach/sent?category=all")
        assert resp_all.status_code == 200
        all_data = resp_all.json()
        assert all_data["total_matching"] == 3

        # 4. Test Search filter
        resp_search = await client.get("/api/outreach/sent?category=all&search=vanquish")
        assert resp_search.status_code == 200
        assert resp_search.json()["total_matching"] == 1
        assert resp_search.json()["items"][0]["business_name"] == "Vanquish Real Estate"

        # 5. Test Detail Endpoint
        resp_det = await client.get("/api/outreach/sent/1")
        assert resp_det.status_code == 200
        det_data = resp_det.json()
        assert det_data["message_id"] == 1
        assert "Hi Vanquish team" in det_data["body"]
        assert det_data["reply"] is not None
        assert det_data["reply"]["classification"] == "INTERESTED"
        assert len(det_data["followups"]) == 1

        # 6. Test 404 for non-existent detail
        resp_404 = await client.get("/api/outreach/sent/9999")
        assert resp_404.status_code == 404

    app.dependency_overrides.clear()
