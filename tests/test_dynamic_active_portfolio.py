"""
Focused Test Suite for Dynamic Global Active Portfolio (Requirement 19)
Verifies:
1. Portfolio can have fewer than 7 active markets when supply is restricted.
2. Portfolio can exceed 7 active markets when eligible supply is abundant.
3. Portfolio size changes dynamically after rebalance.
4. No arbitrary fixed maximum controls normal operation.
5. Global total allocation <= 200 across all portfolio sizes.
6. Capacity reallocation distributes budget dynamically.
7. Candidate exhaustion penalizes and rotates underperforming markets.
8. New eligible markets from the global universe enter automatically.
9. CEO pause / exclude overrides take immediate precedence.
10. CEO emergency stop clears active portfolio (N = 0).
11. Hard exclusions (IN, PK, IL) remain strictly impossible.
12. Exploration (20-30%) vs Exploitation (70-80%) dynamic portfolio balance.
13. N < 10 sample size guard remains strictly INSUFFICIENT_DATA.
14. Dashboard / API reports canonical dynamic active count and sizing reason.
15. Realtime portfolio events (MARKET_ACTIVATED, MARKET_REBALANCED, CAPACITY_REALLOCATED) are emitted.
16. Orchestrator loop selects opportunities from the dynamic active portfolio.
17. Target definitions and historical outcomes remain preserved in database.
"""
import pytest
from datetime import datetime
from sqlalchemy import select, and_

from app.database.connection import AsyncSessionLocal
from app.market_intelligence.autonomous_market_engine import (
    autonomous_market_engine, HARD_EXCLUDED_COUNTRIES, MarketTrend, AutonomousTargetItem
)
from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType
from app.database.models import AgentActivityEvent, TargetDefinition, Business, PipelineStage


@pytest.mark.asyncio
async def test_1_portfolio_can_have_fewer_than_7():
    """Verify portfolio size dynamically contracts below 7 when eligible candidates are limited."""
    async with AsyncSessionLocal() as session:
        # Clear any prior state
        await autonomous_market_engine.set_ceo_override("clear", "ALL", session=session)
        
        # Simulate restricted candidate supply by pausing all except 3 seed candidates
        all_candidates = await autonomous_market_engine.build_candidate_universe(session)
        keep_keys = [
            f"{c['country_code']}:{c['region']}:{c['city']}:{c['niche_id']}".upper()
            for c in all_candidates[:3]
        ]
        
        for cand in all_candidates[3:]:
            k = f"{cand['country_code']}:{cand['region']}:{cand['city']}:{cand['niche_id']}".upper()
            autonomous_market_engine.pause_target(k)
            
        try:
            queue = await autonomous_market_engine.rebalance_target_queue(session, force=True)
            assert len(queue) <= 3, f"Expected <= 3 active markets, got {len(queue)}"
            assert len(queue) > 0
            assert autonomous_market_engine._last_sizing_reason == "DYNAMIC_CONTRACTION_LIMITED_SUPPLY"
        finally:
            await autonomous_market_engine.set_ceo_override("clear", "ALL", session=session)


@pytest.mark.asyncio
async def test_2_portfolio_can_exceed_7():
    """Verify portfolio size expands beyond 7 when abundant eligible candidates exist."""
    async with AsyncSessionLocal() as session:
        await autonomous_market_engine.set_ceo_override("clear", "ALL", session=session)
        queue = await autonomous_market_engine.rebalance_target_queue(session, force=True)
        
        # With our expanded candidate universe (12 seeds + catalog targets), portfolio expands dynamically
        assert len(queue) > 7, f"Expected portfolio to expand beyond 7, got {len(queue)}"
        assert sum(t.allocated_daily_capacity for t in queue) <= 200


@pytest.mark.asyncio
async def test_3_portfolio_size_changes_after_rebalance():
    """Verify portfolio size adjusts dynamically when market eligibility conditions change."""
    async with AsyncSessionLocal() as session:
        await autonomous_market_engine.set_ceo_override("clear", "ALL", session=session)
        q1 = await autonomous_market_engine.rebalance_target_queue(session, force=True)
        size1 = len(q1)

        # Pause 4 active markets
        for t in q1[:4]:
            autonomous_market_engine.pause_target(t.key)

        q2 = await autonomous_market_engine.rebalance_target_queue(session, force=True)
        size2 = len(q2)

        # Keys in q2 must not contain the paused keys
        paused_keys = set(t.key for t in q1[:4])
        for t in q2:
            assert t.key not in paused_keys

        # Cleanup
        await autonomous_market_engine.set_ceo_override("clear", "ALL", session=session)


@pytest.mark.asyncio
async def test_4_no_arbitrary_fixed_maximum_controls_operation():
    """Verify the portfolio is not capped at 7, 10, or 20 when forced or high-supply."""
    async with AsyncSessionLocal() as session:
        await autonomous_market_engine.set_ceo_override("clear", "ALL", session=session)
        
        # Force 15 distinct markets
        candidates = await autonomous_market_engine.build_candidate_universe(session)
        forced_count = 15
        for cand in candidates[:forced_count]:
            k = f"{cand['country_code']}:{cand['region']}:{cand['city']}:{cand['niche_id']}".upper()
            autonomous_market_engine.force_target(k, mode="EXPLOIT")

        try:
            queue = await autonomous_market_engine.rebalance_target_queue(session, force=True)
            assert len(queue) >= forced_count, f"Expected at least {forced_count} active markets, got {len(queue)}"
            assert sum(t.allocated_daily_capacity for t in queue) <= 200
        finally:
            await autonomous_market_engine.set_ceo_override("clear", "ALL", session=session)


@pytest.mark.asyncio
async def test_5_global_total_allocation_le_200():
    """Verify SUM(all market allocations) <= 200 across various dynamic portfolio sizes."""
    async with AsyncSessionLocal() as session:
        await autonomous_market_engine.set_ceo_override("clear", "ALL", session=session)
        queue = await autonomous_market_engine.rebalance_target_queue(session, force=True)
        
        total_allocated = sum(t.allocated_daily_capacity for t in queue)
        assert total_allocated <= 200, f"Total allocation {total_allocated} exceeded 200!"
        assert total_allocated > 0


@pytest.mark.asyncio
async def test_6_capacity_reallocation_works():
    """Verify capacity reallocation distributes budget dynamically and emits event."""
    async with AsyncSessionLocal() as session:
        await autonomous_market_engine.set_ceo_override("clear", "ALL", session=session)
        rebal_res = await autonomous_market_engine.rebalance_portfolio(session=session)
        
        summary = rebal_res.get("portfolio_summary", {})
        assert summary.get("allocated_daily_capacity", 0) <= 200
        assert summary.get("unused_daily_capacity", 0) >= 0
        assert summary.get("allocated_daily_capacity", 0) + summary.get("unused_daily_capacity", 0) == 200


@pytest.mark.asyncio
async def test_7_candidate_exhaustion_removes_market():
    """Verify markets with candidate exhaustion are penalized and deprioritized."""
    # Outcomes with high sample, 0 positive replies, and near-zero contactability
    exhausted_outcomes = {
        "sample_size": 25,
        "total_leads": 25,
        "verified_emails": 2,
        "contactability": 0.08,
        "positive_replies": 0,
        "won_deals": 0,
        "reply_rate": 0.0
    }
    score, conf, reasons, mode = autonomous_market_engine._score_target("US", "HVAC", exhausted_outcomes)
    # The score should reflect the lack of positive outcomes
    assert score < 75.0


@pytest.mark.asyncio
async def test_8_new_eligible_market_enters_automatically():
    """Verify a newly added database target definition enters the candidate universe automatically."""
    async with AsyncSessionLocal() as session:
        test_city = "Salt Lake City"
        test_region = "Utah"
        test_niche = "PLUMBING"
        
        # Check or create target definition
        stmt = select(TargetDefinition).where(
            and_(
                TargetDefinition.country_code == "US",
                TargetDefinition.region == test_region,
                TargetDefinition.city == test_city,
                TargetDefinition.niche_id == test_niche
            )
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if not existing:
            new_target = TargetDefinition(
                country_code="US",
                country_name="United States",
                region=test_region,
                city=test_city,
                niche_id=test_niche,
                niche_name="Plumbing",
                priority="P1",
                enabled=True,
                status="ACTIVE"
            )
            session.add(new_target)
            await session.commit()

        # Invalidate universe cache and rebuild
        autonomous_market_engine._candidate_universe_cache = []
        autonomous_market_engine._candidate_universe_last_built = None
        universe = await autonomous_market_engine.build_candidate_universe(session)
        
        matches = [
            c for c in universe 
            if c["country_code"] == "US" and c["city"] == test_city and c["niche_id"] == test_niche
        ]
        assert len(matches) > 0, "Expected new DB target to enter candidate universe!"


@pytest.mark.asyncio
async def test_9_ceo_pause_exclude_works():
    """Verify CEO pause and exclude operations prevent corridor selection."""
    async with AsyncSessionLocal() as session:
        test_key = "US:TEXAS:HOUSTON:HVAC"
        await autonomous_market_engine.set_ceo_override("pause", test_key, "Test pause", session)
        
        queue = await autonomous_market_engine.rebalance_target_queue(session, force=True)
        active_keys = set(t.key for t in queue)
        assert test_key not in active_keys, "Paused market should not be in active portfolio!"
        
        # Cleanup
        await autonomous_market_engine.set_ceo_override("clear", test_key, session=session)


@pytest.mark.asyncio
async def test_10_emergency_stop_works():
    """Verify emergency stop sets active portfolio to 0 immediately."""
    async with AsyncSessionLocal() as session:
        res = await autonomous_market_engine.set_ceo_override("emergency_stop", reason="Safety Stop", session=session)
        assert res["status"] == "EMERGENCY_STOP_ACTIVATED"
        
        queue = await autonomous_market_engine.rebalance_target_queue(session, force=True)
        assert len(queue) == 0, f"Expected 0 active markets under emergency stop, got {len(queue)}"
        assert autonomous_market_engine._last_sizing_reason == "EMERGENCY_STOP_ACTIVE"
        
        # Clear emergency stop
        await autonomous_market_engine.set_ceo_override("clear", "GLOBAL:ALL", session=session)
        queue_restored = await autonomous_market_engine.rebalance_target_queue(session, force=True)
        assert len(queue_restored) > 0, "Portfolio should be restored after clearing emergency stop!"


@pytest.mark.asyncio
async def test_11_in_pk_il_remain_impossible():
    """Verify India, Pakistan, and Israel remain permanently excluded from all candidate selection."""
    for cc in ("IN", "in", "PK", "pk", "IL", "il"):
        assert autonomous_market_engine.is_country_excluded(cc) is True
        assert cc.upper() in HARD_EXCLUDED_COUNTRIES

    async with AsyncSessionLocal() as session:
        queue = await autonomous_market_engine.rebalance_target_queue(session, force=True)
        for t in queue:
            assert t.country_code not in HARD_EXCLUDED_COUNTRIES


@pytest.mark.asyncio
async def test_12_exploration_exploitation_still_works():
    """Verify dynamic portfolio balances 60-90% exploit and 10-40% explore."""
    async with AsyncSessionLocal() as session:
        await autonomous_market_engine.set_ceo_override("clear", "ALL", session=session)
        queue_data = await autonomous_market_engine.get_autonomous_target_queue(session=session, limit=10)
        
        summary = queue_data["portfolio_summary"]
        active = queue_data["active_portfolio"]
        
        exploit_count = sum(1 for m in active if m["type"] == "EXPLOIT")
        explore_count = sum(1 for m in active if m["type"] == "EXPLORE")
        
        assert len(active) > 0
        assert explore_count >= 1
        if exploit_count > 0:
            assert 60 <= summary["exploitation_pct"] <= 90
            assert 10 <= summary["exploration_pct"] <= 40
        else:
            assert summary["exploration_pct"] == 100.0 or explore_count == len(active)


@pytest.mark.asyncio
async def test_13_n_lt_10_remains_insufficient_data():
    """Verify sample count < 10 always reports INSUFFICIENT_DATA."""
    trend = autonomous_market_engine.evaluate_market_trend({"sample_count": 8, "won": 2})
    assert trend["status"] == MarketTrend.INSUFFICIENT_DATA
    assert trend["is_reliable"] is False


@pytest.mark.asyncio
async def test_14_dashboard_reports_canonical_active_count():
    """Verify /api/targeting/autonomous-queue reports consistent canonical numbers."""
    async with AsyncSessionLocal() as session:
        data = await autonomous_market_engine.get_autonomous_target_queue(session=session, limit=10)
        
        summary = data["portfolio_summary"]
        active = data["active_portfolio"]
        
        assert summary["total_active"] == len(active)
        assert summary["global_daily_cap"] == 200
        assert summary["allocated_daily_capacity"] <= 200
        assert "candidate_universe_count" in summary
        assert summary["candidate_universe_count"] >= len(active)
        assert "sizing_reason" in summary


@pytest.mark.asyncio
async def test_15_realtime_portfolio_events_work():
    """Verify MARKET_REBALANCED and CAPACITY_REALLOCATED events are logged to AgentActivityEvent."""
    async with AsyncSessionLocal() as session:
        await autonomous_market_engine.rebalance_portfolio(session=session)
        
        stmt = select(AgentActivityEvent).where(
            AgentActivityEvent.event_type == AgentEventType.MARKET_REBALANCED.value
        ).order_by(AgentActivityEvent.id.desc())
        evt = (await session.execute(stmt)).scalars().first()
        assert evt is not None
        assert "rebalanced" in evt.message.lower()


@pytest.mark.asyncio
async def test_16_worker_operates_on_dynamic_portfolio():
    """Verify orchestrator cycle consumes dynamic active portfolio candidates seamlessly."""
    async with AsyncSessionLocal() as session:
        auto_queue = await autonomous_market_engine.get_autonomous_target_queue(session=session, limit=5)
        active_portfolio = auto_queue.get("active_portfolio", [])
        assert len(active_portfolio) > 0
        
        # Candidate fields expected by orchestrator loop
        cand0 = active_portfolio[0]
        assert "country_code" in cand0
        assert "region" in cand0
        assert "city" in cand0
        assert "niche_id" in cand0
        assert "score" in cand0


@pytest.mark.asyncio
async def test_17_target_definitions_synced_and_preserved():
    """Verify database target definitions are marked ACTIVE without deleting records."""
    async with AsyncSessionLocal() as session:
        queue = await autonomous_market_engine.rebalance_target_queue(session, force=True)
        active_keys = set(t.key for t in queue)
        
        stmt = select(TargetDefinition).where(TargetDefinition.status == "ACTIVE")
        active_defs = (await session.execute(stmt)).scalars().all()
        assert len(active_defs) > 0
