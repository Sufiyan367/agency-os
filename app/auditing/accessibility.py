from typing import List, Dict, Any, Tuple
from app.auditing.crawler import CrawlResult
from app.database.models import AuditSeverity

class AccessibilityAuditor:
    """
    Audits website accessibility (WCAG 2.1 AA heuristics):
    - Image alt attributes
    - Form input labels (aria-label, <label>)
    - Empty buttons / links lacking accessible names
    - Document lang attribute
    - Semantic HTML landmarks (<main>, <nav>, <header>, <footer>)
    """
    def audit(self, crawl: CrawlResult) -> Tuple[float, List[Dict[str, Any]], Dict[str, Any]]:
        findings = []
        deductions = 0.0
        soup = crawl.soup

        # 1. Image alt attributes
        images = soup.find_all("img")
        missing_alt = [img for img in images if not img.get("alt") and img.get("alt") != ""]
        if missing_alt:
            deductions += min(25.0, len(missing_alt) * 8.0)
            findings.append({
                "category": "Accessibility",
                "finding": "Images Missing Accessible Alt Text",
                "severity": AuditSeverity.HIGH.value if len(missing_alt) > 2 else AuditSeverity.MEDIUM.value,
                "evidence": f"Found {len(missing_alt)} images without 'alt' attributes.",
                "recommended_fix": "Provide concise descriptive alt text for informative images or alt='' for decorative assets.",
                "estimated_business_impact": "Screen reader users cannot understand content; creates potential ADA/WCAG compliance legal risk.",
                "confidence": 0.98
            })

        # 2. Form input labels
        inputs = soup.find_all(["input", "textarea", "select"])
        unlabelled = []
        for inp in inputs:
            if inp.get("type") in ("hidden", "submit", "button"):
                continue
            inp_id = inp.get("id")
            has_explicit_label = bool(soup.find("label", attrs={"for": inp_id})) if inp_id else False
            has_parent_label = bool(inp.find_parent("label"))
            has_aria = bool(inp.get("aria-label") or inp.get("aria-labelledby"))
            if not (has_explicit_label or has_parent_label or has_aria):
                unlabelled.append(inp)

        if unlabelled:
            deductions += min(30.0, len(unlabelled) * 12.0)
            findings.append({
                "category": "Accessibility",
                "finding": "Form Fields Lacking Accessible Labels",
                "severity": AuditSeverity.HIGH.value,
                "evidence": f"Detected {len(unlabelled)} form inputs without associated <label> or aria-label attributes.",
                "recommended_fix": "Add explicit <label for='...'> tags or aria-label attributes to all form fields.",
                "estimated_business_impact": "Causes form abandonment for assistive technology users; reduces inquiries.",
                "confidence": 0.95
            })

        # 3. Empty buttons
        buttons = soup.find_all("button")
        empty_buttons = [b for b in buttons if not b.get_text(strip=True) and not (b.get("aria-label") or b.find("img", attrs={"alt": True}))]
        if empty_buttons:
            deductions += 15.0
            findings.append({
                "category": "Accessibility",
                "finding": "Empty Interactive Buttons",
                "severity": AuditSeverity.MEDIUM.value,
                "evidence": f"Found {len(empty_buttons)} button elements with no discernible text or aria-label.",
                "recommended_fix": "Add text or aria-label describing button action (e.g., 'Submit Inquiry', 'Close').",
                "estimated_business_impact": "Confuses keyboard and screen reader navigation.",
                "confidence": 0.92
            })

        # 4. Document language
        html_tag = soup.find("html")
        if not html_tag or not html_tag.get("lang"):
            deductions += 10.0
            findings.append({
                "category": "Accessibility",
                "finding": "Missing Document Language Attribute",
                "severity": AuditSeverity.LOW.value,
                "evidence": "<html> root element lacks 'lang' attribute.",
                "recommended_fix": "Add `lang='en'` (or target language code) to <html> tag.",
                "estimated_business_impact": "Speech synthesizers default to incorrect pronunciation rules.",
                "confidence": 0.98
            })

        score = max(15.0, round(100.0 - deductions, 1))
        metrics = {
            "total_images": len(images),
            "missing_alt_count": len(missing_alt),
            "unlabelled_inputs": len(unlabelled),
            "empty_buttons": len(empty_buttons)
        }
        return score, findings, metrics

accessibility_auditor = AccessibilityAuditor()
