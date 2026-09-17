from typing import List, Dict, Any, Optional
from app.outreach.composer.models import (
    CanonicalProspect, ResearchFact, SenderIdentity, ComplianceProfile, ComposedEmail
)
from app.outreach.composer.solution_catalog import SolutionCatalog, SolutionMatch


class GeneralizedOutreachComposer:
    """
    Composes concise, professional, evidence-grounded B2B outreach emails
    with strict separation of concerns:
    - Prospect identity
    - Factual research
    - Matched solution
    - Sender identity
    - Compliance footer policy
    Target word count: 60–140 words.
    """

    @staticmethod
    def sanitize_untrusted_text(text: str) -> str:
        """Strips control characters, HTML markup, and dangerous prompt injection tokens."""
        import re
        if not text:
            return ""
        cleaned = re.sub(r'[\r\n\t]+', ' ', text)
        cleaned = re.sub(r'<[^>]*>', '', cleaned)
        injection_patterns = [
            r"ignore\s+(?:all\s+)?previous\s+instructions",
            r"system\s+prompt",
            r"you\s+are\s+now\s+a",
            r"new\s+instructions:",
            r"drop\s+table",
            r"eval\s*\(",
            r"curl\s+http",
            r"powershell",
            r"bash\s+-c",
        ]
        for pattern in injection_patterns:
            cleaned = re.sub(pattern, "[FILTERED]", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def compose_variants(
        self,
        prospect: CanonicalProspect,
        facts: List[ResearchFact],
        solution: SolutionMatch,
        sender: SenderIdentity,
        compliance: Optional[ComplianceProfile] = None
    ) -> List[ComposedEmail]:
        compliance = compliance or ComplianceProfile(enabled=False)

        # 1. Greeting resolution
        if prospect.recipient_name and prospect.recipient_name.strip():
            greeting = f"Hi {prospect.recipient_name.strip()},"
        else:
            greeting = f"Hi {prospect.company_name} team,"

        # 2. Extract top evidence observation (Concrete findings preferred over scores)
        concrete_facts = [
            f for f in facts 
            if f.category in ("conversion", "speed", "seo", "booking") 
            and "score measured at" not in f.fact.lower()
        ]
        top_facts = concrete_facts if concrete_facts else [
            f for f in facts if f.category in ("conversion", "speed", "seo", "booking")
        ]

        if top_facts:
            primary_fact = top_facts[0]
            raw_fact = self.sanitize_untrusted_text(primary_fact.fact.strip().rstrip('.'))
            f_lower = raw_fact.lower()
            if f_lower.startswith("missing"):
                obs_detail = f"an opportunity regarding {f_lower}"
            elif f_lower.startswith("no clear"):
                obs_detail = f"{f_lower} on the primary landing page"
            elif "friction" in f_lower or "deficit" in f_lower:
                obs_detail = f"that {f_lower}"
            else:
                obs_detail = f"{f_lower}"

            observation_1 = f"While reviewing {prospect.website}, I noticed {obs_detail}."
            observation_2 = f"I was recently reviewing {prospect.website} and noted {obs_detail}."
            observation_3 = f"I wanted to share a brief operational observation regarding {prospect.website}: {raw_fact}."
        else:
            solution.requires_review = True
            observation_1 = f"While reviewing {prospect.website}, I wanted to share a brief operational observation."
            observation_2 = f"I was recently reviewing {prospect.website} and had an operational inquiry."
            observation_3 = f"I wanted to share a brief inquiry regarding {prospect.website}."

        signature = sender.signature()
        footer = compliance.render_footer()

        # Variant 1: Value-First Insight
        v1_subject = f"Question regarding {prospect.canonical_company_domain}"
        v1_body = (
            f"{greeting}\n\n"
            f"{observation_1}\n\n"
            f"Implementing {solution.solution_statement} can help {solution.expected_outcome}.\n\n"
            f"Would you be open to a quick look at how this would work for {prospect.company_name}?\n\n"
            f"{signature}"
            f"{footer}"
        )

        # Variant 2: Direct Solution
        v2_subject = f"{prospect.company_name} — inquiry flow observation"
        v2_body = (
            f"{greeting}\n\n"
            f"{observation_2}\n\n"
            f"For businesses in the {prospect.industry.lower()} sector, addressing {solution.problem_statement} directly helps {solution.expected_outcome}.\n\n"
            f"We put together {solution.solution_statement} tailored to your current workflow.\n\n"
            f"Are you open to reviewing a brief summary for {prospect.company_name}?\n\n"
            f"{signature}"
            f"{footer}"
        )

        # Variant 3: Executive Observation
        v3_subject = f"Operational note on {prospect.canonical_company_domain}"
        v3_body = (
            f"{greeting}\n\n"
            f"{observation_3}\n\n"
            f"We specialize in {solution.solution_statement} to help {solution.expected_outcome}.\n\n"
            f"Would you be open to a 2-minute walkthrough showing how this applies to {prospect.company_name}?\n\n"
            f"{signature}"
            f"{footer}"
        )

        variants = [
            ("Value-First Insight", v1_subject, v1_body),
            ("Direct Solution", v2_subject, v2_body),
            ("Executive Observation", v3_subject, v3_body)
        ]

        results: List[ComposedEmail] = []
        for name, subj, body in variants:
            word_count = len(body.split())
            results.append(ComposedEmail(
                subject=subj,
                body=body,
                word_count=word_count,
                variant_name=name,
                prospect_id=prospect.prospect_id,
                solution_matched=solution.solution_key
            ))

        return results


generalized_composer = GeneralizedOutreachComposer()
