import os
import time
import asyncio
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from app.acquisition.providers.base import BaseDiscoveryProvider
from app.acquisition.models import StandardizedProspect
from app.core.config import settings
from app.core.security import normalize_domain
from app.core.logging import logger

class ScrapeGraphCircuitBreaker:
    """
    Prevents cascading failures and credit waste when ScrapeGraph encounters issues.
    Trips open after consecutive failures, stays open during cooldown, then half-opens.
    """
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 60.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_failures = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.last_failure_time: float = 0.0

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        if self.consecutive_failures >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"[ScrapeGraphCircuitBreaker] Circuit TRIPPED OPEN ({self.consecutive_failures} failures). Cooling down for {self.cooldown_seconds}s.")

    def is_allowed(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if (time.time() - self.last_failure_time) >= self.cooldown_seconds:
                self.state = "HALF_OPEN"
                logger.info("[ScrapeGraphCircuitBreaker] Circuit transitioned to HALF_OPEN (probing).")
                return True
            return False
        if self.state == "HALF_OPEN":
            return True
        return False

class ScrapeGraphCreditBudget:
    """
    Enforces a strict budget to avoid uncontrolled spending on external ScrapeGraph credits.
    """
    def __init__(self, max_credits: int = 100):
        self.max_credits = max_credits
        self.credits_used = 0

    def can_spend(self, amount: int = 1) -> bool:
        return (self.credits_used + amount) <= self.max_credits

    def spend(self, amount: int = 1) -> bool:
        if self.can_spend(amount):
            self.credits_used += amount
            return True
        logger.warning(f"[ScrapeGraphCreditBudget] Credit limit reached: {self.credits_used}/{self.max_credits}. Blocking call.")
        return False

    def reset(self) -> None:
        self.credits_used = 0

class ScrapeGraphProvider(BaseDiscoveryProvider):
    """
    Pluggable ScrapeGraphAI discovery and enrichment provider.
    Fails gracefully if unconfigured or encountering errors.
    Mockable for test suites to ensure 0 credit burn.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        credit_limit: int = 100,
        mock_mode: bool = False
    ):
        self.api_key = api_key or os.getenv("SCRAPEGRAPH_API_KEY") or getattr(settings, "SCRAPEGRAPH_API_KEY", None)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.circuit_breaker = ScrapeGraphCircuitBreaker()
        self.budget = ScrapeGraphCreditBudget(max_credits=credit_limit)
        self.mock_mode = mock_mode
        self._total_calls = 0
        self._successful_calls = 0
        self._fallback_count = 0

    @property
    def name(self) -> str:
        return "scrapegraph_ai"

    def is_available(self) -> bool:
        """Available if mock_mode is on or if API key is provided and circuit breaker is closed/half-open."""
        if self.mock_mode:
            return True
        if not self.api_key or not self.api_key.strip():
            return False
        return self.circuit_breaker.is_allowed() and self.budget.can_spend(1)

    def get_health(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "configured": bool(self.api_key) or self.mock_mode,
            "mock_mode": self.mock_mode,
            "circuit_state": self.circuit_breaker.state,
            "consecutive_failures": self.circuit_breaker.consecutive_failures,
            "credits_used": self.budget.credits_used,
            "credits_limit": self.budget.max_credits,
            "total_calls": self._total_calls,
            "successful_calls": self._successful_calls,
            "fallback_count": self._fallback_count
        }

    async def discover_prospects(
        self,
        country_code: str,
        niche: str,
        limit: int = 10,
        cities: Optional[List[str]] = None,
        exclude_domains: Optional[Set[str]] = None
    ) -> List[StandardizedProspect]:
        self._total_calls += 1
        excluded = exclude_domains or set()

        if not self.is_available():
            self._fallback_count += 1
            logger.debug(f"[ScrapeGraphProvider] Provider unavailable (configured={bool(self.api_key)}, circuit={self.circuit_breaker.state}). Bypassing.")
            return []

        # Mock Mode for Tests (consumes zero external credits)
        if self.mock_mode:
            self._successful_calls += 1
            return self._generate_mock_results(country_code, niche, limit, cities, excluded)

        # Budget check
        if not self.budget.spend(1):
            self._fallback_count += 1
            return []

        for attempt in range(1, self.max_retries + 1):
            try:
                # Simulated network call with timeout
                async with asyncio.timeout(self.timeout_seconds):
                    results = await self._execute_scrapegraph_query(country_code, niche, limit, cities, excluded)
                    self.circuit_breaker.record_success()
                    self._successful_calls += 1
                    return results
            except TimeoutError:
                logger.warning(f"[ScrapeGraphProvider] Timeout on attempt {attempt}/{self.max_retries} for {country_code}")
                if attempt == self.max_retries:
                    self.circuit_breaker.record_failure()
                    self._fallback_count += 1
            except Exception as e:
                logger.warning(f"[ScrapeGraphProvider] Error on attempt {attempt}/{self.max_retries}: {e}")
                if attempt == self.max_retries:
                    self.circuit_breaker.record_failure()
                    self._fallback_count += 1

        return []

    async def _execute_scrapegraph_query(
        self,
        country_code: str,
        niche: str,
        limit: int,
        cities: Optional[List[str]],
        excluded: Set[str]
    ) -> List[StandardizedProspect]:
        """
        Executes ScrapeGraph SmartScraper / SearchScraper API call.
        Placeholder for external client integration using requests/httpx.
        """
        # If no real library installed or key invalid, fallback gracefully
        return []

    def _generate_mock_results(
        self,
        country_code: str,
        niche: str,
        limit: int,
        cities: Optional[List[str]],
        excluded: Set[str]
    ) -> List[StandardizedProspect]:
        """Generates deterministic mock prospects for test isolation without burning real credits."""
        results = []
        city_list = cities or ["Central"]
        for i in range(1, limit + 1):
            dom = f"sg-{country_code.lower()}-{niche.lower()}-{i}.com"
            if dom in excluded:
                continue
            city = city_list[(i - 1) % len(city_list)]
            results.append(StandardizedProspect(
                business_name=f"{city} {niche.replace('-', ' ').title()} Co {i}",
                website=f"https://www.{dom}",
                domain=dom,
                country=country_code.upper(),
                city=city,
                niche=niche,
                public_email=f"contact@{dom}",
                public_phone=f"+1-555-01{i:02d}",
                discovery_source="scrapegraph_ai",
                verification_status="VERIFIED",
                confidence=0.92,
                evidence={
                    "source": "scrapegraph_smart_scraper",
                    "extracted_at": datetime.utcnow().isoformat(),
                    "confidence": 0.92
                },
                contactability=85.0,
                audit_status="PENDING",
                raw_signals={"scrapegraph_credits_used": 1}
            ))
            excluded.add(dom)
        return results
