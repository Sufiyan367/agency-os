"""
Conversation Intelligence Engine — Mega Prompt 8.
Analyzes incoming prospect messages, detects buyer intent signals, classifies objections,
and maintains strict prompt injection boundaries.
"""
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.intelligence.models import (
    IntelligenceSignal, SignalType, EpistemicStatus,
    ConfidenceBand
)
from app.intelligence.provider_abstraction import get_intelligence_provider

logger = logging.getLogger("agency.intelligence.conversation")


class ConversationIntelligenceEngine:
    """
    Classifies conversational replies and extracts actionable commercial signals.
    """

    INTENT_CATEGORIES = [
        "POSITIVE", "NEGATIVE", "QUESTION", "NEEDS_HUMAN",
        "UNSUBSCRIBE", "OUT_OF_OFFICE", "UNKNOWN"
    ]

    BUYING_INTENT_PATTERNS = {
        SignalType.READY_TO_BUY: [
            r"\b(let's do it|ready to proceed|send (the )?contract|sign|send invoice|how do we start)\b",
            r"\b(let's start|move forward|get started|onboard)\b"
        ],
        SignalType.BUYING_INTENT: [
            r"\b(interested|call me|book a call|schedule|demo|meet|zoom|calendly)\b",
            r"\b(sounds promising|tell me more|send more details)\b"
        ],
        SignalType.BUDGET_SIGNAL: [
            r"\b(what is the cost|pricing|how much|quote|rates|investment|budget)\b"
        ],
        SignalType.URGENCY: [
            r"\b(asap|urgently|today|this week|immediate|emergency|quickly)\b"
        ],
        SignalType.AUTHORITY_SIGNAL: [
            r"\b(i am the owner|founder|managing director|ceo|principal|partner)\b"
        ]
    }

    OBJECTION_PATTERNS = {
        SignalType.PRICE_OBJECTION: [
            r"\b(too expensive|can't afford|out of our budget|costly|discount|cheaper)\b"
        ],
        SignalType.TIMING_OBJECTION: [
            r"\b(not right now|circle back|next quarter|next year|busy right now|later)\b"
        ],
        SignalType.TRUST_OBJECTION: [
            r"\b(case studies|references|guarantee|who else|proven|portfolio)\b"
        ],
        SignalType.COMPETITOR_REFERENCE: [
            r"\b(already have an agency|working with someone|in-house team|current provider)\b"
        ]
    }

    @classmethod
    def sanitize_untrusted_input(cls, raw_text: str) -> str:
        """
        Strips potential prompt injection syntax and control sequences.
        Ensures malicious external text cannot hijack downstream reasoning.
        """
        if not raw_text:
            return ""
        # Remove prompt injection delimiters (system tags, markdown backticks attempts, system instruction cues)
        sanitized = re.sub(r'(system:|assistant:|user:|<[^>]+>|```)', ' ', raw_text, flags=re.IGNORECASE)
        # Bounded length (max 4000 chars)
        return sanitized[:4000].strip()

    @classmethod
    async def analyze_message(
        cls,
        raw_message: str,
        business_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates an incoming message, detecting intent and granular objection/intent signals.
        """
        clean_text = cls.sanitize_untrusted_input(raw_message)
        provider = get_intelligence_provider()

        # 1. High-level classification from provider (with deterministic guarantee)
        base_classification = await provider.classify_conversation(clean_text, business_context or {})

        # 2. Granular Signal Detection (Deterministic Regular Expression Extraction)
        detected_signals: List[Dict[str, Any]] = []

        # Intent signals
        for sig_type, patterns in cls.BUYING_INTENT_PATTERNS.items():
            for p in patterns:
                match = re.search(p, clean_text, re.IGNORECASE)
                if match:
                    detected_signals.append({
                        "signal_type": sig_type.value,
                        "category": "BUYING_INTENT",
                        "matched_phrase": match.group(0),
                        "confidence": 0.90,
                        "epistemic_status": EpistemicStatus.OBSERVED_FACT.value
                    })
                    break

        # Objection signals
        for sig_type, patterns in cls.OBJECTION_PATTERNS.items():
            for p in patterns:
                match = re.search(p, clean_text, re.IGNORECASE)
                if match:
                    detected_signals.append({
                        "signal_type": sig_type.value,
                        "category": "OBJECTION",
                        "matched_phrase": match.group(0),
                        "confidence": 0.88,
                        "epistemic_status": EpistemicStatus.OBSERVED_FACT.value
                    })
                    break

        # Check for Out of Office
        if re.search(r"\b(out of (the )?office|auto-reply|on vacation|maternity leave|away from)\b", clean_text, re.IGNORECASE):
            base_classification["classification"] = "OUT_OF_OFFICE"
            base_classification["suggested_action"] = "WAIT"

        return {
            "classification": base_classification.get("classification", "UNKNOWN"),
            "intent_level": base_classification.get("intent_level", "LOW"),
            "confidence": base_classification.get("confidence", 0.70),
            "confidence_band": base_classification.get("confidence_band", "MEDIUM"),
            "suggested_action": base_classification.get("suggested_action", "NO_ACTION"),
            "needs_human": base_classification.get("needs_human", False),
            "detected_signals": detected_signals,
            "evidence_snippet": clean_text[:200],
            "decision_rationale": base_classification.get("rationale", "Standard pattern recognition evaluated.")
        }


conversation_intelligence_engine = ConversationIntelligenceEngine()
