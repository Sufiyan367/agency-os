from datetime import datetime
from typing import Tuple
from urllib.parse import urlparse
from app.core.security import is_safe_url

class EvidenceValidator:
    """Validates real public evidence to ensure integrity and prevent SSRF/fabrication."""

    def validate(
        self,
        source_url: str,
        claim: str,
        raw_excerpt: str,
        country_code: str,
        publication_date: datetime = None,
        confidence: float = 0.8
    ) -> Tuple[bool, str]:
        if not source_url or not source_url.strip():
            return False, "Source URL cannot be empty."

        parsed = urlparse(source_url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid URL scheme: {parsed.scheme}."

        if not parsed.netloc:
            return False, "Invalid URL: missing network location / domain."

        safe, reason = is_safe_url(source_url)
        if not safe:
            return False, f"Security rejection (SSRF guard): {reason}"

        if not claim or len(claim.strip()) < 5:
            return False, "Market claim is too short or empty."

        if not raw_excerpt or len(raw_excerpt.strip()) < 5:
            return False, "Evidence raw excerpt is too short or empty."

        if not country_code or len(country_code.strip()) not in (2, 3):
            return False, f"Invalid country code: {country_code}."

        if publication_date:
            now = datetime.now(publication_date.tzinfo) if publication_date.tzinfo else datetime.utcnow()
            if publication_date > now:
                return False, "Publication date cannot be in the future."

        if not (0.0 <= confidence <= 1.0):
            return False, f"Confidence {confidence} must be between 0.0 and 1.0."

        return True, "Valid"

evidence_validator = EvidenceValidator()
