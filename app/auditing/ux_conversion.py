import re
from typing import List, Dict, Any, Tuple
from app.auditing.crawler import CrawlResult
from app.database.models import AuditSeverity

class UxConversionAuditor:
    """
    Audits UX & Conversion Rate Optimization (CRO) signals:
    - Primary CTA visibility (Call to action buttons / links)
    - Click-to-call telephone accessibility (`tel:` links)
    - Above-the-fold hero CTA presence
    - Lead capture / booking form presence
    - Trust proof (customer reviews, star ratings, certifications, testimonials)
    """
    def audit(self, crawl: CrawlResult) -> Tuple[float, List[Dict[str, Any]], Dict[str, Any]]:
        findings = []
        deductions = 0.0
        soup = crawl.soup
        text_content = soup.get_text().lower()

        # 1. Click-to-call telephone link
        tel_links = soup.find_all("a", href=re.compile(r"^tel:", re.IGNORECASE))
        has_phone_text = bool(re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text_content))
        
        if not tel_links:
            deductions += 20.0
            findings.append({
                "category": "UX & Conversion",
                "finding": "Missing Click-to-Call Phone Action",
                "severity": AuditSeverity.HIGH.value,
                "evidence": "Phone number found as static text or missing entirely without an active `tel:` href link.",
                "recommended_fix": "Wrap phone numbers in `<a href='tel:+1...'>` for one-tap mobile calling.",
                "estimated_business_impact": "Causes 30%+ mobile visitor friction when attempting direct telephone inquiries.",
                "confidence": 0.95
            })

        # 2. Prominent Call to Action (CTA)
        cta_keywords = ["book", "schedule", "quote", "contact", "call now", "free estimate", "consultation", "get started"]
        all_buttons_and_links = soup.find_all(["button", "a"])
        has_prominent_cta = False
        hero_cta = False

        for elem in all_buttons_and_links:
            t = elem.get_text(strip=True).lower()
            if any(kw in t for kw in cta_keywords):
                has_prominent_cta = True
                # Check if it's within header or hero section
                parent_classes = " ".join(elem.find_parent().get("class", []) if elem.find_parent() else [])
                if any(x in parent_classes.lower() for x in ["hero", "header", "top", "banner"]):
                    hero_cta = True

        if not has_prominent_cta:
            deductions += 25.0
            findings.append({
                "category": "UX & Conversion",
                "finding": "No Clear Primary Call-to-Action (CTA)",
                "severity": AuditSeverity.CRITICAL.value,
                "evidence": "No primary actionable buttons (e.g., 'Get a Quote', 'Book Now', 'Schedule Call') identified.",
                "recommended_fix": "Add a prominent, contrasting CTA button prominently in header navigation and hero banner.",
                "estimated_business_impact": "Visitors leave without taking commercial action due to unclear next steps.",
                "confidence": 0.94
            })
        elif not hero_cta:
            deductions += 10.0
            findings.append({
                "category": "UX & Conversion",
                "finding": "Above-the-Fold CTA Missing in Hero",
                "severity": AuditSeverity.MEDIUM.value,
                "evidence": "CTA requires scrolling down before becoming visible to the user.",
                "recommended_fix": "Position the primary inquiry/estimate CTA above the fold on mobile and desktop viewports.",
                "estimated_business_impact": "Sub-optimal conversion rate on first screen impression.",
                "confidence": 0.88
            })

        # 3. Trust Signals & Social Proof
        trust_terms = ["reviews", "rating", "licensed", "insured", "certified", "testimonials", "guarantee", "5-star", "google reviews"]
        trust_count = sum(1 for t in trust_terms if t in text_content)
        if trust_count < 2:
            deductions += 15.0
            findings.append({
                "category": "UX & Conversion",
                "finding": "Weak Social Proof & Trust Badges",
                "severity": AuditSeverity.MEDIUM.value,
                "evidence": "Lacks prominent customer testimonials, licensing badges, or Google review rating widgets.",
                "recommended_fix": "Display verified customer reviews, average star rating badge, and license/bonding credentials.",
                "estimated_business_impact": "Lower visitor confidence compared to competitors featuring reviews prominently.",
                "confidence": 0.90
            })

        # 4. Lead capture / contact form
        forms = soup.find_all("form")
        if not forms:
            deductions += 15.0
            findings.append({
                "category": "UX & Conversion",
                "finding": "Missing Direct Lead Capture Form",
                "severity": AuditSeverity.HIGH.value,
                "evidence": "No lead inquiry or contact form detected on the primary landing page.",
                "recommended_fix": "Embed a streamlined 3-field contact/estimate form ('Name', 'Phone', 'Service Needed').",
                "estimated_business_impact": "Direct friction for users preferring asynchronous web inquiry over phone calls.",
                "confidence": 0.95
            })

        score = max(10.0, round(100.0 - deductions, 1))
        metrics = {
            "has_tel_link": bool(tel_links),
            "has_prominent_cta": has_prominent_cta,
            "has_hero_cta": hero_cta,
            "trust_indicators_count": trust_count,
            "has_lead_form": bool(forms)
        }
        return score, findings, metrics

ux_conversion_auditor = UxConversionAuditor()
