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
