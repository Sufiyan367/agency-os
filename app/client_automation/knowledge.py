"""
Agency OS — Client Automation FAQ & Knowledge Retrieval Engine.

Matches customer queries against client-isolated knowledge bases,
evaluates retrieval confidence, formats answers according to brand voice,
and enforces human escalation fallback on low confidence or unknown topics.
Zero fabrication: answers are strictly grounded in client documents.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Any

from app.client_automation.brain import shared_brain_manager, TenantIsolationError
from app.client_automation.models import EscalationReason, EscalationEvent

logger = logging.getLogger("agency.client_automation.knowledge")


class KnowledgeEngine:
    """
    Client-grounded retrieval engine with confidence scoring and escalation triggers.
    """

    CONFIDENCE_THRESHOLD = 0.25

    @classmethod
    async def answer_query(
        cls,
        client_id: str,
        query: str,
        caller_phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves grounded answers for a client-specific query.
        If confidence is low or escalation keywords match, triggers human escalation.
        """
        brain = shared_brain_manager.get_brain(client_id)
        if not brain:
            return {
                "answered": False,
                "confidence": 0.0,
                "answer": "We are currently unavailable. A team member will assist you shortly.",
                "escalate": True,
                "escalation_reason": EscalationReason.UNKNOWN_INTENT.value,
                "sources": [],
            }

        config = brain.config
        lower_query = query.lower()

        # 1. Check for explicit human escalation triggers
        for kw in config.escalation_rules.escalation_keywords:
            if kw.lower() in lower_query:
                # Record escalation in brain
                brain.record_escalation(
                    EscalationEvent(
                        escalation_id=f"ESC-{client_id[:4].upper()}-{len(brain.list_escalations())+1}",
                        client_id=client_id,
                        reason=EscalationReason.EXPLICIT_HUMAN_REQUEST,
                        message=f"Customer requested human assistance: '{query}'",
                        context={"query": query, "caller_phone": caller_phone},
                    )
                )
                return {
                    "answered": False,
                    "confidence": 1.0,
                    "answer": f"I understand you'd like to speak with our team. I have notified {config.business_name}'s staff to assist you right away.",
                    "escalate": True,
                    "escalation_reason": EscalationReason.EXPLICIT_HUMAN_REQUEST.value,
                    "sources": [],
                }

        # 2. Search client's isolated knowledge base
        matches = brain.search_knowledge(query, limit=3)
        if not matches or matches[0]["score"] < cls.CONFIDENCE_THRESHOLD:
            # Low confidence -> Trigger fallback escalation
            brain.record_escalation(
                EscalationEvent(
                    escalation_id=f"ESC-{client_id[:4].upper()}-{len(brain.list_escalations())+1}",
                    client_id=client_id,
                    reason=EscalationReason.LOW_CONFIDENCE,
                    message=f"Unrecognized question below confidence threshold: '{query}'",
                    context={"query": query, "top_match": matches[0] if matches else None},
                )
            )
            return {
                "answered": False,
                "confidence": matches[0]["score"] if matches else 0.0,
                "answer": f"Thank you for asking. I don't have the exact answer in {config.business_name}'s catalog right now, so I've escalated your question to our team.",
                "escalate": True,
                "escalation_reason": EscalationReason.LOW_CONFIDENCE.value,
                "sources": matches,
            }

        # 3. Format grounded response
        top_match = matches[0]
        answer_text = top_match["content"]

        return {
            "answered": True,
            "confidence": top_match["score"],
            "answer": answer_text,
            "escalate": False,
            "escalation_reason": None,
            "sources": [top_match["id"]],
        }


knowledge_engine = KnowledgeEngine()
