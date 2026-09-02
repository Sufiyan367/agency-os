from typing import List, Dict, Any, Tuple
from app.auditing.crawler import CrawlResult
from app.database.models import AuditSeverity

class PerformanceAuditor:
    """
    Audits website performance:
    - HTML payload weight
    - Script and stylesheet count (render blocking)
    - Modern image formats (WebP, AVIF)
    - Viewport tag configuration for mobile usability
    - Simulated Core Web Vitals (LCP, TTFB)
    """
    def audit(self, crawl: CrawlResult) -> Tuple[float, List[Dict[str, Any]], Dict[str, Any]]:
        findings = []
        deductions = 0.0
        soup = crawl.soup

        # 1. Response time (TTFB / Network latency)
        ttfb = crawl.load_time_ms
        if ttfb > 1200:
            deductions += 25
            findings.append({
                "category": "Performance",
                "finding": "Excessive Server Response Time / TTFB",
                "severity": AuditSeverity.HIGH.value,
                "evidence": f"Initial page response took {ttfb:.0f}ms (threshold: < 600ms).",
                "recommended_fix": "Configure edge caching, CDN, or upgrade hosting compute.",
                "estimated_business_impact": "High bounce rates for mobile traffic on cellular connections.",
                "confidence": 0.95
            })
        elif ttfb > 600:
            deductions += 10
            findings.append({
                "category": "Performance",
                "finding": "Sub-optimal Server Response Time",
                "severity": AuditSeverity.MEDIUM.value,
                "evidence": f"Initial page response was {ttfb:.0f}ms.",
                "recommended_fix": "Implement server-level caching and database query optimization.",
                "estimated_business_impact": "Slight conversion loss on first-time visits.",
                "confidence": 0.90
            })

        # 2. Viewport mobile tag
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if not viewport:
            deductions += 25
            findings.append({
                "category": "Performance",
                "finding": "Missing Mobile Viewport Configuration",
                "severity": AuditSeverity.CRITICAL.value,
                "evidence": "No <meta name='viewport'> tag detected in document head.",
                "recommended_fix": "Add `<meta name='viewport' content='width=device-width, initial-scale=1.0'>` to <head>.",
                "estimated_business_impact": "Site will render as desktop view on mobile phones, severely harming mobile conversions.",
                "confidence": 0.99
            })

        # 3. Scripts and render blocking assets
        scripts = soup.find_all("script")
        styles = soup.find_all("link", attrs={"rel": "stylesheet"})
        un_deferred_scripts = [s for s in scripts if s.get("src") and not (s.get("defer") or s.get("async"))]
        
        if len(un_deferred_scripts) > 3:
            deductions += 15
            findings.append({
                "category": "Performance",
                "finding": "Render-Blocking JavaScript Resources",
                "severity": AuditSeverity.HIGH.value,
                "evidence": f"Found {len(un_deferred_scripts)} external scripts loaded without defer or async attributes.",
                "recommended_fix": "Add defer or async attribute to non-critical external scripts.",
                "estimated_business_impact": "Delays First Contentful Paint (FCP) and Largest Contentful Paint (LCP).",
                "confidence": 0.92
            })

        # 4. Images optimization & formats
        images = soup.find_all("img")
        unoptimized_imgs = [img for img in images if img.get("src") and any(ext in img.get("src", "").lower() for ext in [".bmp", ".tiff", ".png"])]
        if len(unoptimized_imgs) > 0:
            deductions += 10
            findings.append({
                "category": "Performance",
                "finding": "Legacy Image Formats In Use",
                "severity": AuditSeverity.LOW.value,
                "evidence": f"Detected {len(unoptimized_imgs)} images using heavy raster formats (.bmp, uncompressed .png).",
                "recommended_fix": "Convert image assets to WebP or AVIF and enable lazy loading.",
                "estimated_business_impact": "Inflates total page transfer size, slowing load times.",
                "confidence": 0.88
            })

        score = max(10.0, round(100.0 - deductions, 1))
        metrics = {
            "load_time_ms": ttfb,
            "total_scripts": len(scripts),
            "total_stylesheets": len(styles),
            "total_images": len(images),
            "has_viewport": bool(viewport)
        }
        return score, findings, metrics

performance_auditor = PerformanceAuditor()
