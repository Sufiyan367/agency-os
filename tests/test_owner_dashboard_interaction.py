import pytest
import subprocess
from httpx import AsyncClient, ASGITransport
from bs4 import BeautifulSoup
from app.api.app import app
from app.core.security import create_session_token

def test_app_js_syntax_integrity():
    """Verify app.js parses with Node with zero syntax errors."""
    res = subprocess.run(["node", "-c", "app/frontend/static/app.js"], capture_output=True, text=True)
    assert res.returncode == 0, f"app.js syntax error: {res.stderr}"

@pytest.mark.asyncio
async def test_owner_dashboard_elements_and_dynamic_wiring():
    """Verify owner dashboard has clean non-mock states and required interactive elements."""
    transport = ASGITransport(app=app)
    admin_token = create_session_token("admin", role="admin")

    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": admin_token}) as client:
        res = await client.get("/dashboard")
        assert res.status_code == 200
        html = res.text
        soup = BeautifulSoup(html, "html.parser")

        # 1. No hardcoded fake business in Current Prospect card
        assert "Sunrise Dental Care" not in html, "Hardcoded fake business name detected in HTML"
        assert soup.find(id="ceo-active-prospect-name") is not None
        assert soup.find(id="ceo-active-prospect-domain") is not None
        assert soup.find(id="ceo-active-prospect-stage") is not None
        assert soup.find(id="btn-view-active-prospect") is not None

        # 2. Activity and Inbound list containers exist
        assert soup.find(id="ceo-recent-activity-list") is not None
        assert soup.find(id="recent-messages-list") is not None

        # 3. Global search input
        assert soup.find(id="global-search-input") is not None

        # 4. Safeguard chips
        assert soup.find(id="owner-outreach-chip-status") is not None
        assert soup.find(id="owner-payment-chip-status") is not None
        assert soup.find(id="owner-loop-chip-status") is not None
        assert soup.find(id="owner-floor-chip-status") is not None

@pytest.mark.asyncio
async def test_dashboard_api_data_contracts():
    """Verify that backend endpoints needed by the Owner Dashboard return expected JSON schemas."""
    transport = ASGITransport(app=app)
    admin_token = create_session_token("admin", role="admin")

    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": admin_token}) as client:
        # Agent status
        r_status = await client.get("/api/agent/status")
        assert r_status.status_code == 200
        status_data = r_status.json()
        assert "status" in status_data
        assert "safety_guardrails" in status_data

        # Activity events
        r_act = await client.get("/api/agent/activity?limit=6")
        assert r_act.status_code == 200
        act_data = r_act.json()
        assert "events" in act_data or isinstance(act_data, list)

        # Inbound replies
        r_replies = await client.get("/api/replies?limit=4")
        assert r_replies.status_code == 200
        assert isinstance(r_replies.json(), list)

        # Owner attention
        r_att = await client.get("/api/owner/attention")
        assert r_att.status_code == 200
        att_data = r_att.json()
        assert "items" in att_data
        assert "status" in att_data
