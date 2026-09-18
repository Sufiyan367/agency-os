"""
Agency OS — Client Automation Lead Qualification Engine.

Evaluates prospect responses against client-configured criteria,
assigning a normalized 0-100 qualification score and determining
advancement to appointment booking or graceful disqualification.
Enforces client-isolated criteria without mutating core agency scoring.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Any, Tuple

from app.client_automation.brain import shared_brain_manager
from app.client_automation.models import LeadRecord, LeadStage, QualificationRule

logger = logging.getLogger("agency.client_automation.qualification")


class QualificationResult:
    def __init__(
        self,
        lead_id: str,
        client_id: str,
        is_qualified: bool,
        score: float,
        passed_rules: List[str],
        failed_rules: List[str],
        notes: str = ""
    ):
        self.lead_id = lead_id
        self.client_id = client_id
        self.is_qualified = is_qualified
        self.score = score
        self.passed_rules = passed_rules
        self.failed_rules = failed_rules
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "client_id": self.client_id,
            "is_qualified": self.is_qualified,
            "score": round(self.score, 1),
            "passed_rules": self.passed_rules,
            "failed_rules": self.failed_rules,
            "notes": self.notes,
        }


class ClientLeadQualifier:
    """
    Evaluates client-specific qualification questions and requirements.
    """

    QUALIFICATION_SCORE_THRESHOLD = 60.0

    @classmethod
    async def evaluate_lead(
        cls,
        client_id: str,
        lead_id: str,
        answers: Dict[str, Any]
    ) -> QualificationResult:
        """
        Evaluates a lead's answers against the client's configured qualification rules.
        """
        brain = shared_brain_manager.get_brain(client_id)
        if not brain:
            return QualificationResult(
                lead_id=lead_id,
                client_id=client_id,
                is_qualified=False,
                score=0.0,
                passed_rules=[],
                failed_rules=["Client brain not registered"],
                notes="Client configuration missing.",
            )

        config = brain.config
        rules: List[QualificationRule] = config.qualification_rules

        # If no specific rules configured, default qualification: has name & contact info
        if not rules:
            has_contact = bool(answers.get("phone") or answers.get("email") or answers.get("contact"))
            score = 75.0 if has_contact else 40.0
            is_qualified = score >= cls.QUALIFICATION_SCORE_THRESHOLD

            lead = brain.get_lead(lead_id)
            if lead:
                lead.score = score
                lead.qualification_answers.update(answers)
                lead.stage = LeadStage.QUALIFIED if is_qualified else LeadStage.INQUIRY
                brain.upsert_lead(lead)

            return QualificationResult(
                lead_id=lead_id,
                client_id=client_id,
                is_qualified=is_qualified,
                score=score,
                passed_rules=["default_contact_present"] if has_contact else [],
                failed_rules=[] if has_contact else ["missing_contact_info"],
                notes="Evaluated via default contact completeness.",
            )

        total_weight = 0.0
        earned_weight = 0.0
        passed: List[str] = []
        failed: List[str] = []

        for rule in rules:
            total_weight += rule.weight
            val = answers.get(rule.key)

            if val is None:
                if rule.required:
                    failed.append(f"{rule.key} (missing required answer)")
                continue

            # Type and constraint checks
            passed_rule = True
            if rule.expected_type == "number":
                try:
                    num_val = float(val)
                    if rule.min_value is not None and num_val < rule.min_value:
                        passed_rule = False
                        failed.append(f"{rule.key} (value {num_val} < min {rule.min_value})")
                except (ValueError, TypeError):
                    passed_rule = False
                    failed.append(f"{rule.key} (expected numeric value)")

            elif rule.expected_type == "choice" and rule.allowed_values:
                str_val = str(val).strip().lower()
                allowed_lower = [str(x).strip().lower() for x in rule.allowed_values]
                if str_val not in allowed_lower:
                    passed_rule = False
                    failed.append(f"{rule.key} (value '{val}' not in allowed choices)")

            elif rule.expected_type == "boolean":
                if not bool(val):
                    passed_rule = False
                    failed.append(f"{rule.key} (condition not met)")

            if passed_rule:
                earned_weight += rule.weight
                passed.append(rule.key)

        score = (earned_weight / total_weight * 100.0) if total_weight > 0 else 50.0
        is_qualified = score >= cls.QUALIFICATION_SCORE_THRESHOLD and len(failed) == 0

        # Update Lead Record in Brain
        lead = brain.get_lead(lead_id)
        if lead:
            lead.score = score
            lead.qualification_answers.update(answers)
            lead.stage = LeadStage.QUALIFIED if is_qualified else LeadStage.INQUIRY
            brain.upsert_lead(lead)

        return QualificationResult(
            lead_id=lead_id,
            client_id=client_id,
            is_qualified=is_qualified,
            score=score,
            passed_rules=passed,
            failed_rules=failed,
            notes=f"Scored {score:.1f}/100 based on {len(rules)} client criteria.",
        )


client_lead_qualifier = ClientLeadQualifier()
