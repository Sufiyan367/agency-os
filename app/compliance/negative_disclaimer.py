"""Negative Disclaimer Detection Engine.

Statutory basis:
- Canadian CASL § 10(9)(b): Exemption inapplicable if accompanied by a statement that
  unsolicited commercial electronic messages are not accepted.
- Australian Spam Act 2003 § 16 / Sch 2: Inferred consent invalidated by express refusal.
- New Zealand UEMA 2007 § 9(5): Consent not inferred if statement refusing messages is present.
- UK / EU / Global: Express notice forbidding marketing strips legitimate interest basis.
"""
import re
from typing import Optional, Tuple, List

NEGATIVE_DISCLAIMER_PATTERNS = [
    # English
    r"no\s+unsolicited\s+(?:messages?|emails?|commercial|marketing|mail)",
    r"do\s+not\s+(?:send|contact\s+us\s+with)\s+unsolicited",
    r"no\s+(?:marketing|sales|promotional|commercial)\s+(?:emails?|inquiries|messages?|pitches)",
    r"strictly\s+no\s+(?:sales|recruiters|marketing|cold\s+calls?|cold\s+emails?)",
    r"no\s+spam\b",
    r"do\s+not\s+contact\s+(?:us\s+)?for\s+(?:marketing|commercial|advertising)",
    r"please\s+do\s+not\s+solicit",
    r"no\s+solicitation\b",
    r"we\s+do\s+not\s+accept\s+unsolicited",

    # German
    r"keine\s+werbung\b",
    r"keine\s+unaufgeforderte\s+werbung\b",
    r"keine\s+akquise\b",
    r"werbung\s+verboten\b",
    r"widerspruch\s+(?:gegen\s+)?werbung\b",
    r"keine\s+werbe-?\s*emails?\b",

    # French
    r"pas\s+de\s+démarchage\b",
    r"aucun\s+démarchage\b",
    r"pas\s+de\s+publicité\b",
    r"interdiction\s+de\s+démarchage\b",
    r"refus\s+de\s+toute\s+prospection\b",

    # Spanish
    r"no\s+se\s+admite\s+publicidad\b",
    r"prohibido\s+spam\b",
    r"no\s+publicidad\b",
    r"prohibido\s+el\s+env[íi]o\s+de\s+publicidad\b",
    r"no\s+deseamos\s+recibir\s+publicidad\b",

    # Italian
    r"no\s+pubblicit[àa]\b",
    r"divieto\s+di\s+pubblicit[àa]\b",
    r"non\s+accettiamo\s+pubblicit[àa]\b",
    r"vietata\s+la\s+pubblicit[àa]\b"
]

COMPILED_NEGATIVE_REGEX = re.compile(
    "|".join(f"(?:{p})" for p in NEGATIVE_DISCLAIMER_PATTERNS),
    re.IGNORECASE
)


def detect_negative_disclaimer(text: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Scans text for statements explicitly refusing unsolicited marketing or commercial inquiries.
    
    Returns:
        (has_disclaimer: bool, matched_phrase: Optional[str])
    """
    if not text or not isinstance(text, str):
        return False, None
    
    match = COMPILED_NEGATIVE_REGEX.search(text)
    if match:
        return True, match.group(0).strip()
    return False, None


def contains_prohibited_contact_notice(
    page_text: Optional[str] = None,
    contact_page_text: Optional[str] = None,
    evidence_snippets: Optional[List[str]] = None
) -> Tuple[bool, Optional[str]]:
    """
    Checks multiple content sources for any explicit anti-marketing notices.
    """
    if page_text:
        has_disc, phrase = detect_negative_disclaimer(page_text)
        if has_disc:
            return True, phrase

    if contact_page_text:
        has_disc, phrase = detect_negative_disclaimer(contact_page_text)
        if has_disc:
            return True, phrase

    if evidence_snippets:
        for snippet in evidence_snippets:
            has_disc, phrase = detect_negative_disclaimer(snippet)
            if has_disc:
                return True, phrase

    return False, None
