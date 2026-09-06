import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.core.security import create_session_token
from app.core.config import settings

@pytest.mark.asyncio
async def test_client_access_redirects_and_portal_serving(monkeypatch):
    """Verify client role is redirected away from owner dashboard and served client portal."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    client_token = create_session_token("director@simulated-lead-4b47e3.co.uk", role="client")

    # 1. Unauthenticated /client redirects to /login
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        r = await client.get("/client")
        assert r.status_code in (302, 307)
        assert r.headers.get("location") == "/login"

    # 2. Authenticated client accessing /client serves client portal HTML
    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": client_token}, follow_redirects=False) as client:
        r = await client.get("/client")
        assert r.status_code == 200
        assert "Client Portal" in r.text
        assert "client_portal.js" in r.text

    # 3. Authenticated client attempting to access owner /dashboard or /app is redirected to /client
    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": client_token}, follow_redirects=False) as client:
        r1 = await client.get("/dashboard")
        assert r1.status_code in (302, 307)
        assert r1.headers.get("location") == "/client"

        r2 = await client.get("/app")
        assert r2.status_code in (302, 307)
        assert r2.headers.get("location") == "/client"

@pytest.mark.asyncio
async def test_client_api_data_isolation_and_rbac_blocking(monkeypatch):
    """Verify client role is strictly 403-blocked from agency internal operational endpoints."""
    import uuid
    from app.database.connection import AsyncSessionLocal
    from app.database.models import Customer, Business, Project
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    transport = ASGITransport(app=app)
    uid = uuid.uuid4().hex[:8]
    unique_domain = f"test-client-{uid}.co.uk"
    test_email = f"director@{unique_domain}"
    company_name = f"Test Client Company {uid}"
    client_token = create_session_token(test_email, role="client")

    # Seed test customer and project
    async with AsyncSessionLocal() as session:
        biz = Business(
            name=company_name,
            domain=unique_domain,
            country="GB",
            niche="Engineering",
            public_email=test_email,
            pipeline_stage="CLOSED_WON"
        )
        session.add(biz)
        await session.flush()

        cust = Customer(
            business_id=biz.id,
            company_name=company_name,
            contact_email=test_email,
            contract_amount=1500.0,
            onboarding_status="ACTIVE"
        )
        session.add(cust)
        await session.flush()

        proj = Project(
            customer_id=cust.id,
            title="AI Automation Rollout",
            service_type="AI Automation",
            status="IN_PROGRESS"
        )
        session.add(proj)
        await session.commit()

    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": client_token}) as client:
        # Blocked endpoints (Agency internal operations)
        blocked_routes = [
            "/api/metrics",
            "/api/leads",
            "/api/deals",
            "/api/queue",
            "/api/markets",
            "/api/proposals",
            "/api/owner/attention",
            "/api/agent/status",
            "/api/production/health",
            "/api/worker/status",
        ]
        for route in blocked_routes:
            res = await client.get(route)
            assert res.status_code == 403, f"Expected 403 on {route} for client role, got {res.status_code}"

        # Allowed client endpoint: /api/client/portal-data
        p_res = await client.get("/api/client/portal-data")
        assert p_res.status_code == 200
        p_data = p_res.json()
        assert p_data.get("has_account") is True
        assert p_data.get("company_name") == company_name
        assert "projects" in p_data
        assert "deliverables" in p_data
        assert "payments" in p_data
        # Verify no leakage of internal pipeline/metrics
        assert "pipeline_value_usd" not in p_data
        assert "leads_total" not in p_data
