"""
Live Production Verification Suite:
Tests that every KPI card on the Agency OS dashboard is functional, database-backed, auditable, and clickable.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from app.api.app import app
from app.core.config import settings
from app.core.security import create_session_token
from app.database.connection import AsyncSessionLocal
from app.database.models import Business, PipelineStage

@pytest.mark.asyncio
async def test_kpi_drilldown_requires_auth():
    orig_auth = settings.AUTH_ENABLED
    try:
        settings.AUTH_ENABLED = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/dashboard/kpi-details?kpi=total_prospects")
            assert res.status_code == 401
    finally:
        settings.AUTH_ENABLED = orig_auth

@pytest.mark.asyncio
async def test_all_eight_kpis_database_backed():
    token = create_session_token("admin", role="admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": token}) as client:
        kpis = [
            "total_prospects",
            "qualified_pipeline",
            "outreach_approved",
            "interested_leads",
            "active_demos",
            "proposals_action",
            "payments_auth",
            "revenue_collected"
        ]
        for k in kpis:
            res = await client.get(f"/api/dashboard/kpi-details?kpi={k}")
            assert res.status_code == 200, f"Failed for {k}: {res.text}"
            data = res.json()
            
            # Audit contracts
            assert data["kpi"] == k
            assert "title" in data and len(data["title"]) > 0
            assert "count" in data and isinstance(data["count"], int)
            assert "definition" in data and len(data["definition"]) > 0
            assert "why_counted" in data and len(data["why_counted"]) > 0
            assert "records" in data and isinstance(data["records"], list)
            assert "pagination" in data
            assert data["pagination"]["page"] == 1
            assert data["pagination"]["total_records"] == data["count"]

@pytest.mark.asyncio
async def test_revenue_truthfulness_invariant():
    token = create_session_token("admin", role="admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": token}) as client:
        res = await client.get("/api/dashboard/kpi-details?kpi=revenue_collected")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] == 0
        assert data["summary"]["total_revenue"] == 0.0
        assert data["summary"]["revenue_label"] == "$0.00"
        assert len(data["records"]) == 0

@pytest.mark.asyncio
async def test_kpi_drilldown_search_and_pagination():
    test_ids = []
    uid = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as session:
        b1 = Business(
            name=f"Precision Roofing Specialists {uid}",
            domain=f"precision-roofing-{uid}.com",
            country="US",
            city="Houston",
            niche="roofing-contractors",
            public_email=f"info@precision-{uid}.com",
            pipeline_stage=PipelineStage.QUALIFIED.value,
            prospect_score=85.0
        )
        b2 = Business(
            name=f"Zenith Dental Clinic {uid}",
            domain=f"zenith-dental-{uid}.com",
            country="US",
            city="Dallas",
            niche="dentists",
            public_email=f"info@zenith-{uid}.com",
            pipeline_stage=PipelineStage.DISCOVERED.value,
            prospect_score=72.0
        )
        session.add_all([b1, b2])
        await session.commit()
        await session.refresh(b1)
        await session.refresh(b2)
        test_ids.extend([b1.id, b2.id])

    try:
        token = create_session_token("admin", role="admin")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", cookies={"agency_session": token}) as client:
            # 1. Test pagination limit
            res = await client.get("/api/dashboard/kpi-details?kpi=total_prospects&page=1&limit=1")
            assert res.status_code == 200
            data = res.json()
            assert len(data["records"]) == 1
            assert data["pagination"]["limit"] == 1

            # 2. Test search filter
            res_search = await client.get(f"/api/dashboard/kpi-details?kpi=total_prospects&search=Precision+Roofing")
            assert res_search.status_code == 200
            data_search = res_search.json()
            assert data_search["count"] >= 1
            found = False
            for r in data_search["records"]:
                if f"Precision Roofing Specialists {uid}" in r["name"]:
                    found = True
            assert found, "Created search prospect was not found in records"

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Business).where(Business.id.in_(test_ids)))
            await session.commit()

@pytest.mark.asyncio
async def test_dashboard_template_contains_all_clickable_kpi_cards():
    with open("app/frontend/templates/index.html", encoding="utf-8") as f:
        html = f.read()

    # 1. Check all 8 KPI onclick handlers
    required_clicks = [
        "openKpiDetailModal('total_prospects')",
        "openKpiDetailModal('qualified_pipeline')",
        "openKpiDetailModal('outreach_approved')",
        "openKpiDetailModal('interested_leads')",
        "openKpiDetailModal('active_demos')",
        "openKpiDetailModal('proposals_action')",
        "openKpiDetailModal('payments_auth')",
        "openKpiDetailModal('revenue_collected')"
    ]
    for click in required_clicks:
        assert click in html, f"Missing click handler: {click}"

    # 2. Check modal and backdrop existence
    assert 'id="kpi-detail-modal"' in html
    assert 'id="kpi-modal-backdrop"' in html
    assert 'id="kpi-table-container"' in html
    assert 'id="kpi-empty-state"' in html
    assert 'id="kpi-search-input"' in html
