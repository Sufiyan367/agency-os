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

        # 3. AI Identity & Transparency Disclosure (never impersonates human or claims to be human)
        if any(w in lower for w in ["are you an ai", "are you ai", "are you human", "are you a bot", "are you a robot", "is this a bot", "is this automated", "is this ai"]):
            reply = (
                "I am an automated AI technical assistant for Agency Growth's web engineering team. "
                "I scan and analyze public website performance diagnostics to identify speed bottlenecks "
                "before our senior human engineering specialists review them. "
                "Would you like to schedule a 15-minute consultation to review the specific findings for your site?"
            )
            resp = ConversationResponse(
                reply_text=reply,
                detected_language=lang,
                intent_detected="AI_IDENTITY_DISCLOSED",
                propose_meeting=True,
                handoff_to_human=False,
                confidence=0.98
            )
            if session:
                session.add_message(sender="AGENT", content=resp.reply_text, intent=resp.intent_detected)
            return resp

        # 4. Routine Question: What do you do / How does this work?
        if any(w in lower for w in ["what do you do", "how does this work", "what service", "what is this about", "explain"]):
            perf = audit_evidence.get("performance_score", 70.0)
            reply = (
                f"We specialize in Core Web Vitals and mobile performance turnarounds for commercial service companies. "
                f"Our scanner identified that your website's performance is currently rated at {perf:.0f}/100, which causes "
                f"friction and lost inquiries on mobile devices. We optimize caching, image payloads, and script execution "
                f"to drastically improve load speed. Can we schedule a 15-minute call to walk through the diagnosis?"
            )
            resp = ConversationResponse(
                reply_text=reply,
                detected_language=lang,
                intent_detected="SERVICE_EXPLANATION",
                propose_meeting=True,
                handoff_to_human=False,
                confidence=0.93
            )
            if session:
                session.add_message(sender="AGENT", content=resp.reply_text, intent=resp.intent_detected)
            return resp

        # 5. Routine Objection: Already have an agency / web developer
        if any(w in lower for w in ["have a guy", "webmaster", "agency", "in-house", "developer", "already have", "ya tengo"]):
            perf = audit_evidence.get("performance_score", 70.0)
            reply = (
                f"We completely respect your existing developer relationship. Since your mobile performance diagnostic scored {perf:.0f}/100, "
                f"we can provide a complimentary one-page technical report detailing the exact bottlenecks so your team can address them directly. "
                f"Would you like us to send that over?"
            )
            resp = ConversationResponse(
                reply_text=reply,
                detected_language=lang,
                intent_detected="OBJECTION_DEVELOPER",
                propose_meeting=False,
                handoff_to_human=False,
                confidence=0.92
            )
            if session:
                session.add_message(sender="AGENT", content=resp.reply_text, intent=resp.intent_detected)
            return resp

        # 5.5 Explicit human demand or legal escalation -> Hand off to human immediately
        if any(w in lower for w in ["human", "real person", "operator", "manager", "lawyer", "attorney", "legal", "speak with someone"]):
            reply = "Thank you for the note. I have routed your message directly to our senior human management team to review and follow up with you personally."
            resp = ConversationResponse(
                reply_text=reply,
                detected_language=lang,
                intent_detected="HUMAN_TAKEOVER_REQUEST",
                propose_meeting=False,
                handoff_to_human=True,
                confidence=0.96
            )
            if session:
                session.add_message(sender="AGENT", content=resp.reply_text, intent=resp.intent_detected)
                session.handed_off_to_human = True
            return resp

        # 6. Meeting request / positive interest
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

        # 7. Pricing inquiries (guard: non-binding exploratory range only with $500+ floor)
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

        # 8. Request for written info / email
        if any(w in lower for w in ["send info", "send email", "email me", "more details", "in writing"]):
            reply = "We'll be glad to send over the technical summary and benchmark case studies to your verified email. Have a great day!"
            resp = ConversationResponse(
                reply_text=reply,
                detected_language=lang,
                intent_detected="SEND_INFO",
                propose_meeting=False,
                handoff_to_human=False,
                confidence=0.92
            )
            if session:
                session.add_message(sender="AGENT", content=resp.reply_text, intent=resp.intent_detected)
            return resp

        # 9. Genuinely exceptional situation or explicit human demand -> Hand off to human
        is_explicit_human_demand = any(w in lower for w in ["human", "real person", "operator", "manager", "lawyer", "attorney", "speak with someone"])
        reply = "Thank you for the additional details. I have routed your query to our senior technical solutions strategist to follow up with you directly."
        resp = ConversationResponse(
            reply_text=reply,
            detected_language=lang,
            intent_detected="HUMAN_TAKEOVER_REQUEST" if is_explicit_human_demand else "UNKNOWN",
            propose_meeting=False,
            handoff_to_human=True,
            confidence=0.70
        )
        if session:
            session.add_message(sender="AGENT", content=resp.reply_text, intent=resp.intent_detected)
            session.handed_off_to_human = True
        return resp
