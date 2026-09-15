"""Jurisdiction-Specific Provenance & Lawful Basis Engine.

Persists deterministic provenance for every outbound transmission:
- source_url
- observed_at
- publication_context
- recipient_role
- recipient_classification
- professional_relevance
- lawful_basis
- consent_status
- compliance_decision
- jurisdiction

CRITICAL INVARIANT:
Never use a generic 'CAN-SPAM / GDPR B2B legitimate interest' fallback.
Every decision must explicitly cite the governing statutory framework.
"""
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from app.compliance.recipient_classifier import RecipientClassification

# Statutory framework registry
LAWFUL_BASIS_REGISTRY = {
    "US": "15_USC_7701_CAN_SPAM_TRUTHFUL_B2B_WITH_PHYSICAL_ADDRESS_AND_OPTOUT",
    "UK": "PECR_REG_22_CORPORATE_SUBSCRIBER_WITH_UK_GDPR_ART_6_1_F_LIA",
    "CA": "CASL_SECTION_10_9_B_CONSPICUOUS_PUBLICATION_RELEVANT_INQUIRY",
    "AU": "SPAM_ACT_2003_SECTION_16_INFERRED_CONSENT_CONSPICUOUS_PUBLICATION",
    "NZ": "UEMA_2007_SECTION_9_5_INFERRED_CONSENT_CONSPICUOUS_PUBLICATION",
    "SG": "SPAM_CONTROL_ACT_CAP_311A_B2B_BUSINESS_CONTACT_EXEMPTION",
    "AE": "UAE_FEDERAL_DECREE_LAW_45_2021_TDRA_B2B_COMMERCIAL_INQUIRY",
    "SA": "SAUDI_PDPL_CITC_ANTI_SPAM_B2B_COMMERCIAL_INQUIRY",
    "FR": "CPCE_ART_L34_5_CNIL_PROFESSIONAL_B2B_EXEMPTION",
    "NL": "DUTCH_TELECOMMUNICATIEWET_ART_11_7_B2B_CORPORATE_ENTITY",
    "SE": "SWEDISH_MARKETING_ACT_B2B_LEGAL_ENTITY_EXEMPTION",
    "IE": "SI_336_2011_REG_13_CORPORATE_BODY_EXEMPTION",
    "JP": "SPECIFIED_ELECTRONIC_MAIL_ACT_PUBLIC_BUSINESS_ADDRESS",
    "QA": "QATAR_LAW_13_2016_PDP_B2B_COMMERCIAL_COMMUNICATION",
    "KW": "CITRA_REGULATORY_FRAMEWORK_B2B_COMMERCIAL_INQUIRY",
    "OM": "OMAN_ROYAL_DECREE_6_2022_PDPL_B2B_COMMERCIAL_INQUIRY",
    "BH": "BAHRAIN_LAW_30_2018_PDPL_B2B_COMMERCIAL_INQUIRY",
    "JO": "JORDAN_PDPL_2023_B2B_COMMERCIAL_INQUIRY",
    # Blocked jurisdictions (no lawful cold B2B basis without prior explicit consent)
    "DE": "CONSENT_REQUIRED_UWG_SECTION_7_2_NO_3",
    "IT": "CONSENT_REQUIRED_CODICE_PRIVACY_ART_130",
    "ES": "CONSENT_REQUIRED_LSSI_CE_ART_21",
    "CH": "CONSENT_REQUIRED_SWISS_UWG_ART_3_1_O"
}

STRICT_OPT_IN_JURISDICTIONS = frozenset(["DE", "IT", "ES", "CH"])


class JurisdictionProvenance(BaseModel):
    source_url: str = Field(description="Exact URL where the contact/business was observed")
    observed_at: str = Field(description="ISO timestamp when the public evidence was observed")
    publication_context: str = Field(description="Context in which email was published")
    recipient_role: str = Field(description="Observed recipient role or title")
    recipient_classification: str = Field(description="Deterministic entity classification")
    professional_relevance: str = Field(description="Nexus between message content and recipient business")
    lawful_basis: str = Field(description="Concrete jurisdiction-specific statutory citation")
    consent_status: str = Field(description="EXPLICIT_OPT_IN, INFERRED_CONSPICUOUS_PUBLICATION, B2B_STATUTORY_EXEMPTION, or NONE")
    compliance_decision: str = Field(description="PERMITTED or OUTBOUND_BLOCKED")
    blocking_reason: Optional[str] = Field(default=None, description="Specific statutory or policy blocking reason if blocked")
    jurisdiction: str = Field(description="ISO country code")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def resolve_lawful_basis(
    country_code: str,
    recipient_type: RecipientClassification,
    has_explicit_consent: bool = False
) -> Tuple[str, str, str, Optional[str]]:
    """
    Evaluates statutory basis based on country, recipient entity classification, and consent.
    
    Returns:
        (lawful_basis, consent_status, compliance_decision, blocking_reason)
    """
    cc = (country_code or "UNKNOWN").strip().upper()

    # Category C: Strict opt-in jurisdictions
    if cc in STRICT_OPT_IN_JURISDICTIONS:
        if has_explicit_consent:
            return (
                f"{cc}_VERIFIED_EXPLICIT_OPT_IN_CONSENT",
                "EXPLICIT_OPT_IN",
                "PERMITTED",
                None
            )
        basis = LAWFUL_BASIS_REGISTRY.get(cc, "CONSENT_REQUIRED")
        return (
            basis,
            "NONE",
            "OUTBOUND_BLOCKED",
            f"jurisdiction_requires_consent: Jurisdiction '{cc}' strictly prohibits unsolicited commercial email without verifiable prior explicit consent."
        )

    # Missing or unsupported country
    if cc not in LAWFUL_BASIS_REGISTRY:
        return (
            "UNKNOWN_JURISDICTION_NO_LAWFUL_BASIS",
            "NONE",
            "OUTBOUND_BLOCKED",
            f"unsupported_jurisdiction: Unknown or unsupported jurisdiction '{cc}'."
        )

    # Recipient Entity Discrimination
    if recipient_type == RecipientClassification.PERSONAL_WEBMAIL:
        # Personal webmail is strictly disallowed in jurisdictions with corporate-only exemptions
        if cc in ("UK", "CA", "AU", "FR", "NL", "SE", "IE", "NZ"):
            return (
                "PERSONAL_WEBMAIL_INELIGIBLE_FOR_B2B_EXEMPTION",
                "NONE",
                "OUTBOUND_BLOCKED",
                f"personal_webmail_ineligible: Recipient uses personal webmail in jurisdiction '{cc}' which requires corporate subscriber or explicit opt-in."
            )
        elif cc == "US":
            # CAN-SPAM applies to all email types if truthful and opt-out provided
            return (
                LAWFUL_BASIS_REGISTRY["US"],
                "B2B_STATUTORY_EXEMPTION",
                "PERMITTED",
                None
            )
        else:
            # GCC / Others: Caution on personal webmail
            return (
                f"{cc}_PERSONAL_WEBMAIL_CAUTION",
                "NONE",
                "OUTBOUND_BLOCKED",
                f"personal_webmail_ineligible: Personal webmail cannot be verified as corporate in '{cc}'."
            )

    if recipient_type == RecipientClassification.SOLE_TRADER:
        # Sole traders treated as natural persons under UK PECR / European ePrivacy
        if cc in ("UK", "FR", "NL", "SE", "IE"):
            return (
                "SOLE_TRADER_REQUIRES_OPT_IN_CONSENT",
                "NONE",
                "OUTBOUND_BLOCKED",
                f"sole_trader_requires_consent: Recipient is a sole trader / natural person in jurisdiction '{cc}', requiring prior opt-in under PECR/ePrivacy."
            )

    if recipient_type == RecipientClassification.UNKNOWN:
        return (
            "UNVERIFIED_RECIPIENT_ENTITY",
            "NONE",
            "OUTBOUND_BLOCKED",
            "unverified_recipient_entity: Cannot verify recipient domain matches business entity."
        )

    # Permitted corporate subscriber / B2B public address
    statutory_citation = LAWFUL_BASIS_REGISTRY[cc]
    consent_status = (
        "INFERRED_CONSPICUOUS_PUBLICATION"
        if cc in ("CA", "AU", "NZ", "JP")
        else "B2B_STATUTORY_EXEMPTION"
    )
    return statutory_citation, consent_status, "PERMITTED", None


def build_jurisdiction_provenance(
    country_code: str,
    email: str,
    business_name: Optional[str] = None,
    business_domain: Optional[str] = None,
    source_url: Optional[str] = None,
    observed_at: Optional[datetime] = None,
    recipient_role: Optional[str] = None,
    recipient_classification: Optional[RecipientClassification] = None,
    audit_summary: Optional[str] = None,
    has_explicit_consent: bool = False
) -> JurisdictionProvenance:
    """Constructs a fully grounded JurisdictionProvenance object."""
    cc = (country_code or "UNKNOWN").strip().upper()
    r_class = recipient_classification or RecipientClassification.UNKNOWN

    lawful_basis, consent_status, decision, block_reason = resolve_lawful_basis(
        country_code=cc,
        recipient_type=r_class,
        has_explicit_consent=has_explicit_consent
    )

    clean_source = source_url or (f"https://{business_domain}" if business_domain else "public_web_discovery")
    obs_time = (observed_at or datetime.utcnow()).isoformat()
    role = recipient_role or "Owner / Lead"
    
    relevance = audit_summary or (
        f"Technical web turnaround & performance audit of observable digital presence {business_domain or ''}."
    )
    
    context = (
        f"Conspicuously published on public website ({clean_source}) in a commercial/business capacity."
        if r_class != RecipientClassification.PERSONAL_WEBMAIL
        else "Personal webmail address identified."
    )

    return JurisdictionProvenance(
        source_url=clean_source,
        observed_at=obs_time,
        publication_context=context,
        recipient_role=role,
        recipient_classification=r_class.value,
        professional_relevance=relevance,
        lawful_basis=lawful_basis,
        consent_status=consent_status,
        compliance_decision=decision,
        blocking_reason=block_reason,
        jurisdiction=cc
    )
