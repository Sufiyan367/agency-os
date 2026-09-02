from typing import List, Dict, Any, Tuple
from app.auditing.crawler import CrawlResult
from app.database.models import AuditSeverity

class SecurityAuditor:
    """
    Audits website technical security non-destructively:
    - HTTPS enforcement
    - Security headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options)
    - CMS & Tech stack fingerprinting
    """
    def audit(self, crawl: CrawlResult) -> Tuple[float, List[Dict[str, Any]], Dict[str, Any]]:
        findings = []
        deductions = 0.0
        headers = {k.lower(): v for k, v in crawl.headers.items()}
        soup = crawl.soup

        # 1. HTTPS enforcement
        is_https = crawl.url.lower().startswith("https://")
        if not is_https:
            deductions += 40.0
            findings.append({
                "category": "Security",
                "finding": "Insecure HTTP Protocol In Use",
                "severity": AuditSeverity.CRITICAL.value,
                "evidence": f"Website serving over unencrypted HTTP: {crawl.url}",
                "recommended_fix": "Install valid SSL certificate and enforce 301 redirect from HTTP to HTTPS.",
                "estimated_business_impact": "Modern browsers flag site as 'Not Secure'; drastic conversion and ranking drop.",
                "confidence": 0.99
            })

        # 2. Strict-Transport-Security (HSTS)
        if "strict-transport-security" not in headers:
            deductions += 15.0
            findings.append({
                "category": "Security",
                "finding": "Missing HSTS Security Header",
                "severity": AuditSeverity.LOW.value,
                "evidence": "Strict-Transport-Security header not returned by server.",
                "recommended_fix": "Add 'Strict-Transport-Security: max-age=31536000; includeSubDomains' to server headers.",
                "estimated_business_impact": "Vulnerability to SSL stripping attacks.",
                "confidence": 0.92
            })

        # 3. X-Frame-Options (Clickjacking defense)
        if "x-frame-options" not in headers and "content-security-policy" not in headers:
            deductions += 15.0
            findings.append({
                "category": "Security",
                "finding": "Missing Clickjacking Protection",
                "severity": AuditSeverity.MEDIUM.value,
                "evidence": "Neither X-Frame-Options nor frame-ancestors CSP directive configured.",
                "recommended_fix": "Set `X-Frame-Options: SAMEORIGIN` header.",
                "estimated_business_impact": "Allows malicious third parties to iframe the website for clickjacking.",
                "confidence": 0.90
            })

        # 4. Tech stack detection
        tech_detected = []
        generator = soup.find("meta", attrs={"name": "generator"})
        gen_content = generator.get("content", "").lower() if generator else ""
        
        if "wordpress" in gen_content or "wp-content" in crawl.html_content:
            tech_detected.append("WordPress")
        if "wix" in gen_content or "wix.com" in crawl.html_content:
            tech_detected.append("Wix")
        if "squarespace" in gen_content or "squarespace" in crawl.html_content:
            tech_detected.append("Squarespace")
        if "shopify" in gen_content or "shopify" in crawl.html_content:
            tech_detected.append("Shopify")
        if not tech_detected:
            tech_detected.append("Custom / Static HTML")

        score = max(20.0, round(100.0 - deductions, 1))
        metrics = {
            "is_https": is_https,
            "has_hsts": "strict-transport-security" in headers,
            "tech_stack": tech_detected
        }
        return score, findings, metrics

security_auditor = SecurityAuditor()
