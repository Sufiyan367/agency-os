import pytest
from app.core.security import is_safe_url, normalize_domain, validate_email_syntax

def test_ssrf_disallows_loopback_and_internal_ips():
    bad_urls = [
        "http://localhost:8080/admin",
        "http://127.0.0.1/secrets",
        "http://0.0.0.0:3000",
        "http://169.254.169.254/latest/meta-data/",
        "ftp://example.com/file",
        "file:///etc/passwd",
        ""
    ]
    for url in bad_urls:
        safe, msg = is_safe_url(url)
        assert safe is False, f"Expected {url} to be unsafe, but got safe."

def test_ssrf_allows_public_domains():
    safe_urls = [
        "https://example.com",
        "https://google.com/search",
        "http://bbc.co.uk"
    ]
    for url in safe_urls:
        safe, msg = is_safe_url(url)
        assert safe is True, f"Expected {url} to be safe, but got: {msg}"

def test_domain_normalization():
    assert normalize_domain("https://www.ApexRidgeRoofing.com/contact/") == "apexridgeroofing.com"
    assert normalize_domain("http://sub.domain.co.uk:8080/path") == "sub.domain.co.uk"
    assert normalize_domain("www.example.org") == "example.org"

def test_email_validation():
    assert validate_email_syntax("contact@company.com") is True
    assert validate_email_syntax("user.name+tag@sub.domain.co.uk") is True
    assert validate_email_syntax("invalid-email") is False
    assert validate_email_syntax("@missing-user.com") is False
    assert validate_email_syntax("") is False
