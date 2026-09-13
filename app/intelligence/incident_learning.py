"""
Incident Learning Engine — Mega Prompt 8.
Extends operational memory: searches prior verified incident patterns before diagnosing new faults.
Surfaces previously verified fixes for automated revalidation without blind execution.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database.models import IncidentMemory
from app.support.sla_and_memory import incident_memory_service

class IncidentLearningEngine:
    """
    Closed-loop incident learning engine.
    Ensures recurring bugs are resolved faster via pattern recognition.
    """

    @classmethod
    async def find_prior_verified_solution(
        cls,
        session: AsyncSession,
        category: str,
        error_pattern: str,
        component: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Queries verified incident memory for matching signatures or error substrings.
        """
        prior_fixes = await incident_memory_service.search_memory(
            session=session,
            category=category,
            error_pattern=error_pattern
        )

        if not prior_fixes:
            return None

        # Return best match with highest occurrence count
        top_match = prior_fixes[0]
        return {
            "status": "PREVIOUSLY_VERIFIED_PATTERN_FOUND",
            "signature": top_match["signature"],
            "component": top_match["component"],
            "root_cause": top_match["root_cause"],
            "remediation_pattern": top_match["remediation_pattern"],
            "verified_fix": top_match.get("verified_fix", {}),
            "occurrence_count": top_match["occurrence_count"],
            "confidence": 0.95 if top_match["occurrence_count"] > 2 else 0.85,
            "instruction": "Revalidate existing preconditions before applying verified pattern."
        }

    @classmethod
    async def learn_from_resolved_incident(
        cls,
        session: AsyncSession,
        category: str,
        component: str,
        error_pattern: str,
        root_cause: str,
        remediation_pattern: str,
        verified_diff: Dict[str, Any],
        prevention_guidance: str = ""
    ) -> IncidentMemory:
        """
        Records or increments occurrence frequency for a verified remediation pattern.
        """
        return await incident_memory_service.record_incident_memory(
            session=session,
            category=category,
            component=component,
            error_pattern=error_pattern,
            root_cause=root_cause,
            remediation_pattern=remediation_pattern,
            verified_fix=verified_diff,
            prevention_guidance=prevention_guidance
        )


incident_learning_engine = IncidentLearningEngine()
