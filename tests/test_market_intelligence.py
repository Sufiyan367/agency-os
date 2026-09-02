import pytest
from app.market_intelligence.engine import market_intelligence_engine
from app.database.models import Country, Niche

@pytest.mark.asyncio
async def test_market_intelligence_ranking_and_comparison(db_session):
    ranks = await market_intelligence_engine.scan_and_rank_markets(db_session)
    assert len(ranks) > 0, "Expected market opportunity evaluations"
    top = ranks[0]
    assert top.total_score >= 0.0 and top.total_score <= 100.0
    assert len(top.reasoning) > 10
    assert top.confidence > 0.5
    
    # Test comparative synthesis
    runner_up = ranks[1]
    comp = market_intelligence_engine.compare_markets(top, runner_up)
    assert comp.winner == top
    assert comp.score_difference >= 0.0
    assert "more attractive than" in comp.comparative_analysis
