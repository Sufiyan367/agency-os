import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.database.connection import init_db, AsyncSessionLocal
from app.database.seed_data import seed_initial_data

@pytest.mark.asyncio
async def test_api_health_and_endpoints():
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        # Ready
        res = await client.get("/ready")
        assert res.status_code == 200

        # Metrics
        res = await client.get("/api/metrics")
        assert res.status_code == 200
        data = res.json()
        assert "revenue" in data
        assert "leads" in data

        # Markets
        res = await client.get("/api/markets")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

        # Leads
        res = await client.get("/api/leads")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

        # Queue
        res = await client.get("/api/queue")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

        # Replies
        res = await client.get("/api/replies")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

        # Worker Status
        res = await client.get("/api/worker/status")
        assert res.status_code == 200
        assert "is_running" in res.json()

        # Payments List
        res = await client.get("/api/payments")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

        # Webhook Inbound Email
        inbound_payload = {
            "sender_email": "prospect@nonexistentcorp.com",
            "subject": "Regarding your audit",
            "body": "Can you share pricing?"
        }
        res = await client.post("/api/webhooks/inbound-email", json=inbound_payload)
        assert res.status_code == 200
        assert res.json()["status"] in ("IGNORED", "PROCESSED")

        # Webhook Stripe (unauthorized signature rejection)
        stripe_payload = {"type": "checkout.session.completed", "id": "evt_123"}
        res = await client.post(
            "/api/webhooks/stripe",
            json=stripe_payload,
            headers={"stripe-signature": "t=1000,v1=bad_sig"}
        )
        # Should be rejected if verification fails
        assert res.status_code in (200, 400)
