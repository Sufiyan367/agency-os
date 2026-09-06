from typing import Dict, Any, List, Optional

class ProspectRanker:
    """
    Multi-objective prospect prioritization engine.
    Ranks prospects by balancing expected revenue, lead quality, contactability,
    service fit, and audit severity—preventing low-probability high-dollar traps.
    """

    WEIGHTS = {
        "expected_revenue": 0.30,
        "lead_quality": 0.25,
        "contactability": 0.20,
        "service_fit": 0.15,
        "audit_severity": 0.10
    }

    def compute_ranking_score(
        self,
        expected_revenue: float,
        lead_quality: float,
        contactability: float,
        service_fit: float,
        audit_severity: float
    ) -> float:
        """
        Computes a balanced multi-criteria score (0-100).
        """
        # Normalize expected revenue against a $1,000 top benchmark
        norm_rev = min(100.0, max(0.0, (expected_revenue / 1000.0) * 100.0))
        
        score = (
            (norm_rev * self.WEIGHTS["expected_revenue"]) +
            (min(100.0, max(0.0, lead_quality)) * self.WEIGHTS["lead_quality"]) +
            (min(100.0, max(0.0, contactability)) * self.WEIGHTS["contactability"]) +
            (min(100.0, max(0.0, service_fit)) * self.WEIGHTS["service_fit"]) +
            (min(100.0, max(0.0, audit_severity)) * self.WEIGHTS["audit_severity"])
        )
        return round(min(100.0, max(0.0, score)), 2)

    def generate_explanation(
        self,
        rank: int,
        composite_score: float,
        expected_revenue: float,
        lead_quality: float,
        contactability: float,
        service_fit: float,
        audit_severity: float
    ) -> str:
        """
        Generates a human-readable explanation for why the prospect received this ranking.
        """
        highlights = []
        if expected_revenue >= 450.0:
            highlights.append(f"high expected revenue (${expected_revenue:.2f})")
        elif expected_revenue >= 250.0:
            highlights.append(f"healthy expected revenue (${expected_revenue:.2f})")

        if contactability >= 85.0:
            highlights.append("verified direct contactability")
        elif contactability < 50.0:
            highlights.append("limited contact reach")

        if lead_quality >= 75.0:
            highlights.append(f"high remediation upside (Quality: {lead_quality:.1f})")

        if audit_severity >= 60.0:
            highlights.append("severe diagnostic deficits")

        if service_fit >= 75.0:
            highlights.append("strong niche service fit")

        highlight_str = ", ".join(highlights) if highlights else "moderate baseline metrics across all categories"
        return f"Rank #{rank} (Score: {composite_score}/100) — Driven by {highlight_str}."

    def rank_prospects(
        self,
        prospects: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Ranks a list of candidate prospects deterministically.
        Ensures ranking is not based solely on expected revenue.
        """
        scored_prospects = []

        for p in prospects:
            rev = float(p.get("expected_revenue", 0.0))
            quality = float(p.get("lead_quality", p.get("quality_score", 50.0)))
            contact = float(p.get("contactability", p.get("contactability_score", 50.0)))
            fit = float(p.get("service_fit", p.get("service_fit_score", 50.0)))
            
            # Severity can come from findings count or audit severity metric
            if "audit_severity" in p:
                severity = float(p["audit_severity"])
            else:
                crit = float(p.get("critical_findings_count", 0.0))
                high = float(p.get("high_findings_count", 0.0))
                severity = min(100.0, (crit * 35.0) + (high * 15.0))

            comp_score = self.compute_ranking_score(
                expected_revenue=rev,
                lead_quality=quality,
                contactability=contact,
                service_fit=fit,
                audit_severity=severity
            )

            scored_prospects.append({
                **p,
                "composite_score": comp_score,
                "expected_revenue": rev,
                "lead_quality": quality,
                "contactability": contact,
                "service_fit": fit,
                "audit_severity": severity
            })

        # Stable deterministic tie-breaker:
        # Sort by composite_score desc, quality desc, contactability desc, then business_id or domain
        scored_prospects.sort(
            key=lambda x: (
                -x["composite_score"],
                -x["lead_quality"],
                -x["contactability"],
                -x["expected_revenue"],
                str(x.get("business_id", x.get("id", "")))
            )
        )

        # Assign ranks and explanations
        ranked = []
        for idx, item in enumerate(scored_prospects, start=1):
            explanation = self.generate_explanation(
                rank=idx,
                composite_score=item["composite_score"],
                expected_revenue=item["expected_revenue"],
                lead_quality=item["lead_quality"],
                contactability=item["contactability"],
                service_fit=item["service_fit"],
                audit_severity=item["audit_severity"]
            )
            item["rank"] = idx
            item["ranking_explanation"] = explanation
            ranked.append(item)

        return ranked

prospect_ranker = ProspectRanker()
