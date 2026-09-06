import pytest
from httpx import AsyncClient, ASGITransport
from bs4 import BeautifulSoup
from app.api.app import app
from app.core.security import create_session_token

@pytest.mark.asyncio
async def test_owner_dashboard_html_structure():
    """Verify owner dashboard HTML has exactly the required architecture and no fake hardcoded data."""
    transport = ASGITransport(app=app)
    admin_token = create_session_token("admin", role="admin")

    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": admin_token}) as client:
        res = await client.get("/dashboard")
        assert res.status_code == 200
        html = res.text
        soup = BeautifulSoup(html, "html.parser")

        # 1. Verify 6 primary KPI elements
        assert soup.find(id="ceo-val-revenue") is not None, "Missing Revenue KPI element"
        assert soup.find(id="val-pipeline") is not None, "Missing Pipeline KPI element"
        assert soup.find(id="val-qualified") is not None, "Missing Qualified Leads KPI element"
        assert soup.find(id="val-outreach-sent") is not None, "Missing Outreach Sent KPI element"
        assert soup.find(id="ceo-val-replies-pending") is not None, "Missing Replies Pending KPI element"
        assert soup.find(id="ceo-val-deals-won") is not None, "Missing Deals Won KPI element"

        # 2. Verify Sales Funnel elements (7 stages)
        assert soup.find(id="funnel-c-discovered") is not None
        assert soup.find(id="funnel-c-qualified") is not None
        assert soup.find(id="funnel-c-contacted") is not None
        assert soup.find(id="funnel-c-replied") is not None
        assert soup.find(id="funnel-c-meeting") is not None
        assert soup.find(id="funnel-c-proposal") is not None
        assert soup.find(id="funnel-c-won") is not None

        # 3. Verify Empty Revenue chart state
        assert soup.find(id="ceo-empty-chart") is not None
        assert "No real revenue data yet" in html

        # 4. Verify Needs Your Attention section
        assert soup.find(id="owner-attention-card") is not None
        assert soup.find(id="owner-attention-items") is not None
        assert soup.find(id="attention-status-badge") is not None

        # 5. Verify Operational Safeguards section
        assert soup.find(id="owner-safeguards-card") is not None

        # 6. Verify Infrastructure view container
        assert soup.find(id="view-infra") is not None
        assert soup.find(id="infra-subsystems-list") is not None
        assert soup.find(id="infra-worker-stats") is not None

        # 7. Verify NO hardcoded fake messages in overview
        assert "Dr. Michael T." not in html, "Fake hardcoded message detected"
        assert "Sarah K." not in html, "Fake hardcoded message detected"

@pytest.mark.asyncio
async def test_owner_attention_endpoint():
    """Verify GET /api/owner/attention returns structured owner alerts or nominal state."""
    transport = ASGITransport(app=app)
    admin_token = create_session_token("admin", role="admin")

    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": admin_token}) as client:
        res = await client.get("/api/owner/attention")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "count" in data
        assert "status" in data
        assert data["status"] in ("ALL_CLEAR", "ATTENTION_REQUIRED")

@pytest.mark.asyncio
async def test_proposals_list_endpoint():
    """Verify GET /api/proposals is active and returns proposals array."""
    transport = ASGITransport(app=app)
    admin_token = create_session_token("admin", role="admin")

    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": admin_token}) as client:
        res = await client.get("/api/proposals")
        assert res.status_code == 200
        data = res.json()
        assert "proposals" in data
        assert isinstance(data["proposals"], list)
