"""Deterministic Recipient Classification Engine.

Implements strict entity-type discrimination for global outbound compliance:
- CORPORATE_DOMAIN
- ROLE_BASED_CORPORATE
- IDENTIFIED_CORPORATE_CONTACT
- SOLE_TRADER
- PERSONAL_WEBMAIL
- UNKNOWN

INVARIANT: Personal webmail domains must NEVER be treated as corporate recipients.
INVARIANT: Corporate status must NEVER be inferred solely from a job title.
"""
import enum
import re
from typing import Optional, Tuple

class RecipientClassification(str, enum.Enum):
    CORPORATE_DOMAIN = "CORPORATE_DOMAIN"
    ROLE_BASED_CORPORATE = "ROLE_BASED_CORPORATE"
    IDENTIFIED_CORPORATE_CONTACT = "IDENTIFIED_CORPORATE_CONTACT"
    SOLE_TRADER = "SOLE_TRADER"
    PERSONAL_WEBMAIL = "PERSONAL_WEBMAIL"
    UNKNOWN = "UNKNOWN"

# Exhaustive registry of consumer / personal webmail domains
PERSONAL_WEBMAIL_DOMAINS = frozenset([
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "yahoo.ca", "yahoo.fr", "yahoo.de", "yahoo.es", "yahoo.it", "ymail.com",
    "hotmail.com", "hotmail.co.uk", "hotmail.fr", "hotmail.de", "hotmail.es", "hotmail.it",
    "outlook.com", "outlook.co.uk", "live.com", "live.co.uk", "msn.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "aim.com",
    "proton.me", "protonmail.com",
    "zoho.com", "zohomail.com",
    "mail.com", "email.com",
    "gmx.com", "gmx.net", "gmx.de", "web.de", "t-online.de",
    "yandex.com", "yandex.ru",
    "fastmail.com", "hushmail.com",
    "rediffmail.com", "libero.it", "virgilio.it",
    "wanadoo.fr", "orange.fr", "free.fr", "sfr.fr"
])

# Role-based functional mailboxes
ROLE_BASED_LOCAL_PARTS = frozenset([
    "info", "contact", "hello", "support", "sales", "office", "admin",
    "team", "inquiries", "enquiries", "help", "billing", "service",
    "frontdesk", "reception", "mail", "general", "customercare",
    "feedback", "marketing", "operations", "booking", "appointments"
])

# Statutory corporate entity markers in business legal names
CORPORATE_ENTITY_MARKERS = [
    r"\bltd\b", r"\blimited\b",
    r"\bllc\b", r"\bl\.l\.c\.\b",
    r"\binc\b", r"\binc\.\b", r"\bincorporated\b",
    r"\bcorp\b", r"\bcorp\.\b", r"\bcorporation\b",
    r"\bplc\b", r"\bp\.l\.c\.\b",
    r"\bllp\b", r"\bl\.l\.p\.\b",
    r"\bgmbh\b", r"\bag\b",
    r"\bb\.v\.\b", r"\bbv\b",
    r"\bs\.a\.\b", r"\bsa\b",
    r"\bs\.l\.\b", r"\bsl\b",
    r"\bs\.r\.l\.\b", r"\bsrl\b",
    r"\bpty\s+ltd\b", r"\bpty\.\s*ltd\b",
    r"\bw\.l\.l\b", r"\bwll\b",
    r"\bspc\b", r"\bs\.p\.c\.\b",
    r"\bq\.p\.s\.c\b", r"\bqpsc\b",
    r"\bj\.s\.c\b", r"\bjsc\b",
    r"\bs\.a\.o\.g\b", r"\bsaog\b",
    r"\bs\.a\.o\.c\b", r"\bsaoc\b"
]
CORPORATE_REGEX = re.compile("|".join(CORPORATE_ENTITY_MARKERS), re.IGNORECASE)

# Sole trader / individual trader markers
SOLE_TRADER_MARKERS = [
    r"\bsole\s+trader\b", r"\bsole\s+proprietor\b",
    r"\bfreelanc", r"\bself-employed\b", r"\btrading\s+as\b",
    r"\bt\/a\b"
]
SOLE_TRADER_REGEX = re.compile("|".join(SOLE_TRADER_MARKERS), re.IGNORECASE)


def parse_email_parts(email: str) -> Tuple[str, str]:
    """Safely extracts (local_part, domain) in lower-case."""
    if not email or "@" not in email:
        return "", ""
    parts = email.strip().lower().split("@", 1)
    return parts[0], parts[1]


def is_personal_webmail(email: str) -> bool:
    """Returns True if the email domain belongs to a consumer/free webmail provider."""
    _, domain = parse_email_parts(email)
    return domain in PERSONAL_WEBMAIL_DOMAINS


def is_role_based_address(email: str) -> bool:
    """Returns True if the email local-part matches a generic role-based inbox."""
    local_part, _ = parse_email_parts(email)
    # Strip dots/plus e.g. info+leads -> info
    clean_local = local_part.split("+")[0].split(".")[0]
    return clean_local in ROLE_BASED_LOCAL_PARTS


def classify_recipient(
    email: str,
    business_name: Optional[str] = None,
    business_domain: Optional[str] = None,
    contact_name: Optional[str] = None,
    contact_title: Optional[str] = None
) -> RecipientClassification:
    """
    Deterministically classifies a recipient.
    
    Rules:
    1. If the email domain is in PERSONAL_WEBMAIL_DOMAINS -> PERSONAL_WEBMAIL (Never corporate).
    2. If email format is invalid or empty -> UNKNOWN.
    3. If local part is role-based (info@, contact@, etc.) on a business domain -> ROLE_BASED_CORPORATE.
    4. If business name explicitly matches sole-trader patterns -> SOLE_TRADER.
    5. If corporate entity markers match in business name AND email has identifiable name -> IDENTIFIED_CORPORATE_CONTACT.
    6. If email belongs to a business domain with corporate markers -> CORPORATE_DOMAIN.
    7. If business domain matches email domain without explicit corporate markers -> CORPORATE_DOMAIN.
    8. Otherwise -> UNKNOWN.
    """
    local_part, email_domain = parse_email_parts(email)
    if not local_part or not email_domain:
        return RecipientClassification.UNKNOWN

    # RULE 1: Personal webmail is strictly PERSONAL_WEBMAIL regardless of title
    if email_domain in PERSONAL_WEBMAIL_DOMAINS:
        return RecipientClassification.PERSONAL_WEBMAIL

    # Check for sole trader markers in business identity
    b_name = (business_name or "").strip()
    if SOLE_TRADER_REGEX.search(b_name):
        return RecipientClassification.SOLE_TRADER

    # Check for corporate entity markers in business name
    has_corporate_marker = bool(CORPORATE_REGEX.search(b_name))

    # Clean domain comparison
    clean_b_domain = (business_domain or "").strip().lower()
    if clean_b_domain.startswith("http://") or clean_b_domain.startswith("https://"):
        clean_b_domain = clean_b_domain.split("://", 1)[1]
    clean_b_domain = clean_b_domain.split("/", 1)[0].replace("www.", "")

    domain_matches_business = bool(clean_b_domain and (clean_b_domain == email_domain or email_domain.endswith(f".{clean_b_domain}")))

    # RULE 2: Role-based address on corporate/business domain
    if is_role_based_address(email):
        return RecipientClassification.ROLE_BASED_CORPORATE

    # RULE 3: Identified contact on corporate domain
    # Check if contact_name is an actual human name (not default placeholder)
    is_named_contact = bool(
        contact_name and
        contact_name.strip() and
        "owner" not in contact_name.lower() and
        "lead" not in contact_name.lower() and
        "marketing" not in contact_name.lower() and
        contact_name != "Business Owner / Marketing Lead"
    )

    # Also inspect local_part for naming structure (e.g. john.smith, jsmith, john-smith)
    has_name_syntax = bool("." in local_part or "_" in local_part or "-" in local_part)

    if (is_named_contact or has_name_syntax) and (has_corporate_marker or domain_matches_business):
        return RecipientClassification.IDENTIFIED_CORPORATE_CONTACT

    # RULE 4: Corporate domain
    if domain_matches_business or has_corporate_marker:
        return RecipientClassification.CORPORATE_DOMAIN

    # If domain does not match business domain and no corporate markers exist
    if not domain_matches_business:
        return RecipientClassification.UNKNOWN

    return RecipientClassification.CORPORATE_DOMAIN
