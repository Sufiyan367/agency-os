"""
Voice Escalation Engine — Phase 17.
Detects sensitive conversational conditions requiring immediate handover to human operators:
- Legal threats / regulatory matters / litigation
- Aggressive hostility / profanity / harassment
- Refund or payment dispute
- Sensitive personal data / privacy requests
- Out-of-scope custom requests / unusual contract terms
- Explicit requests for human operators
- Low AI confidence scores (< 0.65)
"""

import re
from typing import Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel

class VoiceEscalationReason(str, Enum):
    LEGAL_THREAT = "LEGAL_THREAT"
    HOSTILITY_HARASSMENT = "HOSTILITY_HARASSMENT"
    PRIVACY_REQUEST = "PRIVACY_REQUEST"
    PAYMENT_DISPUTE = "PAYMENT_DISPUTE"
    UNUSUAL_CONTRACT_TERMS = "UNUSUAL_CONTRACT_TERMS"
    OUT_OF_SCOPE_SERVICE = "OUT_OF_SCOPE_SERVICE"
    EXPLICIT_HUMAN_REQUEST = "EXPLICIT_HUMAN_REQUEST"
    UNCERTAIN_AI_RESPONSE = "UNCERTAIN_AI_RESPONSE"


class VoiceEscalationCheckResult(BaseModel):
    should_escalate: bool
    reason: Optional[VoiceEscalationReason] = None
    confidence: float = 1.0
    details: str = ""
    suggested_operator_handover_message: Optional[str] = None


class VoiceEscalationEngine:
    """
    Evaluates utterances and conversational state to determine if human escalation is required.
    Ensures routine questions and standard objections do NOT trigger escalation.
    """

    LEGAL_PATTERNS = [
        r"\b(lawyer|attorney|lawsuit|legal action|litigation|sue you|court|cease and desist|damages)\b"
    ]

    HOSTILITY_PATTERNS = [
        r"\b(harass|harassment|fuck|bitch|bastard|asshole|threat|police|report you)\b"
    ]

    PRIVACY_PATTERNS = [
        r"\b(gdpr|ccpa|right to be forgotten|delete my data|where did you get my number|personal data|data privacy)\b"
    ]

    PAYMENT_DISPUTE_PATTERNS = [
        r"\b(chargeback|scam|fraud|stole|refund my money|rip off|dispute the charge)\b"
    ]

    CONTRACT_PATTERNS = [
        r"\b(sla penalty|unlimited liability|indemnification|custom nda|exclusive ownership of ip|guarantee 100%)\b"
    ]

    OUT_OF_SCOPE_PATTERNS = [
        r"\b(build a mobile app|ios app|android app|blockchain|crypto|hardware repair|seo backlinks|print marketing)\b"
    ]

    EXPLICIT_HUMAN_PATTERNS = [
        r"\b(talk to a human|speak to a human|real person|human please|transfer me to someone|speak with your manager|let me speak to someone)\b"
    ]

    @classmethod
    def evaluate(
        cls,
        utterance: str,
        ai_confidence: float = 1.0,
        context: Optional[Dict[str, Any]] = None
    ) -> VoiceEscalationCheckResult:
        text = utterance.strip().lower()

        # 1. Legal / Regulatory
        for pat in cls.LEGAL_PATTERNS:
            if re.search(pat, text):
                return VoiceEscalationCheckResult(
                    should_escalate=True,
                    reason=VoiceEscalationReason.LEGAL_THREAT,
                    confidence=0.99,
                    details="Legal threat or regulatory matter detected.",
                    suggested_operator_handover_message=(
                        "I understand your concern. I am noting your file and escalating this directly "
                        "to our executive management team for immediate review."
                    )
                )

        # 2. Hostility / Harassment
        for pat in cls.HOSTILITY_PATTERNS:
            if re.search(pat, text):
                return VoiceEscalationCheckResult(
                    should_escalate=True,
                    reason=VoiceEscalationReason.HOSTILITY_HARASSMENT,
                    confidence=0.99,
                    details="Hostile or aggressive interaction detected.",
                    suggested_operator_handover_message=(
                        "I apologize for the disturbance. I am terminating this call and marking your contact preferences."
                    )
                )

        # 3. Privacy requests
        for pat in cls.PRIVACY_PATTERNS:
            if re.search(pat, text):
                return VoiceEscalationCheckResult(
                    should_escalate=True,
                    reason=VoiceEscalationReason.PRIVACY_REQUEST,
                    confidence=0.98,
                    details="Privacy or statutory data protection request.",
                    suggested_operator_handover_message=(
                        "We take privacy very seriously. We sourced your publicly listed business contact from public web records. "
                        "I will immediately ensure your contact details are removed and handled by our privacy officer."
                    )
                )

        # 4. Payment dispute
        for pat in cls.PAYMENT_DISPUTE_PATTERNS:
            if re.search(pat, text):
                return VoiceEscalationCheckResult(
                    should_escalate=True,
                    reason=VoiceEscalationReason.PAYMENT_DISPUTE,
                    confidence=0.98,
                    details="Payment dispute or fraud allegation.",
                    suggested_operator_handover_message=(
                        "I want to make sure your account is handled accurately. "
                        "Let me connect you with our billing and finance director."
                    )
                )

        # 5. Unusual contract terms
        for pat in cls.CONTRACT_PATTERNS:
            if re.search(pat, text):
                return VoiceEscalationCheckResult(
                    should_escalate=True,
                    reason=VoiceEscalationReason.UNUSUAL_CONTRACT_TERMS,
                    confidence=0.95,
                    details="Unusual contractual terms or liability demands.",
                    suggested_operator_handover_message=(
                        "Specialized contract terms require review by our executive team. "
                        "I will have our director send over our standard enterprise schedule."
                    )
                )

        # 6. Out of scope services
        for pat in cls.OUT_OF_SCOPE_PATTERNS:
            if re.search(pat, text):
                return VoiceEscalationCheckResult(
                    should_escalate=True,
                    reason=VoiceEscalationReason.OUT_OF_SCOPE_SERVICE,
                    confidence=0.93,
                    details="Requested service outside authorized scope (Core Web Vitals / Speed Turnaround).",
                    suggested_operator_handover_message=(
                        "We specialize specifically in website speed, mobile conversion, and Core Web Vitals turnaround. "
                        "I will have a solutions consultant follow up to confirm whether our engineering team can accommodate that."
                    )
                )

        # 7. Explicit human request
        for pat in cls.EXPLICIT_HUMAN_PATTERNS:
            if re.search(pat, text):
                return VoiceEscalationCheckResult(
                    should_escalate=True,
                    reason=VoiceEscalationReason.EXPLICIT_HUMAN_REQUEST,
                    confidence=0.99,
                    details="Prospect explicitly requested human operator.",
                    suggested_operator_handover_message=(
                        "Certainly. Let me connect you directly with one of our senior specialists."
                    )
                )

        # 8. Low AI Confidence score
        if ai_confidence < 0.65:
            return VoiceEscalationCheckResult(
                should_escalate=True,
                reason=VoiceEscalationReason.UNCERTAIN_AI_RESPONSE,
                confidence=ai_confidence,
                details=f"AI confidence {ai_confidence:.2f} is below 0.65 threshold.",
                suggested_operator_handover_message=(
                    "I want to make sure you get the exact right technical information. "
                    "Let me flag this for our lead systems engineer to follow up."
                )
            )

        return VoiceEscalationCheckResult(should_escalate=False)

voice_escalation_engine = VoiceEscalationEngine()
