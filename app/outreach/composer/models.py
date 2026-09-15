from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class CanonicalProspect:
    """Single canonical identity representation for an outreach prospect."""
    prospect_id: int
    company_name: str
    website: str
    canonical_company_domain: str
    recipient_email: str
    recipient_name: Optional[str] = None
    industry: str = "General Business"
    city: Optional[str] = None
    state_or_region: Optional[str] = None
    country: str = "US"
    phone: Optional[str] = None


@dataclass
class ResearchFact:
    """A factual research item grounded in verified prospect analysis."""
    prospect_id: int
    fact: str
    source: str  # e.g., "audit:performance", "audit:ux", "evidence:booking", "evidence:contact"
    category: str  # e.g., "speed", "conversion", "booking", "workflow", "seo", "a11y"
    is_verified: bool = True
    metric_value: Optional[Any] = None


@dataclass
class SenderIdentity:
    """Configured sender credentials and signature details."""
    sender_name: str
    sender_email: str
    sender_company: str
    sender_role: Optional[str] = None
    reply_to: Optional[str] = None

    def signature(self) -> str:
        role_part = f"\n{self.sender_role}" if self.sender_role else ""
        return f"Best,\n{self.sender_name}{role_part}\n{self.sender_company}"


@dataclass
class ComplianceProfile:
    """Configurable legal and compliance disclosure settings."""
    enabled: bool = False
    business_name: Optional[str] = None
    postal_address: Optional[str] = None
    unsubscribe_text: Optional[str] = None
    privacy_link: Optional[str] = None
    custom_disclosure: Optional[str] = None

    def render_footer(self) -> str:
        if not self.enabled:
            return ""

        parts = []
        if self.postal_address:
            parts.append(f"Mailing Address: {self.postal_address.strip()}")
        if self.unsubscribe_text:
            parts.append(self.unsubscribe_text.strip())
        elif self.business_name:
            parts.append("To opt out of future messages, reply 'unsubscribe'.")

        if self.privacy_link:
            parts.append(f"Privacy Policy: {self.privacy_link.strip()}")
        if self.custom_disclosure:
            parts.append(self.custom_disclosure.strip())

        if not parts:
            return ""

        return "\n\n---\n" + "\n".join(parts)


@dataclass
class ComposedEmail:
    """A generated, validated email draft ready for approval or dispatch."""
    subject: str
    body: str
    word_count: int
    variant_name: str
    prospect_id: int
    solution_matched: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ValidationResult:
    """Result of entity resolution or pre-send validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
