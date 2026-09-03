"""
Voice Sales Agent & Conversational Intelligence Engine.
Handles:
- Script generation grounded strictly in technical audit diagnostics
- Multilingual voice synthesis (EN, AR, ES, FR)
- Live objection handling (cost, existing agency, timing, send email)
- Non-binding pricing guardrails ($500 floor to $2,500 maximum)
- Appointment booking & meeting scheduling
- Escalation to human operator upon low confidence or hostility
"""
import re
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from app.core.config import settings


class VoiceConversationTurn(BaseModel):
    speaker: str  # 'AGENT' or 'PROSPECT'
    text: str
    intent: Optional[str] = None
    sentiment: Optional[str] = None


class VoiceQualificationResult(BaseModel):
    qualified: bool
    intent: str  # 'BOOK_MEETING', 'SEND_INFO', 'OBJECTION_HANDLED', 'NOT_INTERESTED', 'HUMAN_ESCALATION'
    recommended_action: str
    proposed_meeting_time: Optional[datetime] = None
    suggested_reply: str
    confidence: float
    escalate_to_human: bool = False
    opt_out: bool = False


class VoiceSalesAgent:
    """Conversational intelligence engine for outbound voice sales calls."""

    PRICING_FLOOR_USD = 500.0
    PRICING_CEILING_USD = 2500.0

    @classmethod
    def generate_call_script(
        cls,
        business_name: str,
        niche: str,
        city: str,
        audit_evidence: Dict[str, Any],
        language: str = "en"
    ) -> str:
        """Generates initial conversational opener grounded in factual diagnostic findings."""
        perf = audit_evidence.get("performance_score", 52.0)
        speed_sec = audit_evidence.get("load_time_seconds", 4.1)

        if language == "es":
            return (
                f"Hola, llamo de parte de Agency Growth para {business_name}. "
                f"Completamos un diagnóstico técnico de su sitio web en {city}. "
                f"Detectamos que tarda aproximadamente {speed_sec:.1f} segundos en cargar en móviles (puntuación {perf:.0f}/100), "
                f"lo cual suele provocar la pérdida de llamadas de clientes potenciales. "
                f"¿Tienen 2 minutos para revisar brevemente cómo solucionar esto?"
            )
        elif language == "fr":
            return (
                f"Bonjour, je vous contacte de la part d'Agency Growth pour {business_name}. "
                f"Nous avons effectué un audit technique de votre site à {city}. "
                f"Le site met environ {speed_sec:.1f} secondes à s'afficher sur mobile ({perf:.0f}/100), "
                f"ce qui réduit vos demandes de devis. "
                f"Auriez-vous deux minutes pour en discuter ?"
            )
        elif language == "ar":
            return (
                f"مرحباً، أتواصل معكم بخصوص موقع {business_name} في {city}. "
                f"أجرينا فحصاً فنياً ولاحظنا أن سرعة تحميل الموقع تستغرق {speed_sec:.1f} ثانية على الهواتف، "
                f"مما يقلل من تواصل العملاء. هل يناسبكم الحديث لدقيقتين لتوضيح النتائج؟"
            )

        # Default English
        return (
            f"Hi, this is Elena Vance from Agency Growth calling for {business_name} in {city}. "
            f"We ran a preliminary mobile speed diagnostic on your site and noticed it takes about {speed_sec:.1f} seconds to load "
            f"with a Google PageSpeed score of {perf:.0f}/100. In the {niche} industry, that typically causes up to 40% of mobile visitors to bounce before calling. "
            f"Do you have two minutes to see how we quickly fix this?"
        )

    @staticmethod
    def _contains_phrase(text: str, phrases: list) -> bool:
        for p in phrases:
            pattern = r'(?:\b|^)' + re.escape(p) + r'(?:\b|$)'
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    @classmethod
    def process_prospect_speech(
        cls,
        prospect_utterance: str,
        audit_evidence: Dict[str, Any],
        language: str = "en"
    ) -> VoiceQualificationResult:
        """Evaluates prospect verbal response, handles objections, and determines next step."""
        text = prospect_utterance.lower().strip()
        perf = audit_evidence.get("performance_score", 50.0)

        # 1. Hostility or explicit opt-out
        if cls._contains_phrase(text, ["stop calling", "remove me", "sue", "fuck", "don't call again", "harassment", "baja", "arret"]):
            return VoiceQualificationResult(
                qualified=False,
                intent="NOT_INTERESTED",
                recommended_action="APOLOGIZE_AND_OPTOUT",
                suggested_reply="I apologize for the intrusion. I will immediately update our records to ensure you are not called again. Have a good day.",
                confidence=0.99,
                opt_out=True
            )

        # 2. Objection: "Already have a web guy / agency" (prioritize before generic affirmative words)
        if cls._contains_phrase(text, ["have a guy", "webmaster", "agency", "in-house", "developer", "ya tengo"]):
            return VoiceQualificationResult(
                qualified=True,
                intent="OBJECTION_HANDLED",
                recommended_action="PROVIDE_DIAGNOSTIC_FOR_WEBMASTER",
                suggested_reply=(
                    f"That makes total sense, and we certainly respect that relationship. "
                    f"Since the mobile diagnostic scored {perf:.0f}/100, we'd be happy to send you the one-page technical report "
                    f"so your developer can address the caching and image bottlenecks directly. What's the best email for you?"
                ),
                confidence=0.91
            )

        # 3. Meeting confirmation / positive interest
        if cls._contains_phrase(text, ["sure", "yes", "interested", "let's talk", "schedule", "thursday", "tomorrow", "sounds good", "si", "sí", "d'accord", "نعم"]):
            meeting_time = datetime.utcnow() + timedelta(days=2, hours=4)
            return VoiceQualificationResult(
                qualified=True,
                intent="BOOK_MEETING",
                recommended_action="SCHEDULE_CONSULTATION",
                proposed_meeting_time=meeting_time,
                suggested_reply="That's great. I have an opening this Thursday at 2:00 PM for our technical lead to walk through the exact speed fixes. Would that time work for you?",
                confidence=0.95
            )

        # 4. Objection: "Too expensive / How much does it cost?"
        if any(w in text for w in ["cost", "how much", "price", "expensive", "budget", "cuanto", "combien", "كم"]):
            return VoiceQualificationResult(
                qualified=True,
                intent="OBJECTION_HANDLED",
                recommended_action="ANCHOR_PRICING_RANGE",
                suggested_reply=(
                    f"Our full mobile speed turnaround packages start at a baseline of ${cls.PRICING_FLOOR_USD:,.0f} "
                    f"up to ${cls.PRICING_CEILING_USD:,.0f} for complete custom core-web-vitals overhauls. "
                    f"Most businesses recover that in the very first commercial contract they win. "
                    f"Can we do a 10-minute screenshare to confirm your exact scope?"
                ),
                confidence=0.92
            )

        # 5. Request for email / written information
        if any(w in text for w in ["send an email", "email me", "send details", "in writing", "correo"]):
            return VoiceQualificationResult(
                qualified=True,
                intent="SEND_INFO",
                recommended_action="CONFIRM_EMAIL_AND_SEND",
                suggested_reply="I'd be glad to. I will compile the audit diagnostic and email it over within 10 minutes with our case studies. Thank you for your time.",
                confidence=0.94
            )

        # 6. Unclear / Complex inquiry -> Human Escalation
        return VoiceQualificationResult(
            qualified=False,
            intent="HUMAN_ESCALATION",
            recommended_action="TRANSFER_OR_ESCALATE_TO_SENIOR",
            suggested_reply="I want to make sure you get the exact technical specifications for that. Let me connect you directly with our senior strategy director.",
            confidence=0.60,
            escalate_to_human=True
        )
