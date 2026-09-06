from typing import Dict, Any
from app.market_intelligence.config import BUDGET_CONFIG
from app.core.logging import logger

class MarketResearchCostGuard:
    """Monitors external search requests and estimated monetary costs to prevent budget overruns."""

    def __init__(
        self,
        max_requests: int = None,
        max_cost_usd: float = None,
        cost_per_request_usd: float = None
    ):
        self.max_requests = max_requests if max_requests is not None else BUDGET_CONFIG["max_requests_per_run"]
        self.max_cost_usd = max_cost_usd if max_cost_usd is not None else BUDGET_CONFIG["max_cost_per_run_usd"]
        self.cost_per_request = cost_per_request_usd if cost_per_request_usd is not None else BUDGET_CONFIG["cost_per_request_usd"]
        self.requests_made = 0
        self.cache: Dict[str, Any] = {}

    @property
    def total_requests(self) -> int:
        return self.requests_made

    def can_request(self) -> bool:
        if self.requests_made >= self.max_requests:
            logger.warning(f"[CostGuard] Request limit exceeded: {self.requests_made}/{self.max_requests}.")
            return False
        if (self.requests_made * self.cost_per_request) >= self.max_cost_usd:
            logger.warning(f"[CostGuard] Cost limit exceeded: ${self.requests_made * self.cost_per_request:.2f}/${self.max_cost_usd}.")
            return False
        return True

    def record_request(self, cost_usd: float = None) -> None:
        self.requests_made += 1

    def get_cost_usd(self) -> float:
        return round(self.requests_made * self.cost_per_request, 4)

    def reset(self) -> None:
        self.requests_made = 0
        self.cache.clear()

market_cost_guard = MarketResearchCostGuard()
