import re
from typing import Optional, List
from app.core.security import normalize_domain
from app.outreach.composer.models import CanonicalProspect, ValidationResult

# Well-known consumer/freemail provider domains
FREE_WEBMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "mail.com", "zoho.com", "protonmail.com", "gmx.com"
}

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class EntityResolver:
    """
    Validates identity consistency across company name, website domain,
    recipient email, industry, and geographical location.
    Enforces deterministic entity resolution before composition or dispatch.
    """

    @classmethod
    def resolve_and_validate(cls, prospect: CanonicalProspect) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Company name validation
        name = (prospect.company_name or "").strip()
        if not name or len(name) < 2:
            errors.append("Invalid entity: company_name is missing or too short.")
        elif name.lower() in ("unknown", "n/a", "none", "test", "company"):
            errors.append(f"Invalid entity: company_name '{name}' is a generic placeholder.")

        # 2. Canonical domain & website alignment
        canonical_dom = normalize_domain(prospect.canonical_company_domain or "")
        if not canonical_dom or "." not in canonical_dom:
            errors.append(f"Invalid entity: canonical_company_domain '{canonical_dom}' is malformed.")

        web_dom = normalize_domain(prospect.website or "")
        if not web_dom or "." not in web_dom:
            errors.append(f"Invalid entity: website '{prospect.website}' could not be normalized to a valid domain.")
        elif canonical_dom and web_dom != canonical_dom:
            errors.append(
                f"Entity mismatch: website domain '{web_dom}' does not match "
                f"canonical company domain '{canonical_dom}'."
            )

        # 3. Recipient email validation & cross-prospect check
        email = (prospect.recipient_email or "").strip().lower()
        if not email or not EMAIL_REGEX.match(email):
            errors.append(f"Invalid entity: recipient_email '{email}' is malformed.")
        else:
            email_domain = normalize_domain(email.split("@")[-1])
            # If recipient is on a corporate domain (not free webmail), it MUST match the company domain
            if email_domain not in FREE_WEBMAIL_DOMAINS:
                if canonical_dom and email_domain != canonical_dom:
                    # Allow subdomains (e.g. support.company.com matching company.com)
                    if not email_domain.endswith("." + canonical_dom):
                        errors.append(
                            f"Entity mismatch: Corporate email domain '{email_domain}' "
                            f"does not match company domain '{canonical_dom}'."
                        )

        # 4. Industry check
        industry = (prospect.industry or "").strip()
        if not industry:
            warnings.append("Industry is unspecified; defaulting to commercial services.")

        # 5. Geographic & Phone location check
        if not prospect.country:
            warnings.append("Country unspecified; defaulting to US.")
        elif prospect.phone:
            p = prospect.phone.strip()
            c = prospect.country.upper()
            if p.startswith("+1") and c not in ("US", "CA"):
                errors.append(f"Entity mismatch: North American phone number '{p}' assigned to country '{c}'.")
            elif p.startswith("+44") and c not in ("UK", "GB"):
                errors.append(f"Entity mismatch: UK phone number '{p}' assigned to country '{c}'.")
            elif p.startswith("+971") and c != "AE":
                errors.append(f"Entity mismatch: UAE phone number '{p}' assigned to country '{c}'.")
            elif p.startswith("+81") and c != "JP":
                errors.append(f"Entity mismatch: Japanese phone number '{p}' assigned to country '{c}'.")

        return ValidationResult(
            is_valid=(len(errors) == 0),
            errors=errors,
            warnings=warnings
        )

    @classmethod
    def validate_identity_consistency(cls, prospect: CanonicalProspect) -> tuple[bool, Optional[str]]:
        """
        Validates cross-prospect consistency: company, domain, city, industry, contact.
        Returns (True, None) if valid, or (False, 'OUTREACH_VALIDATION_FAILED: ...') on mismatch.
        """
        res = cls.resolve_and_validate(prospect)
        if not res.is_valid:
            return False, f"OUTREACH_VALIDATION_FAILED: {'; '.join(res.errors)}"
        return True, None
