import re
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, Set

logger = logging.getLogger(__name__)

@dataclass
class ContactVerificationResult:
    is_valid: bool
    status: str  # "CONTACTABLE" or "CONTACT_UNAVAILABLE"
    email: Optional[str]
    email_source: Optional[str]
    verified: bool
    reason: str
    domain_match: bool


class ContactabilityVerifier:
    """
    Verifies that prospect contact channels are legitimate and observed before
    outreach messages can be queued or transmitted.
    Strictly forbids guessing, fabricating, or synthesizing email addresses.
    """

    # Placeholder and demo domain blacklist
    PLACEHOLDER_DOMAINS: Set[str] = {
        "example.com", "example.org", "example.net",
        "test.com", "test.org", "test.net",
        "domain.com", "placeholder.com", "yourcompany.com",
        "mywebsite.com", "company.com", "sample.com",
        "client.com", "agencygrowth.co", "localhost", "none"
    }

    # Free consumer mail provider blacklist
    FREE_MAIL_DOMAINS: Set[str] = {
        "gmail.com", "googlemail.com",
        "yahoo.com", "ymail.com", "rocketmail.com",
        "hotmail.com", "live.com", "msn.com", "outlook.com",
        "aol.com", "aim.com",
        "icloud.com", "me.com", "mac.com",
        "protonmail.com", "proton.me", "pm.me",
        "mail.com", "gmx.com", "zoho.com"
    }

    # Strict standard email format regex (RFC 5322 compatible subset)
    EMAIL_REGEX = re.compile(
        r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    )

    @classmethod
    def verify_contact_email(
        cls,
        email: Optional[str],
        business_domain: Optional[str],
        source: Optional[str] = None,
        allow_free_mail: bool = False
    ) -> ContactVerificationResult:
        """
        Validates observed email against legitimacy rules:
        1. Checks for presence (never synthesizes missing emails).
        2. Validates syntactic structure.
        3. Checks against placeholder and sinkhole domains.
        4. Checks against free consumer webmail (unless allow_free_mail is True).
        5. Verifies domain alignment with the business entity.
        """
        # 1. Reject missing or empty email
        if not email or not email.strip():
            return ContactVerificationResult(
                is_valid=False,
                status="CONTACT_UNAVAILABLE",
                email=None,
                email_source=source,
                verified=False,
                reason="No public contact email was legitimately observed for this business. Fabrication is strictly prohibited.",
                domain_match=False
            )

        clean_email = email.strip().lower()

        # 2. Syntax validation
        if not cls.EMAIL_REGEX.match(clean_email):
            return ContactVerificationResult(
                is_valid=False,
                status="CONTACT_UNAVAILABLE",
                email=clean_email,
                email_source=source,
                verified=False,
                reason=f"Malformed email syntax: '{clean_email}'.",
                domain_match=False
            )

        parts = clean_email.split("@")
        if len(parts) != 2:
            return ContactVerificationResult(
                is_valid=False,
                status="CONTACT_UNAVAILABLE",
                email=clean_email,
                email_source=source,
                verified=False,
                reason="Invalid email format.",
                domain_match=False
            )

        mailbox, email_domain = parts[0], parts[1]

        # Reject obvious fabricated prefixes
        if mailbox in ("null", "undefined", "none", "fake", "placeholder"):
            return ContactVerificationResult(
                is_valid=False,
                status="CONTACT_UNAVAILABLE",
                email=clean_email,
                email_source=source,
                verified=False,
                reason=f"Placeholder mailbox name '{mailbox}' rejected.",
                domain_match=False
            )

        # 3. Check placeholder domains
        if email_domain in cls.PLACEHOLDER_DOMAINS or any(email_domain.endswith("." + p) for p in cls.PLACEHOLDER_DOMAINS):
            return ContactVerificationResult(
                is_valid=False,
                status="CONTACT_UNAVAILABLE",
                email=clean_email,
                email_source=source,
                verified=False,
                reason=f"Placeholder/example domain '@{email_domain}' is not a legitimate recipient.",
                domain_match=False
            )

        # 4. Check free mail providers
        if not allow_free_mail and email_domain in cls.FREE_MAIL_DOMAINS:
            return ContactVerificationResult(
                is_valid=False,
                status="CONTACT_UNAVAILABLE",
                email=clean_email,
                email_source=source,
                verified=False,
                reason=f"Consumer free-mail provider '@{email_domain}' rejected for corporate B2B outreach.",
                domain_match=False
            )

        # 5. Check domain alignment with business domain
        domain_matched = False
        if business_domain:
            norm_biz_dom = business_domain.lower().replace("www.", "").strip()
            if email_domain == norm_biz_dom or email_domain.endswith("." + norm_biz_dom):
                domain_matched = True

        verification_reason = (
            f"Verified observed business email '@{email_domain}' matching business domain."
            if domain_matched
            else f"Verified legitimate public contact email '@{email_domain}'."
        )

        return ContactVerificationResult(
            is_valid=True,
            status="CONTACTABLE",
            email=clean_email,
            email_source=source or "observed_public_registry",
            verified=True,
            reason=verification_reason,
            domain_match=domain_matched
        )

contactability_verifier = ContactabilityVerifier()
