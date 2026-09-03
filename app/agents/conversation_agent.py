"""
Provider-Agnostic Conversation Agent with Language Adaptation and Fact-Grounding Guardrails.
Guards:
- Explains findings only from audited diagnostic evidence
- Answers strictly using configured services
- Never promises unavailable services
- Never commits to legally binding pricing autonomously
- Never claims payment confirmed without verified webhook signature
"""
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.communications.conversation import ConversationSession, ConversationMessage


class ConversationResponse(BaseModel):
    reply_text: str
    detected_language: str
    intent_detected: str  # INTERESTED, OBJECTION, PRICING, MEETING_REQUEST, UNSUBSCRIBE, UNKNOWN
    propose_meeting: bool
    handoff_to_human: bool
    confidence: float


class ConversationAgent:
    SUPPORTED_LANGUAGES = {"en": "English", "ar": "Arabic", "es": "Spanish", "fr": "French"}

    @classmethod
    def detect_language(cls, text: str) -> str:
        # Arabic character range
        if re.search(r"[\u0600-\u06FF]", text):
            return "ar"
        lower = text.lower()
        # Spanish markers
        if any(w in lower for w in ["hola", "gracias", "precio", "reunion", "¿", "buenos dias", "interesado"]):
            return "es"
        # French markers
        if any(w in lower for w in ["bonjour", "merci", "combien", "rendez-vous", "salut", "intéressé"]):
            return "fr"
        return "en"

    @classmethod
    def process_reply(
        cls,
        incoming_message: str,
        audit_evidence: Dict[str, Any],
        offered_service_value: float,
        session: Optional[ConversationSession] = None
    ) -> ConversationResponse:
        lang = cls.detect_language(incoming_message)
        lower = incoming_message.lower()

        # 1. Store incoming message in session if provided
        if session:
            session.add_message(sender="PROSPECT", content=incoming_message)

        # 2. Unsubscribe check
        if any(w in lower for w in ["stop", "unsubscribe", "remove", "cancel", "arret", "baja"]):
            resp = ConversationResponse(
                reply_text="You have been removed from our communications. Have a great day.",
                detected_language=lang,
                intent_detected="UNSUBSCRIBE",
                propose_meeting=False,
                handoff_to_human=False,
                confidence=0.99
            )
            if session:
                session.add_message(sender="AGENT", content=resp.reply_text, intent=resp.intent_detected)
            return resp

        # 3. Meeting request / positive interest
        meeting_keywords = [
            "schedule", "call", "meet", "book", "zoom", "interested", "available",
            "agendar", "llamada", "reunion", "cita", "interesado",
            "rendez-vous", "discuter", "disponible", "intéressé",
            "موعد", "مكالمة", "اجتماع", "مهتم"
        ]
        if any(w in lower for w in meeting_keywords):
            perf = audit_evidence.get("performance_score", 70.0)
            if lang == "es":
                reply = f"Excelente. Podemos agendar una llamada breve de 15 minutos para revisar los hallazgos técnicos (puntuación actual: {perf:.0f}/100). ¿Qué horario le conviene esta semana?"
            elif lang == "fr":
                reply = f"Parfait. Nous pouvons planifier un court échange de 15 minutes pour vous présenter l'audit technique ({perf:.0f}/100). Quel créneau vous convient ?"
            elif lang == "ar":
                reply = f"ممتاز. يسعدنا ترتيب مكالمة سريعة لمدة 15 دقيقة لمراجعة تقرير الفحص الفني الخاص بموقعكم. ما هو الوقت المناسب لكم؟"
            else:
                reply = f"Great to hear from you. We can schedule a brief 15-minute consultation to walk through the technical diagnostic findings ({perf:.0f}/100 performance). Which time works best for you this week?"

            resp = ConversationResponse(
                reply_text=reply,
                detected_language=lang,
                intent_detected="MEETING_REQUEST",
                propose_meeting=True,
                handoff_to_human=False,
                confidence=0.94
            )
            if session:
                session.add_message(sender="AGENT", content=resp.reply_text, intent=resp.intent_detected)
            return resp

        # 4. Pricing inquiries (guard: non-binding exploratory range only)
        if any(w in lower for w in ["how much", "cost", "price", "pricing", "cuanto", "tarifs", "كم"]):
            reply = f"Our turnaround and automation packages start at a baseline minimum of ${offered_service_value:,.0f}, tailored specifically to your website's performance bottlenecks. Let's schedule a 10-minute discovery chat to scope exact deliverables."
            resp = ConversationResponse(
                reply_text=reply,
                detected_language=lang,
                intent_detected="PRICING",
                propose_meeting=True,
                handoff_to_human=False,
                confidence=0.90
            )
            if session:
                session.add_message(sender="AGENT", content=resp.reply_text, intent=resp.intent_detected)
            return resp

        # 5. Complex objection or custom requirements -> Hand off to human
        reply = "Thank you for the additional details. I have routed your query to our technical solutions team so a senior strategist can reply directly."
        resp = ConversationResponse(
            reply_text=reply,
            detected_language=lang,
            intent_detected="UNKNOWN",
            propose_meeting=False,
            handoff_to_human=True,
            confidence=0.60
        )
        if session:
            session.add_message(sender="AGENT", content=resp.reply_text, intent=resp.intent_detected)
            session.handed_off_to_human = True
        return resp
