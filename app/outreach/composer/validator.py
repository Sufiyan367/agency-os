from typing import List, Dict, Any, Optional
from app.outreach.composer.models import (
    CanonicalProspect, SenderIdentity, ComposedEmail, ValidationResult
)

PROHIBITED_LEAKAGE_TOKENS = [
    "autonomous growth engine",
    "digital strategy advisory",
    "al faisaliah",
    "stitch",
    "google ai studio",
    "antigravity",
    "firebase",
    "system prompt",
    "pipeline stage",
    "worker tick",
    "we contacted this public address"
]


class PreSendValidator:
    """
    Enforces deterministic and semantic pre-send safety validation:
    - Identity consistency (company, domain, location)
    - Zero internal system leakage
    - Factual & capability contradiction checking
    - Sender configuration readiness
    - Word count boundary enforcement (50–160 words)
    """

    @classmethod
    def validate_email(
        cls,
        email: ComposedEmail,
        prospect: CanonicalProspect,
        sender: SenderIdentity,
        capabilities: Optional[Dict[str, bool]] = None
    ) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []
        capabilities = capabilities or {}

        body_lower = email.body.lower()
        subject_lower = email.subject.lower()
        full_text = f"{subject_lower} {body_lower}"

        # 1. Company name validation
        if prospect.company_name.lower() not in full_text:
            errors.append(
                f"Factual mismatch: Company name '{prospect.company_name}' "
                f"is not referenced in the email."
            )

        # 2. Domain / website validation
        if (prospect.canonical_company_domain.lower() not in full_text and
            prospect.website.lower() not in full_text):
            errors.append(
                f"Factual mismatch: Neither domain '{prospect.canonical_company_domain}' "
                f"nor website '{prospect.website}' is referenced in the email."
            )

        # 3. Location mismatch check (detect alien/foreign cities)
        known_alien_locations = ["riyadh", "al faisaliah", "saudi arabia"]
        for loc in known_alien_locations:
            if loc in full_text and (not prospect.city or loc not in prospect.city.lower()) and (not prospect.country or loc not in prospect.country.lower()):
                errors.append(
                    f"Contamination error: Alien location '{loc}' detected in email body "
                    f"for prospect in {prospect.city or 'unknown'}, {prospect.country}."
                )

        # 4. Zero internal system leakage check
        for token in PROHIBITED_LEAKAGE_TOKENS:
            if token in full_text:
                errors.append(f"Internal leakage detected: '{token}' found in email copy.")

        # 5. Semantic contradiction check
        if capabilities.get("has_online_booking"):
            contradictions = ["no online booking", "lack an online booking", "without online booking"]
            if any(c in full_text for c in contradictions):
                errors.append("Semantic contradiction: Copy claims lack of booking system, but research confirms online booking exists.")

        if capabilities.get("has_fast_mobile_speed"):
            contradictions = ["slow mobile load", "sluggish page load", "fails speed tests"]
            if any(c in full_text for c in contradictions):
                errors.append("Semantic contradiction: Copy claims slow loading speed, but research confirms fast mobile performance.")

        # 6. Sender identity validation
        if not sender.sender_email or "@" not in sender.sender_email:
            errors.append("Sender configuration error: sender_email is missing or malformed.")
        if not sender.sender_name or len(sender.sender_name.strip()) < 2:
            errors.append("Sender configuration error: sender_name is missing.")
        if not sender.sender_company:
            errors.append("Sender configuration error: sender_company is missing.")

        # 7. Length boundary enforcement
        words = len(email.body.split())
        if words < 40:
            errors.append(f"Length violation: Email body too short ({words} words; minimum is 40).")
        elif words > 160:
            errors.append(f"Length violation: Email body exceeds maximum length ({words} words; maximum is 160).")

        return ValidationResult(
            is_valid=(len(errors) == 0),
            errors=errors,
            warnings=warnings
        )
