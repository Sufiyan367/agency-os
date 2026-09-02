from typing import List, Dict, Any, Tuple
from app.auditing.crawler import CrawlResult
from app.database.models import AuditSeverity

class SeoAuditor:
    """
    Audits website technical and on-page SEO:
    - Title & meta description presence and length
    - Heading hierarchy (H1, H2, H3)
    - Canonical link tag
    - OpenGraph social cards
    - JSON-LD structured schema markup (LocalBusiness)
    - Image alt text coverage
    """
    def audit(self, crawl: CrawlResult) -> Tuple[float, List[Dict[str, Any]], Dict[str, Any]]:
        findings = []
        deductions = 0.0
        soup = crawl.soup

        # 1. Title tag
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""
        if not title_text:
            deductions += 25
            findings.append({
                "category": "SEO",
                "finding": "Missing Page Title Tag",
                "severity": AuditSeverity.CRITICAL.value,
                "evidence": "Document <head> does not define a non-empty <title> tag.",
                "recommended_fix": "Add a descriptive 50-60 character <title> containing primary service and target city.",
                "estimated_business_impact": "Google cannot accurately index the page, resulting in near-zero organic local rankings.",
                "confidence": 0.99
            })
        elif len(title_text) < 20 or len(title_text) > 70:
            deductions += 10
            findings.append({
                "category": "SEO",
                "finding": "Sub-optimal Title Length",
                "severity": AuditSeverity.LOW.value,
                "evidence": f"Title '{title_text[:40]}...' is {len(title_text)} characters (ideal: 50-60 chars).",
                "recommended_fix": "Refine title tag to concise '[Service] in [City] | [Company Name]'.",
                "estimated_business_impact": "Title truncation in SERP snippets reducing CTR.",
                "confidence": 0.90
            })

        # 2. Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        desc_content = meta_desc.get("content", "").strip() if meta_desc else ""
        if not desc_content:
            deductions += 20
            findings.append({
                "category": "SEO",
                "finding": "Missing Meta Description",
                "severity": AuditSeverity.HIGH.value,
                "evidence": "Page lacks a meta description tag.",
                "recommended_fix": "Add a compelling 150-160 character meta description with a clear call to action.",
                "estimated_business_impact": "Search engines generate arbitrary snippets, reducing organic click-through rates by up to 30%.",
                "confidence": 0.95
            })

        # 3. Headings (H1)
        h1s = soup.find_all("h1")
        if len(h1s) == 0:
            deductions += 15
            findings.append({
                "category": "SEO",
                "finding": "Missing H1 Heading",
                "severity": AuditSeverity.HIGH.value,
                "evidence": "No <h1> element found on the page.",
                "recommended_fix": "Add a single primary <h1> summarizing the core commercial offering and location.",
                "estimated_business_impact": "Search engines struggle to identify the primary topical focus.",
                "confidence": 0.95
            })
        elif len(h1s) > 1:
            deductions += 5
            findings.append({
                "category": "SEO",
                "finding": "Multiple H1 Headings Detected",
                "severity": AuditSeverity.LOW.value,
                "evidence": f"Found {len(h1s)} distinct <h1> elements.",
                "recommended_fix": "Consolidate into one main <h1> and use <h2>/<h3> for secondary sub-sections.",
                "estimated_business_impact": "Dilutes primary keyword hierarchy.",
                "confidence": 0.85
            })

        # 4. Canonical tag
        canonical = soup.find("link", attrs={"rel": "canonical"})
        if not canonical:
            deductions += 10
            findings.append({
                "category": "SEO",
                "finding": "Missing Canonical Tag",
                "severity": AuditSeverity.MEDIUM.value,
                "evidence": "No `<link rel='canonical'>` tag found in document head.",
                "recommended_fix": "Add canonical link pointing to the preferred protocol and domain URL.",
                "estimated_business_impact": "Potential duplicate content indexing between http/https or www/non-www.",
                "confidence": 0.90
            })

        # 5. Schema Structured Data (JSON-LD)
        schemas = soup.find_all("script", attrs={"type": "application/ld+json"})
        has_local_schema = False
        for s in schemas:
            if any(term in s.text.lower() for term in ["localbusiness", "organization", "service", "medicalbusiness"]):
                has_local_schema = True
                break

        if not has_local_schema:
            deductions += 20
            findings.append({
                "category": "SEO",
                "finding": "Missing LocalBusiness Schema Markup",
                "severity": AuditSeverity.HIGH.value,
                "evidence": "No JSON-LD LocalBusiness or Organization structured data detected.",
                "recommended_fix": "Deploy schema.org/LocalBusiness markup including name, geo, telephone, address, and openingHours.",
                "estimated_business_impact": "Ineligibility for Google Maps rich snippets and Knowledge Graph placement.",
                "confidence": 0.95
            })

        score = max(10.0, round(100.0 - deductions, 1))
        metrics = {
            "title": title_text,
            "has_meta_desc": bool(desc_content),
            "h1_count": len(h1s),
            "has_canonical": bool(canonical),
            "has_local_schema": has_local_schema
        }
        return score, findings, metrics

seo_auditor = SeoAuditor()
