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

        # 2. Extract top evidence observation
        top_facts = [f for f in facts if f.category in ("conversion", "speed", "seo", "booking")]
        if top_facts:
            primary_fact = top_facts[0]
            observation_1 = f"While reviewing {prospect.website}, I noticed {primary_fact.fact.lower().rstrip('.')}."
            observation_2 = f"I was recently reviewing {prospect.website} and noted {primary_fact.fact.lower().rstrip('.')}."
            observation_3 = f"I wanted to share a brief operational observation regarding {prospect.website}: {primary_fact.fact.lower().rstrip('.')}."
        else:
            observation_1 = f"While reviewing {prospect.website}, I looked at how inquiries are currently handled."
            observation_2 = f"I was recently looking at {prospect.website} and noticed your current contact pathway."
            observation_3 = f"I wanted to share a brief observation regarding customer inquiry flow on {prospect.website}."

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
