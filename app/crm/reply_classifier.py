import re
from typing import Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import (
    Business, OutreachMessage, Reply, ReplyClassification,
    PipelineStage, PipelineEvent, FollowupStatus
)
from app.core.llm import llm_client
from app.core.logging import logger
from app.followups.engine import followup_engine
from app.outreach.compliance import compliance_guard

class ReplyClassifier:
    """
    Intelligently analyzes and classifies prospect email replies,
    generates contextual suggested follow-ups, enforces opt-out/suppression,
    and advances CRM pipeline stages.
    """

    async def classify_text(self, reply_body: str) -> Dict[str, Any]:
        """Classifies raw reply text using LLM with deterministic regex fallback."""
        text = reply_body.strip()
        lower = text.lower()

        # 1. Immediate Rule-based Checks (High confidence shortcuts)
        if re.search(r"\b(unsubscribe|remove me|stop emailing|opt[- ]?out|take me off)\b", lower):
            return {
                "classification": ReplyClassification.UNSUBSCRIBE.value,
                "confidence": 0.99,
                "reasoning": "Explicit unsubscribe/opt-out keyword detected.",
                "suggested_response": "Understood. You have been removed from our list."
            }

        if re.search(r"\b(delivery failure|mailer-daemon|undeliverable|address not found|550 user)\b", lower):
            return {
                "classification": ReplyClassification.BOUNCE.value,
                "confidence": 0.99,
                "reasoning": "Automated mail server bounce notification.",
                "suggested_response": ""
            }

        if re.search(r"\b(out of the office|on leave|vacation|auto[- ]?reply|maternity leave)\b", lower):
            return {
                "classification": ReplyClassification.OUT_OF_OFFICE.value,
                "confidence": 0.95,
                "reasoning": "Automated out-of-office autoreply.",
                "suggested_response": "No immediate action required until return date."
            }

        if re.search(r"\b(schedule|call|calendar|calendly|meet|zoom|thursday|monday|tuesday|wednesday|friday|tomorrow)\b", lower) and \
           any(w in lower for w in ["time", "talk", "chat", "discuss", "available", "morning", "afternoon"]):
            return {
                "classification": ReplyClassification.MEETING_REQUEST.value,
                "confidence": 0.95,
                "reasoning": "Prospect requested or proposed a discussion/meeting time.",
                "suggested_response": "Thank you! I can do Thursday at 10:00 AM or 2:30 PM. Would either time work for a 10-minute screenshare?"
            }

        if re.search(r"\b(cost|pricing|price|how much|fee|quote|rates|estimate)\b", lower):
            return {
                "classification": ReplyClassification.PRICE_REQUEST.value,
                "confidence": 0.92,
                "reasoning": "Prospect inquired about commercial fee or pricing structure.",
                "suggested_response": "Our turnkey remediation packages range from $450 to $1,200 depending on scope. Would you like me to send the itemized breakdown?"
            }

        if any(w in lower for w in ["interested", "sounds good", "send more", "send video", "send audit", "sure", "love to see", "yes please"]):
            return {
                "classification": ReplyClassification.INTERESTED.value,
                "confidence": 0.90,
                "reasoning": "Positive sentiment indicating interest in reviewing diagnostic audit.",
                "suggested_response": "Great to hear from you! Here is the link to your audit report summary. Would you like to review the implementation steps together?"
            }

        if any(w in lower for w in ["not interested", "no thanks", "we're good", "already have", "pass"]):
            return {
                "classification": ReplyClassification.NOT_INTERESTED.value,
                "confidence": 0.92,
                "reasoning": "Polite or direct decline.",
                "suggested_response": "Thank you for the reply and consideration. Wishing you and the team continued success!"
            }

        # 2. LLM Evaluation for nuanced replies
        prompt = (
            f"Classify this B2B prospect reply into one category: "
            f"[INTERESTED, QUESTION, NOT_INTERESTED, LATER, PRICE_REQUEST, MEETING_REQUEST, REFERRAL, OUT_OF_OFFICE, UNSUBSCRIBE, BOUNCE, UNKNOWN].\n"
            f"Reply Text: \"{text}\"\n\n"
            f"Return a JSON object with: classification, confidence (0.0 to 1.0), reasoning, suggested_response."
        )
        try:
            llm_result = await llm_client.generate_json(prompt)
            if "classification" in llm_result:
                return llm_result
        except Exception as e:
            logger.warning(f"LLM reply classification error: {e}")

        return {
            "classification": ReplyClassification.QUESTION.value,
            "confidence": 0.75,
            "reasoning": "General inquiry requiring human review.",
            "suggested_response": "Thank you for your response. Let me clarify that point for you."
        }

    async def process_incoming_reply(
        self,
        session: AsyncSession,
        business_id: int,
        sender_email: str,
        raw_body: str,
        message_id: int | None = None
    ) -> Reply:
        classification_data = await self.classify_text(raw_body)
        cat = classification_data.get("classification", ReplyClassification.UNKNOWN.value)
        conf = classification_data.get("confidence", 0.85)
        reason = classification_data.get("reasoning", "")
        suggested = classification_data.get("suggested_response", "")

        reply = Reply(
            business_id=business_id,
            outreach_message_id=message_id,
            sender_email=sender_email,
            raw_body=raw_body,
            classification=cat,
            confidence=conf,
            suggested_response=suggested
        )
        session.add(reply)

        biz = await session.get(Business, business_id)

        # Handle Unsubscribes and Bounces: Immediately add to suppression list
        if cat == ReplyClassification.UNSUBSCRIBE.value:
            await compliance_guard.add_to_suppression(session, sender_email, reason="UNSUBSCRIBE")
            await followup_engine.cancel_pending_followups(session, business_id, FollowupStatus.CANCELLED_UNSUB)
            if biz:
                biz.pipeline_stage = PipelineStage.LOST.value
        elif cat == ReplyClassification.BOUNCE.value:
            await compliance_guard.add_to_suppression(session, sender_email, reason="BOUNCE")
            await followup_engine.cancel_pending_followups(session, business_id, FollowupStatus.CANCELLED_UNSUB)
            if biz:
                biz.pipeline_stage = PipelineStage.LOST.value
        else:
            # Stop pending follow-ups since lead replied
            await followup_engine.cancel_pending_followups(session, business_id, FollowupStatus.CANCELLED_REPLY)

            # Advance CRM stage based on intent
            if biz:
                old_stage = biz.pipeline_stage
                if cat in (ReplyClassification.INTERESTED.value, ReplyClassification.MEETING_REQUEST.value, ReplyClassification.PRICE_REQUEST.value):
                    new_stage = PipelineStage.QUALIFIED_REPLY.value
                elif cat == ReplyClassification.NOT_INTERESTED.value:
                    new_stage = PipelineStage.LOST.value
                else:
                    new_stage = PipelineStage.REPLIED.value

                biz.pipeline_stage = new_stage
                event = PipelineEvent(
                    business_id=biz.id,
                    from_stage=old_stage,
                    to_stage=new_stage,
                    deal_value=0.0,
                    note=f"Reply received from {sender_email}. Classified as {cat} ({conf*100:.0f}% confidence): {reason}"
                )
                session.add(event)

        await session.commit()
        logger.info(f"Processed reply from {sender_email} for business {business_id}. Classified as {cat}")
        return reply

reply_classifier = ReplyClassifier()
