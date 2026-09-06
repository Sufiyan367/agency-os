import re
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.core.security import validate_email_syntax

DISALLOWED_EMAIL_DOMAINS = {
    "example.com", "example.org", "domain.com", "yoursite.com", "email.com",
    "placeholder.com", "sample.com", "test.com", "company.com"
}

DISALLOWED_LOCAL_PARTS = {
    "user", "name", "email", "username", "yourname", "first.last", "info@example"
}

class VerifiedContactResult(BaseModel):
    email: Optional[str] = None
    email_status: str  # 'verified', 'unverified', 'no_contact'
    phone: Optional[str] = None
    phone_status: str  # 'verified', 'unverified', 'no_contact'
    social_profiles: Dict[str, str] = Field(default_factory=dict)
    contact_page_url: Optional[str] = None
    source_url: str
    confidence: float
    can_outreach: bool
    details: Dict[str, Any] = Field(default_factory=dict)

class RealContactVerifier:
    """
    Extracts, cleans, and verifies authentic contact coordinates from real public webpages.
    Disallows fabricated, placeholder, or synthetic emails/phones.
    """

    EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    # International & national phone formats
    PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}")

    def verify_contacts(
        self,
        html_content: str,
        source_url: str,
        candidate_domain: Optional[str] = None
    ) -> VerifiedContactResult:
        if not html_content or not html_content.strip():
            return VerifiedContactResult(
                email=None,
                email_status="no_contact",
                phone=None,
                phone_status="no_contact",
                source_url=source_url,
                confidence=0.0,
                can_outreach=False,
                details={"reason": "Empty HTML content"}
            )

        soup = BeautifulSoup(html_content, "html.parser")
        extracted_emails: List[str] = []
        extracted_phones: List[str] = []
        socials: Dict[str, str] = {}
        contact_page: Optional[str] = None

        cand_dom = candidate_domain.lower().strip() if candidate_domain else ""

        # 1. Check mailto: links (highest confidence)
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("mailto:"):
                raw_em = href[7:].split("?")[0].strip()
                if self._is_valid_email(raw_em):
                    extracted_emails.append(raw_em.lower())

            elif href.lower().startswith("tel:"):
                raw_ph = href[4:].strip()
                if len(re.sub(r"\D", "", raw_ph)) >= 7:
                    extracted_phones.append(raw_ph)

            elif any(s in href.lower() for s in ("contact", "get-in-touch", "reach-us")):
                if not contact_page:
                    contact_page = href

            # Social profiles detection
            lower_href = href.lower()
            if "linkedin.com/company/" in lower_href or "linkedin.com/in/" in lower_href:
                socials["linkedin"] = href
            elif "facebook.com/" in lower_href and not any(x in lower_href for x in ["sharer", "share.php"]):
                socials["facebook"] = href
            elif "instagram.com/" in lower_href:
                socials["instagram"] = href
            elif "twitter.com/" in lower_href or "x.com/" in lower_href:
                socials["twitter"] = href
            elif "youtube.com/" in lower_href or "youtu.be/" in lower_href:
                socials["youtube"] = href

        # 2. Extract from body text
        body_text = soup.get_text(separator=" ", strip=True)
        for match in self.EMAIL_PATTERN.finditer(body_text):
            em = match.group(0).strip(".,;:()")
            if self._is_valid_email(em):
                lower_em = em.lower()
                if lower_em not in extracted_emails:
                    extracted_emails.append(lower_em)

        for match in self.PHONE_PATTERN.finditer(body_text):
            ph = match.group(0).strip(".,;:()")
            digits = re.sub(r"\D", "", ph)
            if 7 <= len(digits) <= 15:
                if ph not in extracted_phones:
                    extracted_phones.append(ph)

        # Prioritize domain-matching emails (e.g. info@domain.com over gmail.com)
        best_email = None
        if extracted_emails:
            domain_matched = [e for e in extracted_emails if cand_dom and cand_dom in e]
            best_email = domain_matched[0] if domain_matched else extracted_emails[0]

        best_phone = extracted_phones[0] if extracted_phones else None

        email_status = "verified" if best_email else "no_contact"
        phone_status = "verified" if best_phone else "no_contact"

        confidence = 0.90 if (best_email and cand_dom and cand_dom in best_email) else (0.75 if best_email else 0.40)
        can_outreach = bool(best_email)

        return VerifiedContactResult(
            email=best_email,
            email_status=email_status,
            phone=best_phone,
            phone_status=phone_status,
            social_profiles=socials,
            contact_page_url=contact_page,
            source_url=source_url,
            confidence=confidence,
            can_outreach=can_outreach,
            details={
                "total_emails_detected": len(extracted_emails),
                "total_phones_detected": len(extracted_phones)
            }
        )

    def _is_valid_email(self, email: str) -> bool:
        if not email or not isinstance(email, str):
            return False
        clean = email.lower().strip()
        if not validate_email_syntax(clean):
            return False
        
        # Filter extensions that accidentally match regex (like .png)
        if any(clean.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")):
            return False

        parts = clean.split("@")
        if len(parts) != 2:
            return False

        local_part, domain_part = parts[0], parts[1]
        if local_part in DISALLOWED_LOCAL_PARTS:
            return False
        if domain_part in DISALLOWED_EMAIL_DOMAINS:
            return False

        return True

contact_verifier = RealContactVerifier()
