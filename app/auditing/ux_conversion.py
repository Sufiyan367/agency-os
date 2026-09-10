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

        # 5. Call-Opportunity & Inbound Phone Dependency Diagnostics
        has_published_phone = bool(tel_links) or has_phone_text
        hours_regex = re.compile(
            r"(?:hours|opening hours|working hours|timing|timings|schedule|mon(?:day)?\s*[-–to]\s*(?:fri(?:day)?|sat(?:urday)?|sun(?:day)?)|[0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)\s*[-–to]\s*[0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm))",
            re.IGNORECASE
        )
        has_business_hours = bool(hours_regex.search(text_content))

        # Check for evening/weekend closed indications
        after_hours_gap = has_business_hours and not any(kw in text_content for kw in ["24/7", "open 24 hours", "round the clock", "always open"])

        # Appointment / consultation dependency
        appointment_terms = [
            "appointment", "book appointment", "schedule consultation", "consultation",
            "reserve", "book online", "patient portal", "book your visit", "schedule a visit",
            "request appointment"
        ]
        has_appointment_dep = any(t in text_content for t in appointment_terms)

        # Emergency or urgent service characteristics
        emergency_terms = ["emergency", "urgent care", "urgent service", "24/7", "same day service", "breakdown", "immediate assistance"]
        has_emergency_service = any(t in text_content for t in emergency_terms)

        # High-value service indicators
        high_value_terms = [
            "implant", "veneers", "cosmetic", "surgery", "hvac replacement", "ac installation",
            "transmission", "engine overhaul", "litigation", "legal counsel", "villa", "penthouse",
            "luxury", "retainer"
        ]
        high_value_count = sum(1 for t in high_value_terms if t in text_content)

        # Inbound phone dependency
        phone_action_terms = ["call us", "call today", "call now", "phone:", "telephone", "tel:"]
        phone_mentions = sum(1 for t in phone_action_terms if t in text_content)
        is_phone_driven = has_published_phone and (bool(tel_links) or phone_mentions >= 2 or has_appointment_dep)

        # Calculate Call-Driven Business Score (0-100)
        call_score_raw = 0.0
        if has_published_phone:
            call_score_raw += 25.0
        if bool(tel_links):
            call_score_raw += 15.0
        if has_appointment_dep:
            call_score_raw += 20.0
        if after_hours_gap:
            call_score_raw += 20.0
        if high_value_count > 0:
            call_score_raw += min(10.0, high_value_count * 5.0)
        if has_emergency_service:
            call_score_raw += 10.0
        call_driven_score = min(100.0, round(call_score_raw, 1))

        # Add structured finding for Potential Missed-Call Opportunity when evidence supports it
        if is_phone_driven and (after_hours_gap or has_appointment_dep):
            evidence_parts = []
            if has_published_phone:
                evidence_parts.append("published phone line observed as primary contact")
            if has_business_hours:
                evidence_parts.append("scheduled operational hours observed without 24/7 automated answering")
            if has_appointment_dep:
                evidence_parts.append("service booking relies on direct customer coordination")

            findings.append({
                "category": "UX & Conversion",
                "finding": "Potential After-Hours / Peak Missed-Call Opportunity",
                "severity": AuditSeverity.HIGH.value,
                "evidence": f"Observable operational evidence indicates {', '.join(evidence_parts)}. Inbound calls outside operating hours or during peak staff volume represent potential missed-call opportunities.",
                "recommended_fix": "Implement an autonomous AI Receptionist to answer, qualify, and book incoming calls 24/7 with immediate SMS follow-up.",
                "estimated_business_impact": "Recovers high-intent inbound inquiries during after-hours and peak call periods without additional staffing overhead.",
                "confidence": 0.92
            })

        score = max(10.0, round(100.0 - deductions, 1))
        metrics = {
            "has_tel_link": bool(tel_links),
            "has_prominent_cta": has_prominent_cta,
            "has_hero_cta": hero_cta,
            "trust_indicators_count": trust_count,
            "has_lead_form": bool(forms),
            "call_opportunity": {
                "has_published_phone": has_published_phone,
                "has_tel_link": bool(tel_links),
                "business_hours_detected": has_business_hours,
                "after_hours_gap_detected": after_hours_gap,
                "appointment_dependency": has_appointment_dep,
                "emergency_or_urgent_service": has_emergency_service,
                "high_value_service_signals": high_value_count,
                "phone_inquiry_dependency": is_phone_driven,
                "call_driven_score": call_driven_score
            }
        }
        return score, findings, metrics

ux_conversion_auditor = UxConversionAuditor()
