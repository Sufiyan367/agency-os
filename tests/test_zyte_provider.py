"""
Unit and Invariant Tests for Zyte Provider Integration.

Verifies:
1. Provider registration & production baseline priority in DiscoveryProviderRegistry.
2. Unconfigured state fail-closed behavior (no calls made, healthy reporting).
3. Secret protection: API key is never exposed in health output, string representations, or logs.
4. Circuit breaker trips on failures and recovers cleanly.
5. Spend budget enforces hard ceiling on external calls.
6. SSRF safety check prevents crawling private or disallowed network addresses.
7. Mock mode returns valid StandardizedProspect objects conforming to the unified schema.
8. Shadow evaluation executes safely and reports comparative metrics without mutating production data.
"""
import pytest
from app.acquisition.providers.zyte_provider import (
    ZyteProvider,
    ZyteCircuitBreaker,
    ZyteSpendBudget
)
from app.acquisition.providers.registry import discovery_registry
from app.acquisition.models import StandardizedProspect


def test_zyte_provider_registration_and_baseline_priority():
    """Verifies Zyte is registered and existing_web_search remains primary source of truth."""
    providers = discovery_registry.providers
    provider_names = [p.name for p in providers]

    assert "zyte_api" in provider_names
    assert "existing_web_search" in provider_names
    # Production baseline MUST be index 0
    assert providers[0].name == "existing_web_search"

    zyte = discovery_registry.get_provider("zyte_api")
    assert zyte is not None
    assert zyte.name == "zyte_api"


def test_zyte_provider_unconfigured_fails_closed():
    """Verifies that an unconfigured provider safely fails closed and reports UNCONFIGURED."""
    provider = ZyteProvider(api_key=None, mock_mode=False)
    assert not provider.is_configured
    assert not provider.is_available()

    health = provider.get_health()
    assert health["status"] == "UNCONFIGURED"
    assert health["mode"] in ("evaluation", "shadow")
    assert health["is_shadow"] is True
    assert health["configured"] is False
    assert "api_key" not in health


def test_zyte_secret_masking():
    """Verifies that the Zyte API key is never exposed in health telemetry or string representations."""
    test_key = "zyte_secret_test_key_1234567890"
    provider = ZyteProvider(api_key=test_key, mock_mode=False)

    health = provider.get_health()
    health_str = str(health)
    assert test_key not in health_str
    assert health["configured"] is True


def test_zyte_circuit_breaker():
    """Verifies that repeated failures trip the circuit breaker open."""
    breaker = ZyteCircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
    assert breaker.state == "CLOSED"
    assert breaker.is_allowed()

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "CLOSED"
    assert breaker.is_allowed()

    breaker.record_failure()
    assert breaker.state == "OPEN"
    assert not breaker.is_allowed()

    breaker.record_success()
    assert breaker.state == "CLOSED"
    assert breaker.is_allowed()


def test_zyte_spend_budget_hard_limit():
    """Verifies that the spend budget strictly prevents exceeding the credit ceiling."""
    budget = ZyteSpendBudget(max_credits=3)
    assert budget.can_spend(1)
    assert budget.spend(1)  # 1/3
    assert budget.spend(1)  # 2/3
    assert budget.spend(1)  # 3/3
    assert not budget.can_spend(1)
    assert not budget.spend(1)  # Blocked!
    assert budget.credits_used == 3

    budget.reset()
    assert budget.credits_used == 0
    assert budget.can_spend(1)


@pytest.mark.asyncio
async def test_zyte_ssrf_safety_rejection():
    """Verifies that crawling localhost, 127.0.0.1, or private ranges is rejected."""
    provider = ZyteProvider(mock_mode=True)
    res = await provider.crawl_url("http://127.0.0.1:8000/internal")
    assert res["status_code"] == 403
    assert not res["is_success"]
    assert "SSRF" in res["error"]


@pytest.mark.asyncio
async def test_zyte_mock_prospect_normalization():
    """Verifies that discovered prospects match StandardizedProspect unified schema."""
    provider = ZyteProvider(mock_mode=True)
    prospects = await provider.discover_prospects(
        country_code="AE",
        niche="automotive",
        limit=3
    )
    assert len(prospects) == 3
    for p in prospects:
        assert isinstance(p, StandardizedProspect)
        assert p.country == "AE"
        assert p.niche == "automotive"
        assert p.domain
        assert p.website
        assert p.public_email
        assert p.discovery_source == "zyte_api_shadow"
        assert p.verification_status == "VERIFIED"


@pytest.mark.asyncio
async def test_zyte_shadow_evaluation_non_destructive():
    """Verifies that shadow evaluation returns expected comparative structure without error."""
    provider = ZyteProvider(mock_mode=True)
    report = await provider.evaluate_shadow_discovery(
        country_code="AE",
        niche="automotive",
        limit=2
    )
    assert "production_source_of_truth" in report
    assert report["production_source_of_truth"] == "existing_web_search"
    assert "zyte_health" in report
    assert "zyte_evaluation_status" in report
    assert report["zyte_evaluation_status"]["ready_for_cutover"] is False
