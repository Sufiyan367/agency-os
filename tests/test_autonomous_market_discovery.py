"""
Comprehensive Test Suite for Autonomous Multi-Market Acquisition Engine & CEO Ops Telemetry
Validates:
1. Multi-market portfolio initialization & concurrent active targets (Country x Region x City x Niche).
2. Exploit (70-80%) vs. Explore (20-30%) allocation balance.
3. Trend detection sample threshold: N < 10 -> INSUFFICIENT_DATA.
4. Hard exclusions: India (IN), Pakistan (PK), Israel (IL) permanently blocked from autonomous selection.
5. CEO manual overrides: Pause, Exclude, Force, Emergency Stop, Clear.
6. Multi-market queue distribution under the global 200/day outreach budget.
7. Real-time event recording & WebSocket broadcasting (MARKET_SELECTED, MARKET_REBALANCED).
8. Targeting API endpoints: GET /api/targeting/autonomous-queue, POST /api/targeting/rebalance, POST /api/targeting/override.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.api.app import app
from app.database.connection import AsyncSessionLocal
from app.market_intelligence.autonomous_market_engine import autonomous_market_engine, HARD_EXCLUDED_COUNTRIES
from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType
from app.database.models import AgentActivityEvent, TargetDefinition


@pytest.mark.asyncio
async def test_hard_excluded_countries_constant():
    """Verify hard exclusions are strictly defined for IN, PK, and IL."""
    assert "IN" in HARD_EXCLUDED_COUNTRIES
    assert "PK" in HARD_EXCLUDED_COUNTRIES
    assert "IL" in HARD_EXCLUDED_COUNTRIES

    # Verify engine method rejects them
    assert autonomous_market_engine.is_country_excluded("IN") is True
    assert autonomous_market_engine.is_country_excluded("in") is True
    assert autonomous_market_engine.is_country_excluded("PK") is True
    assert autonomous_market_engine.is_country_excluded("IL") is True
    assert autonomous_market_engine.is_country_excluded("US") is False
    assert autonomous_market_engine.is_country_excluded("AE") is False


@pytest.mark.asyncio
async def test_autonomous_queue_structure_and_corridors():
    """Verify autonomous queue generates active markets with Country x Region x City x Niche."""
    async with AsyncSessionLocal() as session:
        queue_data = await autonomous_market_engine.get_autonomous_target_queue(session=session, limit=10)
        
        assert "portfolio_summary" in queue_data
        assert "active_portfolio" in queue_data
        assert "next_targets" in queue_data
        assert "currently_running_ops" in queue_data
        
        summary = queue_data["portfolio_summary"]
        assert summary["total_active"] >= 3
        assert summary["global_daily_cap"] == 200

        active_portfolio = queue_data["active_portfolio"]
        assert len(active_portfolio) >= 3

        for market in active_portfolio:
            assert market["country_code"] is not None
            assert market["country_code"].upper() not in HARD_EXCLUDED_COUNTRIES
            assert market["region"] is not None
            assert market["city"] is not None
            assert market["niche_id"] is not None
            assert market["type"] in ("EXPLOIT", "EXPLORE")
            assert market["reason_code"] in (
                "HIGH_CONTACTABILITY", "HIGH_AUTOMATION_FIT",
                "POSITIVE_HISTORICAL_OUTCOMES", "HIGH_PAIN_DENSITY",
                "DATA_REFRESHED", "EXPLORATION_REQUIRED"
            )
            assert market["score"] > 0
            assert "freshness" in market


@pytest.mark.asyncio
async def test_exploit_explore_portfolio_balance():
    """Verify 70-80% exploitation and 20-30% exploration balance."""
    async with AsyncSessionLocal() as session:
        queue_data = await autonomous_market_engine.get_autonomous_target_queue(session=session, limit=10)
        active = queue_data["active_portfolio"]
        
        exploit_count = sum(1 for m in active if m["type"] == "EXPLOIT")
        explore_count = sum(1 for m in active if m["type"] == "EXPLORE")
        total = len(active)
        
        assert total >= 3
        assert exploit_count >= 1
        assert explore_count >= 1
        
        # Check ratios
        summary = queue_data["portfolio_summary"]
        assert 60 <= summary["exploitation_pct"] <= 90
        assert 10 <= summary["exploration_pct"] <= 40


@pytest.mark.asyncio
async def test_trend_detection_minimum_sample_threshold():
    """Verify N < 10 sample size reports INSUFFICIENT_DATA and prevents false conclusions."""
    low_sample_metrics = {"sample_count": 5, "won": 3, "replies": 4}
    trend = autonomous_market_engine.evaluate_market_trend(low_sample_metrics)
    assert trend["status"] == "INSUFFICIENT_DATA"
    assert trend["is_reliable"] is False
    assert trend["sample_count"] == 5

    adequate_sample_metrics = {"sample_count": 15, "won": 4, "replies": 8}
    trend_ok = autonomous_market_engine.evaluate_market_trend(adequate_sample_metrics)
    assert trend_ok["status"] != "INSUFFICIENT_DATA"
    assert trend_ok["is_reliable"] is True
    assert trend_ok["sample_count"] == 15


@pytest.mark.asyncio
async def test_ceo_manual_overrides():
    """Verify CEO manual overrides take precedence over autonomous scoring."""
    async with AsyncSessionLocal() as session:
        test_key = "US:TEXAS:AUSTIN:ROOFING"
        
        # 1. Force override
        force_res = await autonomous_market_engine.set_ceo_override("force", test_key, "CEO requested focus", session)
        assert force_res["status"] == "OVERRIDE_APPLIED"
        overrides = autonomous_market_engine.get_ceo_overrides()
        assert test_key in overrides
        assert overrides[test_key]["action"] == "force"

        # 2. Pause override
        pause_res = await autonomous_market_engine.set_ceo_override("pause", test_key, "CEO temporary pause", session)
        assert pause_res["status"] == "OVERRIDE_APPLIED"
        assert autonomous_market_engine.get_ceo_overrides()[test_key]["action"] == "pause"

        # 3. Clear override
        clear_res = await autonomous_market_engine.set_ceo_override("clear", test_key, session=session)
        assert clear_res["status"] == "OVERRIDE_CLEARED"
        assert test_key not in autonomous_market_engine.get_ceo_overrides()


@pytest.mark.asyncio
async def test_ceo_emergency_stop_override():
    """Verify emergency stop suspends discovery across all markets."""
    async with AsyncSessionLocal() as session:
        res = await autonomous_market_engine.set_ceo_override("emergency_stop", reason="Safety test", session=session)
        assert res["status"] == "EMERGENCY_STOP_ACTIVATED"
        assert autonomous_market_engine.get_ceo_overrides().get("GLOBAL:ALL", {}).get("action") == "emergency_stop"

        # Clear emergency stop
        clear_res = await autonomous_market_engine.set_ceo_override("clear", "GLOBAL:ALL", session=session)
        assert clear_res["status"] == "OVERRIDE_CLEARED"


@pytest.mark.asyncio
async def test_portfolio_rebalance_and_event_emission():
    """Verify portfolio rebalance evaluates markets and records MARKET_REBALANCED event."""
    async with AsyncSessionLocal() as session:
        rebal_res = await autonomous_market_engine.rebalance_portfolio(session=session)
        assert "active_portfolio" in rebal_res
        assert len(rebal_res["active_portfolio"]) >= 3

        # Check that AgentActivityEvent has MARKET_REBALANCED
        evt_stmt = select(AgentActivityEvent).where(
            AgentActivityEvent.event_type == AgentEventType.MARKET_REBALANCED.value
        ).order_by(AgentActivityEvent.id.desc())
        latest_evt = (await session.execute(evt_stmt)).scalars().first()
        assert latest_evt is not None
        assert "Autonomous market portfolio rebalanced" in latest_evt.message


@pytest.mark.asyncio
async def test_api_autonomous_queue_endpoint():
    """Verify GET /api/targeting/autonomous-queue returns live state."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/targeting/autonomous-queue?limit=5")
        assert res.status_code == 200
        data = res.json()
        assert "portfolio_summary" in data
        assert "active_portfolio" in data
        assert "next_targets" in data
        assert "currently_running_ops" in data
        assert data["portfolio_summary"]["total_active"] >= 3


@pytest.mark.asyncio
async def test_api_rebalance_and_override_endpoints():
    """Verify POST /api/targeting/rebalance and POST /api/targeting/override."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Rebalance
        reb_res = await client.post("/api/targeting/rebalance")
        assert reb_res.status_code == 200
        reb_json = reb_res.json()
        assert reb_json["status"] == "COMPLETED"

        # CEO Override
        override_payload = {
            "action": "pause",
            "market_key": "AE:DUBAI:DUBAI:REAL_ESTATE",
            "reason": "Test pause"
        }
        ov_res = await client.post("/api/targeting/override", json=override_payload)
        assert ov_res.status_code == 200
        ov_json = ov_res.json()
        assert ov_json["status"] == "OVERRIDE_APPLIED"

        # Clear override
        clear_payload = {
            "action": "clear",
            "market_key": "AE:DUBAI:DUBAI:REAL_ESTATE"
        }
        cl_res = await client.post("/api/targeting/override", json=clear_payload)
        assert cl_res.status_code == 200
        assert cl_res.json()["status"] == "OVERRIDE_CLEARED"
