from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from app.outreach.composer.models import CanonicalProspect, ResearchFact


@dataclass
class SolutionMatch:
    solution_key: str
    title: str
    problem_statement: str
    solution_statement: str
    expected_outcome: str
    confidence: float
    requires_review: bool = False


class SolutionCatalog:
    """
    Determines relevant commercial solutions from audit evidence and business niche.
    Prevents forcing a single solution (e.g. AI Receptionist) on mismatched businesses.
    """

    SOLUTIONS = {
        "conversion_optimization": {
            "title": "Mobile Conversion & Inquiry Engine Optimization",
            "problem_statement": "prospective customers encountering friction on mobile inquiry paths",
            "solution_statement": "a streamlined high-converting mobile inquiry flow",
            "expected_outcome": "capture visitors who currently drop off before contacting you"
        },
        "performance_acceleration": {
            "title": "Speed & Mobile Load Acceleration",
            "problem_statement": "mobile page loading delays slowing down prospective customer engagement",
            "solution_statement": "targeted Core Web Vitals speed optimization",
            "expected_outcome": "reduce load times under 2 seconds and keep high-intent visitors on your site"
        },
        "local_seo_schema": {
            "title": "Local Search Authority & Schema Acceleration",
            "problem_statement": "incomplete local structured data limiting visibility in local map and search results",
            "solution_statement": "complete local business schema deployment and on-page metadata optimization",
            "expected_outcome": "improve discoverability for customers actively searching for your services"
        },
        "workflow_automation": {
            "title": "Automated Lead Routing & Follow-Up System",
            "problem_statement": "manual steps in customer inquiry routing causing delayed responses",
            "solution_statement": "an automated inquiry routing and instant notification workflow",
            "expected_outcome": "respond to incoming leads in minutes instead of hours"
        },
        "missed_call_recovery": {
            "title": "Inbound Call Answering & Lead Recovery System",
            "problem_statement": "unanswered inbound calls during peak hours or after business hours",
            "solution_statement": "an automated 24/7 call answering and instant text-back qualification system",
            "expected_outcome": "recover potential customers who would otherwise contact a competitor"
        }
    }

    @classmethod
    def match_solution(
        cls,
        prospect: CanonicalProspect,
        facts: List[ResearchFact],
        capabilities: Dict[str, bool]
    ) -> SolutionMatch:
        # Score solution candidates based on grounded facts
        scores: Dict[str, float] = {k: 0.1 for k in cls.SOLUTIONS}

        for f in facts:
            cat = f.category
            val = f.metric_value
            if cat == "conversion" and isinstance(val, (int, float)) and val < 70:
                scores["conversion_optimization"] += 0.4
            elif cat == "speed" and isinstance(val, (int, float)) and val < 60:
                scores["performance_acceleration"] += 0.4
            elif cat == "seo" and isinstance(val, (int, float)) and val < 65:
                scores["local_seo_schema"] += 0.4

        # Check call dependency
        if capabilities.get("has_phone_dependency") and not capabilities.get("has_after_hours_flow"):
            scores["missed_call_recovery"] += 0.5

        # Check existing capabilities to downrank contradictory solutions
        if capabilities.get("has_fast_mobile_speed"):
            scores["performance_acceleration"] = 0.0
        if capabilities.get("has_after_hours_flow"):
            scores["missed_call_recovery"] = 0.0
        if capabilities.get("has_strong_seo"):
            scores["local_seo_schema"] = 0.0

        best_key = max(scores, key=scores.get)
        confidence = scores[best_key]

        requires_review = confidence < 0.35

        sol_def = cls.SOLUTIONS[best_key]
        return SolutionMatch(
            solution_key=best_key,
            title=sol_def["title"],
            problem_statement=sol_def["problem_statement"],
            solution_statement=sol_def["solution_statement"],
            expected_outcome=sol_def["expected_outcome"],
            confidence=min(1.0, confidence),
            requires_review=requires_review
        )
