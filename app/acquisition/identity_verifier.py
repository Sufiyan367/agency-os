import re
from typing import Dict, Any, Optional, List, Tuple, Set
from pydantic import BaseModel, Field

from app.core.security import normalize_domain

CORPORATE_SUFFIXES = {
    "ltd", "limited", "llc", "inc", "incorporated", "corp", "corporation",
    "co", "company", "services", "contractors", "enterprises", "group", "holdings",
    "pty", "gmbh", "sarl", "bv", "sa", "plc"
}

def clean_business_name(name: str) -> str:
    """Normalizes business name by removing punctuation, corporate suffixes, and excessive whitespace."""
    if not name:
        return ""
    text = name.lower()
    # Replace special chars with spaces
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    filtered = [t for t in tokens if t not in CORPORATE_SUFFIXES and len(t) > 1]
    return " ".join(filtered) if filtered else text.strip()

def normalize_phone_digits(phone: Optional[str]) -> str:
    """Extracts only digits from phone number for robust comparison."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    # If starts with country code like 1 or 44, retain last 10 digits for local comparison
    if len(digits) > 10:
        return digits[-10:]
    return digits

class IdentityMatchResult(BaseModel):
    is_match: bool
    confidence: float
    match_reason: str
    signals_matched: List[str] = Field(default_factory=list)
    signals_conflicted: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)

class BusinessIdentityVerifier:
    """
    Empirically verifies whether an external source relates to the SAME business entity
    or a distinct/unrelated entity with an overlapping name.
    """

    def verify_identity(
        self,
        candidate_name: str,
        candidate_domain: str,
        candidate_city: Optional[str],
        candidate_phone: Optional[str],
        source_title: Optional[str],
        source_text: str,
        source_domain: str,
        source_phone: Optional[str] = None,
        source_city: Optional[str] = None
    ) -> IdentityMatchResult:
        matched_signals: List[str] = []
        conflicted_signals: List[str] = []

        norm_cand_domain = normalize_domain(candidate_domain)
        norm_src_domain = normalize_domain(source_domain)

        # 1. Direct Domain Reference in Source Content or Source Domain
        domain_matched = False
        if norm_cand_domain:
            if norm_cand_domain == norm_src_domain:
                domain_matched = True
                matched_signals.append(f"Domain exact match ({norm_cand_domain})")
            elif norm_cand_domain in source_text.lower():
                domain_matched = True
                matched_signals.append(f"Candidate domain cited in source text ({norm_cand_domain})")

        # 2. Business Name Match
        clean_cand = clean_business_name(candidate_name)
        clean_src = clean_business_name(source_title or "")
        
        name_matched = False
        name_score = 0.0

        if clean_cand and clean_src:
            cand_tokens = set(clean_cand.split())
            src_tokens = set(clean_src.split())
            intersection = cand_tokens.intersection(src_tokens)
            union = cand_tokens.union(src_tokens)
            if union:
                name_score = len(intersection) / len(union)

            if name_score >= 0.50 or clean_cand in clean_src or clean_src in clean_cand:
                name_matched = True
                matched_signals.append(f"Name token overlap ({name_score:.2f}) between '{clean_cand}' and '{clean_src}'")
            else:
                conflicted_signals.append(f"Name divergence: '{clean_cand}' vs '{clean_src}'")
        elif clean_cand and clean_cand in source_text.lower():
            name_matched = True
            name_score = 0.70
            matched_signals.append(f"Candidate name '{clean_cand}' present in source body")

        # 3. Phone Match
        phone_matched = False
        cand_p = normalize_phone_digits(candidate_phone)
        src_p = normalize_phone_digits(source_phone)
        if cand_p and src_p:
            if cand_p == src_p:
                phone_matched = True
                matched_signals.append(f"Phone number match ({cand_p})")
            else:
                conflicted_signals.append(f"Phone divergence: '{cand_p}' vs '{src_p}'")
        elif cand_p and cand_p in source_text:
            phone_matched = True
            matched_signals.append(f"Phone number {cand_p} verified in source content")

        # 4. Location / City Match
        location_matched = False
        if candidate_city and candidate_city.strip():
            c_city = candidate_city.lower().strip()
            if source_city and source_city.lower().strip() == c_city:
                location_matched = True
                matched_signals.append(f"City match ({candidate_city})")
            elif c_city in source_text.lower():
                location_matched = True
                matched_signals.append(f"City '{candidate_city}' confirmed in source content")
            elif source_city and source_city.lower().strip() != c_city:
                conflicted_signals.append(f"Geographic discrepancy: '{candidate_city}' vs '{source_city}'")

        # Decision Matrix
        # Case A: Same domain -> Always matches identity
        if norm_cand_domain and norm_cand_domain == norm_src_domain:
            return IdentityMatchResult(
                is_match=True,
                confidence=0.98,
                match_reason="First-party official domain match.",
                signals_matched=matched_signals,
                signals_conflicted=conflicted_signals
            )

        # Case B: Independent Source citing domain AND name
        if domain_matched and name_matched:
            return IdentityMatchResult(
                is_match=True,
                confidence=0.95,
                match_reason="Corroborated by independent domain citation and business name presence.",
                signals_matched=matched_signals,
                signals_conflicted=conflicted_signals
            )

        # Case C: Name match AND Phone match
        if name_matched and phone_matched:
            return IdentityMatchResult(
                is_match=True,
                confidence=0.92,
                match_reason="Corroborated by matching business name and registered telephone number.",
                signals_matched=matched_signals,
                signals_conflicted=conflicted_signals
            )

        # Case D: Name match AND City match without phone or domain conflict
        if name_matched and location_matched and not conflicted_signals:
            return IdentityMatchResult(
                is_match=True,
                confidence=0.82,
                match_reason=f"Corroborated by matching business name in geographic area ({candidate_city}).",
                signals_matched=matched_signals,
                signals_conflicted=conflicted_signals
            )

        # Case E: Mismatch / Conflicting company
        reason = f"Identity mismatch or insufficient corroboration. Matched: {matched_signals}; Conflicted: {conflicted_signals}"
        return IdentityMatchResult(
            is_match=False,
            confidence=0.20,
            match_reason=reason,
            signals_matched=matched_signals,
            signals_conflicted=conflicted_signals
        )

identity_verifier = BusinessIdentityVerifier()
