"""Safety Filters & Synthetic Record Guard.

Provides deterministic detection and query-layer exclusion for:
- Synthetic domains (.example, .test, .invalid, .localhost, .local, example.com/org/net)
- Test/internal emails (@agencyos.tech, test@, sufiyan*@gmail.com, postmaster@, etc.)
- Mock/fixture business records
Ensures operator views and CRM dashboards display only genuine commercial prospects.
"""

import re
from typing import Optional, Set
from sqlalchemy import not_, or_, and_

# Reserved TLDs (RFC 2606 / RFC 6761) and test TLDs
SYNTHETIC_TLDS: Set[str] = {
    "example", "test", "invalid", "localhost", "local", "internal"
}

# Synthetic and benchmark domain names
SYNTHETIC_DOMAINS: Set[str] = {
    "example.com", "example.org", "example.net",
    "test.com", "test.org", "test.net",
    "localhost", "designcorp.example", "reliableroofingtest.com"
}

# Internal or developer test email patterns (regex)
TEST_EMAIL_REGEX = re.compile(
    r"^(arttest@|"
    r"postmaster@|"
    r"sufiyan.*@|"
    r"mrsufiyan.*@|"
    r"classicshot\.7@|"
    r".*@agencyos\.tech|"
    r".*@vanceautomations\.test|"
    r".*@.*\.example$|"
    r".*@.*\.test$|"
    r".*@.*\.invalid$|"
    r".*@.*\.localhost$)",
    re.IGNORECASE
)


def is_test_or_synthetic(
    domain: Optional[str] = None,
    email: Optional[str] = None,
    name: Optional[str] = None
) -> bool:
    """
    Returns True if the domain, email, or entity name matches known test,
    developer, fixture, or synthetic patterns.
    """
    if domain:
        clean_domain = domain.strip().lower()
        if clean_domain.startswith("www."):
            clean_domain = clean_domain[4:]
        if clean_domain in SYNTHETIC_DOMAINS:
            return True
        tld = clean_domain.split(".")[-1] if "." in clean_domain else ""
        if tld in SYNTHETIC_TLDS:
            return True
        if "test" in clean_domain.split(".")[0] and len(clean_domain.split(".")[0]) <= 8:
            return True

    if email:
        clean_email = email.strip().lower()
        if TEST_EMAIL_REGEX.match(clean_email):
            return True
        email_domain = clean_email.split("@")[-1] if "@" in clean_email else ""
        if email_domain in SYNTHETIC_DOMAINS:
            return True
        email_tld = email_domain.split(".")[-1] if "." in email_domain else ""
        if email_tld in SYNTHETIC_TLDS:
            return True

    if name:
        clean_name = name.strip().lower()
        if clean_name in ("test business", "arttest", "test", "mock business"):
            return True

    return False


def get_synthetic_business_filter_clauses(business_model):
    """
    Returns a list of SQL binary expression clauses to filter out synthetic businesses.
    Usage: query.where(*get_synthetic_business_filter_clauses(Business))
    """
    clauses = [
        not_(business_model.domain.ilike("%.example")),
        not_(business_model.domain.ilike("%.test")),
        not_(business_model.domain.ilike("%.invalid")),
        not_(business_model.domain.ilike("%.localhost")),
        not_(business_model.domain.ilike("%.local")),
        not_(business_model.domain.in_(["example.com", "example.org", "test.com", "localhost", "reliableroofingtest.com"])),
    ]
    if hasattr(business_model, "public_email"):
        clauses.extend([
            or_(
                business_model.public_email.is_(None),
                and_(
                    not_(business_model.public_email.ilike("%@agencyos.tech")),
                    not_(business_model.public_email.ilike("arttest@%")),
                    not_(business_model.public_email.ilike("sufiyan%@%")),
                    not_(business_model.public_email.ilike("mrsufiyan%@%")),
                    not_(business_model.public_email.ilike("postmaster@%")),
                    not_(business_model.public_email.ilike("%.example")),
                    not_(business_model.public_email.ilike("%.test")),
                )
            )
        ])
    return clauses


def get_synthetic_outreach_filter_clauses(outreach_model):
    """
    Returns a list of SQL binary expression clauses to filter out synthetic outreach messages.
    Usage: query.where(*get_synthetic_outreach_filter_clauses(OutreachMessage))
    """
    return [
        not_(outreach_model.recipient_email.ilike("%@agencyos.tech")),
        not_(outreach_model.recipient_email.ilike("arttest@%")),
        not_(outreach_model.recipient_email.ilike("sufiyan%@%")),
        not_(outreach_model.recipient_email.ilike("mrsufiyan%@%")),
        not_(outreach_model.recipient_email.ilike("postmaster@%")),
        not_(outreach_model.recipient_email.ilike("%.example")),
        not_(outreach_model.recipient_email.ilike("%.test")),
        not_(outreach_model.recipient_email.ilike("%.invalid")),
        not_(outreach_model.recipient_email.ilike("%@example.com")),
        not_(outreach_model.recipient_email.ilike("%@test.com")),
    ]


def get_synthetic_reply_filter_clauses(reply_model):
    """
    Returns a list of SQL binary expression clauses to filter out synthetic reply messages.
    Usage: query.where(*get_synthetic_reply_filter_clauses(Reply))
    """
    return [
        not_(reply_model.sender_email.ilike("%@agencyos.tech")),
        not_(reply_model.sender_email.ilike("arttest@%")),
        not_(reply_model.sender_email.ilike("sufiyan%@%")),
        not_(reply_model.sender_email.ilike("mrsufiyan%@%")),
        not_(reply_model.sender_email.ilike("postmaster@%")),
        not_(reply_model.sender_email.ilike("%.example")),
        not_(reply_model.sender_email.ilike("%.test")),
        not_(reply_model.sender_email.ilike("%.invalid")),
        not_(reply_model.sender_email.ilike("%@example.com")),
        not_(reply_model.sender_email.ilike("%@test.com")),
        not_(reply_model.sender_email.ilike("classicshot.7@gmail.com")),
    ]
