"""
Agency OS — Failure Pattern Learning & Bounded Self-Correction.
Provides structured failure classification, bounded 3-attempt self-repair limits,
escalation to CEO_REQUIRED, and empirical persistence of recurring failure patterns.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.intelligence.knowledge_model import store_failure_pattern, get_facts_for_entity
from app.database.models import KnowledgeFact


class FailureCategory(str, Enum):
    TIMEOUT = "TIMEOUT"
    AUTH_ERROR = "AUTH_ERROR"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    BUILD_DEPENDENCY_ERROR = "BUILD_DEPENDENCY_ERROR"
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"
    CONFIG_ERROR = "CONFIG_ERROR"
    UNKNOWN = "UNKNOWN"


class SelfCorrectionLimitExceeded(Exception):
    """Raised when an operation reaches the maximum allowed repair attempts (3)."""
    pass


class FailureLearningEngine:
    """
    Classifies execution failures, governs bounded self-repair,
    escalates terminal failures to CEO_REQUIRED, and stores recurring failure patterns.
    """

    MAX_REPAIR_ATTEMPTS = 3

    @classmethod
    def classify_failure(cls, error_message: str, error_context: Optional[Dict[str, Any]] = None) -> FailureCategory:
        """
        Classifies raw error messages into deterministic failure categories.
        """
        msg = (error_message or "").lower()
        ctx = str(error_context or "").lower()
        combined = f"{msg} {ctx}"

        if any(w in combined for w in ("timeout", "timed out", "deadline exceeded", "readtimeout", "connecttimeout")):
            return FailureCategory.TIMEOUT
        if any(w in combined for w in ("401", "403", "unauthorized", "forbidden", "auth", "token expired", "invalid_api_key")):
            return FailureCategory.AUTH_ERROR
        if any(w in combined for w in ("validationerror", "pydantic", "schema", "missing field", "keyerror", "jsondecodeerror")):
            return FailureCategory.SCHEMA_MISMATCH
        if any(w in combined for w in ("modulenotfounderror", "importerror", "package", "dependency", "npm err", "pip failed")):
            return FailureCategory.BUILD_DEPENDENCY_ERROR
        if any(w in combined for w in ("rate limit", "429", "quota", "gemini", "openai", "model overloaded", "503")):
            return FailureCategory.AI_PROVIDER_ERROR
        if any(w in combined for w in ("env", "config", "missing url", "webhook_url", "connection refused", "not configured")):
            return FailureCategory.CONFIG_ERROR

        return FailureCategory.UNKNOWN

    @classmethod
    def get_suggested_mitigation(cls, failure_category: FailureCategory) -> str:
        """
        Returns deterministic, bounded mitigation strategies based on failure category.
        """
        mitigations = {
            FailureCategory.TIMEOUT: "Increase timeout limit or switch to asynchronous background execution queue.",
            FailureCategory.AUTH_ERROR: "Verify credentials in environment vault and refresh expired authentication tokens.",
            FailureCategory.SCHEMA_MISMATCH: "Validate payload against canonical contract; sanitize missing optional fields.",
            FailureCategory.BUILD_DEPENDENCY_ERROR: "Verify lockfile dependencies and rebuild sandbox virtual environment.",
            FailureCategory.AI_PROVIDER_ERROR: "Activate secondary provider fallback (Gemini -> Antigravity) with backoff.",
            FailureCategory.CONFIG_ERROR: "Provision required missing configuration parameters or route to operator.",
            FailureCategory.UNKNOWN: "Isolate trace logs and request human engineering review."
        }
        return mitigations.get(failure_category, "Inspect execution logs and diagnose root cause.")

    @classmethod
    def evaluate_attempt(
        cls,
        current_attempt: int,
        failure_category: FailureCategory,
        operation_id: str
    ) -> Dict[str, Any]:
        """
        Enforces strict 3-attempt ceiling. If current_attempt >= 3, escalates to CEO_REQUIRED.
        """
        if current_attempt >= cls.MAX_REPAIR_ATTEMPTS:
            return {
                "operation_id": operation_id,
                "attempt": current_attempt,
                "max_attempts": cls.MAX_REPAIR_ATTEMPTS,
                "can_retry": False,
                "status": "CEO_REQUIRED",
                "action": "ESCALATE_TO_OPERATOR",
                "mitigation": cls.get_suggested_mitigation(failure_category),
                "reason": f"Bounded self-correction exhausted ({current_attempt}/{cls.MAX_REPAIR_ATTEMPTS} attempts). Human sign-off required."
            }

        return {
            "operation_id": operation_id,
            "attempt": current_attempt,
            "next_attempt": current_attempt + 1,
            "max_attempts": cls.MAX_REPAIR_ATTEMPTS,
            "can_retry": True,
            "status": "RETRY_SCHEDULED",
            "action": "APPLY_BOUNDED_FIX",
            "mitigation": cls.get_suggested_mitigation(failure_category),
            "reason": f"Failure classified as {failure_category.value}. Applying bounded correction (attempt {current_attempt + 1}/{cls.MAX_REPAIR_ATTEMPTS})."
        }

    @classmethod
    async def record_and_learn_failure(
        cls,
        session: AsyncSession,
        entity_id: str,
        error_message: str,
        error_context: Optional[Dict[str, Any]] = None,
        occurrence_count: int = 1
    ) -> KnowledgeFact:
        """
        Classifies failure and stores a learned failure pattern fact for the entity.
        """
        category = cls.classify_failure(error_message, error_context)
        fix = cls.get_suggested_mitigation(category)
        signature = error_message[:100] if error_message else "general_error"

        return await store_failure_pattern(
            session=session,
            entity_id=entity_id,
            failure_type=category.value,
            failure_signature=signature,
            suggested_fix=fix,
            occurrence_count=occurrence_count
        )

    @classmethod
    async def get_known_failure_patterns(
        cls,
        session: AsyncSession,
        entity_id: str
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all learned failure patterns associated with a target entity or system component.
        """
        facts = await get_facts_for_entity(
            session=session,
            entity_type="system_pattern",
            entity_id=entity_id,
            category="failure_pattern"
        )
        patterns = []
        for f in facts:
            patterns.append({
                "fact_id": f.id,
                "fact_key": f.fact_key,
                "failure_type": f.fact_value.get("failure_type"),
                "signature": f.fact_value.get("signature"),
                "suggested_fix": f.fact_value.get("suggested_fix"),
                "occurrence_count": f.fact_value.get("occurrence_count", 1),
                "confidence": f.confidence
            })
        return patterns


failure_learning_engine = FailureLearningEngine()
