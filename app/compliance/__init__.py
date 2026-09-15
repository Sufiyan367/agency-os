"""Jurisdiction-Specific Outbound Compliance Package.
Deterministic recipient classification, negative disclaimer detection,
and statutory provenance tracking across international corridors.
"""
from app.compliance.recipient_classifier import (
    RecipientClassification,
    classify_recipient,
    is_personal_webmail,
    is_role_based_address
)
from app.compliance.negative_disclaimer import (
    detect_negative_disclaimer,
    contains_prohibited_contact_notice
)
from app.compliance.provenance import (
    JurisdictionProvenance,
    resolve_lawful_basis,
    build_jurisdiction_provenance
)

__all__ = [
    "RecipientClassification",
    "classify_recipient",
    "is_personal_webmail",
    "is_role_based_address",
    "detect_negative_disclaimer",
    "contains_prohibited_contact_notice",
    "JurisdictionProvenance",
    "resolve_lawful_basis",
    "build_jurisdiction_provenance",
]
