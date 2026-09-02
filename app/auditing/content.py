from typing import List, Dict, Any, Tuple
from app.auditing.crawler import CrawlResult
from app.database.models import AuditSeverity

class ContentAuditor:
    """
    Audits website content depth and commercial architecture:
    - Homepage body word count / thin content
    - Service page architecture (presence of dedicated service links)
    - Location page architecture (presence of local landing pages)
    """
    def audit(self, crawl: CrawlResult) -> Tuple[float, List[Dict[str, Any]], Dict[str, Any]]:
        findings = []
        deductions = 0.0
        soup = crawl.soup

        # 1. Word count / Thin content
        body_text = " ".join(soup.stripped_strings)
        word_count = len(body_text.split())

        if word_count < 150:
            deductions += 30.0
            findings.append({
                "category": "Content",
                "finding": "Thin Homepage Content (< 150 words)",
                "severity": AuditSeverity.HIGH.value,
                "evidence": f"Total page body contains only {word_count} words.",
                "recommended_fix": "Expand homepage copy with detailed descriptions of core services, process, and client benefits.",
                "estimated_business_impact": "Google treats thin pages as low value, severely limiting search impression share.",
                "confidence": 0.95
            })
        elif word_count < 350:
            deductions += 15.0
            findings.append({
                "category": "Content",
                "finding": "Sub-optimal Content Depth",
                "severity": AuditSeverity.MEDIUM.value,
                "evidence": f"Total page body contains {word_count} words (recommended minimum: 500 words).",
                "recommended_fix": "Add dedicated sections detailing service differentiators, FAQ, and scope.",
                "estimated_business_impact": "Limits long-tail topical relevance for search crawlers.",
                "confidence": 0.90
            })

        # 2. Service page architecture
        links = soup.find_all("a", href=True)
        service_links = [a for a in links if any(k in a.get("href", "").lower() for k in ["/service", "/what-we-do", "/commercial", "/residential"])]
        if not service_links:
            deductions += 20.0
            findings.append({
                "category": "Content",
                "finding": "Missing Dedicated Service Sub-pages",
                "severity": AuditSeverity.HIGH.value,
                "evidence": "No links pointing to distinct dedicated service pages detected in navigation.",
                "recommended_fix": "Create standalone URLs for each specialized service (e.g. /commercial-roofing, /emergency-repair).",
                "estimated_business_impact": "Prevents ranking for high-intent specific service queries.",
                "confidence": 0.92
            })

        # 3. Location / Service Area architecture
        location_links = [a for a in links if any(k in a.get("href", "").lower() for k in ["/area", "/location", "/cities", "/service-area"])]
        if not location_links:
            deductions += 10.0
            findings.append({
                "category": "Content",
                "finding": "Missing City / Geographic Service Area Pages",
                "severity": AuditSeverity.MEDIUM.value,
                "evidence": "No regional landing page links found (e.g. /service-areas/north-austin).",
                "recommended_fix": "Develop targeted city/suburb landing pages to dominate neighboring regional search queries.",
                "estimated_business_impact": "Loses local search traffic from adjacent towns and metropolitan suburbs.",
                "confidence": 0.88
            })

        score = max(15.0, round(100.0 - deductions, 1))
        metrics = {
            "word_count": word_count,
            "service_links_count": len(service_links),
            "location_links_count": len(location_links)
        }
        return score, findings, metrics

content_auditor = ContentAuditor()
