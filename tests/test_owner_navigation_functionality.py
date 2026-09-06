import pytest
from httpx import AsyncClient, ASGITransport
from bs4 import BeautifulSoup
from app.api.app import app
from app.core.security import create_session_token
from app.core.config import settings

@pytest.mark.asyncio
async def test_owner_sidebar_and_view_containers_alignment():
    """Verify every sidebar navigation item has a matching view container in the DOM."""
    transport = ASGITransport(app=app)
    admin_token = create_session_token("admin", role="admin")

    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": admin_token}) as client:
        res = await client.get("/dashboard")
        assert res.status_code == 200
        soup = BeautifulSoup(res.text, "html.parser")

        # Required views
        required_views = [
            "overview",
            "leads",
            "markets",
            "queue",
            "pipeline",
            "payments",
            "decision-analytics",
            "infra",
            "settings"
        ]

        for view_name in required_views:
            nav_item = soup.find(attrs={"data-view": view_name})
            assert nav_item is not None, f"Missing nav item for view: {view_name}"
            view_elem = soup.find(id=f"view-{view_name}")
            assert view_elem is not None, f"Missing view container: #view-{view_name}"

@pytest.mark.asyncio
async def test_safety_invariants_strictly_active():
    """Verify production safety dry-run flags remain strictly enabled."""
    assert getattr(settings, "EMAIL_DRY_RUN", False) is True, "EMAIL_DRY_RUN must remain True"
    assert getattr(settings, "PAYMENTS_ENABLED", True) is False, "PAYMENTS_ENABLED must remain False"
    assert getattr(settings, "PAYMENT_DRY_RUN", False) is True, "PAYMENT_DRY_RUN must remain True"
    assert getattr(settings, "VOICE_DRY_RUN", False) is True, "VOICE_DRY_RUN must remain True"
    assert getattr(settings, "DRY_RUN", False) is True, "DRY_RUN must remain True"
