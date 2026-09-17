import pytest
import asyncio
import re
import socket
import ssl
import httpx
import httpcore
from unittest.mock import patch, MagicMock, AsyncMock

from app.core.security import is_safe_ip, resolve_and_validate_hostname, is_safe_url
from app.auditing.crawler import ResilientWebsiteCrawler, SafeNetworkBackend, CrawlResult
from app.core.llm import llm_client
from app.outreach.composer import (
    GeneralizedOutreachComposer, PreSendValidator, CanonicalProspect,
    ResearchFact, SenderIdentity, SolutionCatalog, ComplianceProfile, ComposedEmail
)


# =====================================================================
# PHASE 1: CRAWLER SSRF & TRANSPORT HARDENING TESTS (Tests 1 - 7)
# =====================================================================

def test_1_ssrf_blocks_loopback():
    """1. Public URL or input pointing to 127.0.0.1 or localhost is blocked."""
    safe, msg = is_safe_ip("127.0.0.1")
    assert not safe
    assert "Loopback" in msg or "Restricted" in msg

    safe_url, reason = is_safe_url("http://127.0.0.1:8080/internal")
    assert not safe_url
    assert "Loopback" in reason or "restricted" in reason.lower()

    safe_url_local, reason_local = is_safe_url("http://localhost:3000/metrics")
    assert not safe_url_local


def test_2_ssrf_blocks_cloud_metadata():
    """2. Public URL or input targeting cloud metadata (169.254.169.254) is blocked."""
    safe, msg = is_safe_ip("169.254.169.254")
    assert not safe

    safe_url, reason = is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not safe_url
    assert "metadata" in reason.lower() or "private" in reason.lower() or "restricted" in reason.lower()


def test_3_ssrf_blocks_private_ipv6():
    """3. IPv6 loopback, link-local, unique local, and IPv4-mapped IPv6 are blocked."""
    # IPv6 loopback
    safe, _ = is_safe_ip("::1")
    assert not safe

    # IPv6 Link-local
    safe, _ = is_safe_ip("fe80::1ff:fe23:4567:890a")
    assert not safe

    # IPv6 Unique Local (private)
    safe, _ = is_safe_ip("fc00::1")
    assert not safe
    safe, _ = is_safe_ip("fd12:3456:789a:1::1")
    assert not safe

    # IPv4-mapped IPv6 pointing to 127.0.0.1
    safe, _ = is_safe_ip("::ffff:127.0.0.1")
    assert not safe

    # IPv4-mapped IPv6 pointing to 10.0.0.1
    safe, _ = is_safe_ip("::ffff:10.0.0.1")
    assert not safe

    safe_url, _ = is_safe_url("http://[::1]/secret")
    assert not safe_url


@pytest.mark.asyncio
async def test_4_redirect_chain_exceeding_maximum_is_aborted():
    """4. Crawler aborts if redirect chain exceeds maximum allowed hops (5)."""
    crawler = ResilientWebsiteCrawler()
    
    # Mock httpx client in crawler to return continuous 302 redirects
    mock_resp = MagicMock()
    mock_resp.is_redirect = True
    mock_resp.headers = {"Location": "http://example.com/redirect"}
    mock_resp.status_code = 302

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with patch("app.core.security.is_safe_url", return_value=(True, "Safe")):
            res = await crawler.fetch("http://example.com/start")
            assert res.status_code == 310
            assert not res.is_successful
            assert "Exceeded maximum redirect limit" in res.error_msg


@pytest.mark.asyncio
async def test_5_dns_rebinding_defense():
    """5. SafeNetworkBackend prevents connection when hostname resolves to restricted IP."""
    backend = SafeNetworkBackend()
    
    # Simulate a domain that resolves to 127.0.0.1 (rebound DNS)
    with patch("app.core.security.resolve_and_validate_hostname", return_value=(False, [], "Restricted IP 127.0.0.1")):
        with pytest.raises(httpcore.ConnectError) as exc_info:
            await backend.connect_tcp("rebound-attacker.com", 80)
        assert "SSRF guard rejected connection" in str(exc_info.value)


@pytest.mark.asyncio
async def test_6_invalid_tls_certificate_behavior():
    """6. Invalid/untrusted TLS cert is recorded as an audit fact (status 526) rather than crashing or ignoring."""
    crawler = ResilientWebsiteCrawler()
    
    # Simulate an SSL certificate verification failure
    ssl_error = ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")
    with patch("httpx.AsyncClient.get", side_effect=ssl_error):
        with patch("app.core.security.is_safe_url", return_value=(True, "Safe")):
            res = await crawler.fetch("https://self-signed.badssl.com")
            assert res.status_code == 526
            assert not res.is_successful
            assert res.error_msg == "SSL/TLS Certificate Verification Failed"


@pytest.mark.asyncio
async def test_7_normal_public_redirect_functional():
    """7. Normal public HTTP -> HTTPS redirect remains functional."""
    crawler = ResilientWebsiteCrawler()

    resp_301 = MagicMock()
    resp_301.is_redirect = True
    resp_301.headers = {"Location": "https://example.com/"}
    resp_301.status_code = 301

    resp_200 = MagicMock()
    resp_200.is_redirect = False
    resp_200.status_code = 200
    resp_200.headers = {"content-type": "text/html"}
    resp_200.text = "<html><head><title>Example Domain</title></head><body><h1>Example</h1></body></html>"
    resp_200.url = "https://example.com/"

    with patch("httpx.AsyncClient.get", side_effect=[resp_301, resp_200]):
        with patch("app.core.security.is_safe_url", return_value=(True, "Safe")):
            res = await crawler.fetch("http://example.com")
            assert res.status_code == 200
            assert res.is_successful
            assert res.url == "https://example.com/"
            assert "Example Domain" in res.soup.title.text


# =====================================================================
# PHASE 2: EVIDENCE-GROUNDED OUTREACH FALLBACK TESTS (Tests 8 - 11)
# =====================================================================

def test_8_fallback_cannot_create_unsupported_commercial_claim_or_roi():
    """8. LLM text fallback must NEVER invent ROI percentages, conversion claims, or testimonials."""
    fallback_text = llm_client._heuristic_text_fallback(
        prompt="Compose cold email outreach for acmedental.com",
        system_prompt=""
    )

    # Invariants:
    assert "15-25%" not in fallback_text
    assert "%" not in fallback_text
    assert "percent" not in fallback_text.lower()
    assert "helped similar firms" not in fallback_text.lower()
    assert "in under 5 business days" not in fallback_text.lower()
    assert "zero downtime" not in fallback_text.lower()
    assert "guarantee" not in fallback_text.lower()


def test_9_unsupported_claim_without_evidence_is_rejected_by_validator():
    """9. Fabricated commercial claims or ROI percentages fail PreSendValidator."""
    prospect = CanonicalProspect(
        prospect_id=1,
        company_name="Apex Legal",
        website="apexlegal.com",
        canonical_company_domain="apexlegal.com",
        recipient_email="partner@apexlegal.com"
    )
    sender = SenderIdentity(
        sender_name="Sufiyan Surve",
        sender_email="sufiyan@automatedagencyos.tech",
        sender_company="Agency OS"
    )

    # Fabricated email with invented ROI
    dirty_email = ComposedEmail(
        subject="Apex Legal inquiry",
        body="Hi Apex Legal team,\n\nWe noticed mobile speed issues on apexlegal.com. Fixing this delivers 15-25% more revenue.\nWe recently helped similar firms with guaranteed results.\n\nBest,\nSufiyan",
        word_count=55,
        variant_name="Test Variant",
        prospect_id=1,
        solution_matched="conversion_optimization"
    )

    result = PreSendValidator.validate_email(dirty_email, prospect, sender)
    assert not result.is_valid
    assert any("ROI" in err or "commercial claim" in err for err in result.errors)


@pytest.mark.asyncio
async def test_10_malformed_llm_json_is_rejected_safely():
    """10. Malformed LLM JSON does not become authoritative; fallback metadata marks validation_result=INVALID."""
    with patch.object(llm_client, "_generate_text_with_meta", new_callable=AsyncMock) as mock_gen:
        # LLM returns malformed JSON
        mock_gen.return_value = ("{malformed: 'json', no_close_brace", "openrouter", "llama-3.1")
        
        result = await llm_client.generate_json("Classify reply text: 'I am interested in a demo'")
        assert result["fallback"] is True
        assert result["validation_result"] in ("INVALID", "MALFORMED_JSON")
        assert result["provider"] == "fallback"
        assert result["confidence"] <= 0.90


@pytest.mark.asyncio
async def test_11_evidence_backed_claim_passes_with_metadata():
    """11. Evidence-backed outreach passes validation and JSON responses include explicit provenance metadata."""
    prospect = CanonicalProspect(
        prospect_id=1,
        company_name="Beacon Dental",
        website="beacondental.com",
        canonical_company_domain="beacondental.com",
        recipient_email="drbeacon@beacondental.com"
    )
    sender = SenderIdentity(
        sender_name="Sufiyan Surve",
        sender_email="sufiyan@automatedagencyos.tech",
        sender_company="Agency OS"
    )
    facts = [
        ResearchFact(
            prospect_id=1,
            fact="Missing mobile viewport configuration",
            source="audit_finding:101",
            category="conversion",
            metric_value=45.0
        )
    ]
    solution = SolutionCatalog.match_solution(prospect, facts, {})
    composer = GeneralizedOutreachComposer()
    variants = composer.compose_variants(prospect, facts, solution, sender)

    assert len(variants) >= 1
    # Verify pre-send validation passes on cleanly composed email
    val = PreSendValidator.validate_email(variants[0], prospect, sender)
    assert val.is_valid, f"Validation failed with: {val.errors}"

    # Verify JSON generation metadata contract
    json_result = await llm_client.generate_json("Classify reply text: 'Yes, please send more info'")
    assert "provider" in json_result
    assert "model" in json_result
    assert "fallback" in json_result
    assert "validation_result" in json_result
    assert "confidence" in json_result
