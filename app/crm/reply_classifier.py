import re
from datetime import datetime
from typing import Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import (
    Business, OutreachMessage, Reply, ReplyClassification,
    PipelineStage, PipelineEvent, FollowupStatus, Proposal, Offer, AuditRun, ProspectMemory
)
from app.core.llm import llm_client
from app.core.logging import logger
from app.followups.engine import followup_engine
from app.outreach.compliance import compliance_guard
from app.crm.objections import (
    objection_detector, objection_response_engine, ObjectionCategory, ObjectionResponse
)

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
        if re.search(r"\b(unsubscribe|remove (?:me|us)|stop emailing|opt[- ]?out|take (?:me|us) off)\b", lower):
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

        if any(w in lower for w in ["not interested", "no thanks", "we're good", "already have", "pass", "not for us", "uninterested"]):
            return {
                "classification": ReplyClassification.NOT_INTERESTED.value,
                "confidence": 0.92,
                "reasoning": "Polite or direct decline.",
                "suggested_response": "Thank you for the reply and consideration. Wishing you and the team continued success!"
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
                "suggested_response": "Our turnkey remediation packages range from $500 to $1,200 depending on scope. Would you like me to send the itemized breakdown?"
            }

        if any(w in lower for w in ["interested", "sounds good", "send more", "send video", "send audit", "sure", "love to see", "yes please"]):
            return {
                "classification": ReplyClassification.INTERESTED.value,
                "confidence": 0.90,
                "reasoning": "Positive sentiment indicating interest in reviewing diagnostic audit.",
                "suggested_response": "Great to hear from you! Here is the link to your audit report summary. Would you like to review the implementation steps together?"
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

                # Autonomous proposal & payment link preparation for commercial intent
                if cat in (ReplyClassification.INTERESTED.value, ReplyClassification.MEETING_REQUEST.value, ReplyClassification.PRICE_REQUEST.value):
                    try:
                        q_prop = select(Proposal).where(Proposal.business_id == business_id).order_by(Proposal.created_at.desc())
                        existing_prop = (await session.execute(q_prop)).scalars().first()
                        if not existing_prop:
                            q_off = select(Offer).where(Offer.business_id == business_id).order_by(Offer.created_at.desc())
                            offer = (await session.execute(q_off)).scalars().first()
                            title = offer.title if offer else "Website Turnaround & Optimization Package"
                            price = offer.recommended_price if (offer and offer.recommended_price >= 500.0) else 650.0
                            from app.core.config import settings
                            adv_pct = getattr(settings, "DEFAULT_ADVANCE_PERCENTAGE", 40.0)
                            adv_req = round(price * (adv_pct / 100.0), 2)
                            
                            from app.payments.deal_service import deal_closing_service
                            existing_prop = await deal_closing_service.create_proposal(
                                session=session,
                                business_id=business_id,
                                title=title,
                                total_value=price,
                                advance_required=adv_req,
                                service_type=getattr(offer, "service_type", "Conversion Rate Optimization") if offer else "Website Turnaround",
                                is_mock=getattr(settings, "PAYMENT_DRY_RUN", True)
                            )

                        from app.payments.provider import get_active_payment_provider
                        provider = get_active_payment_provider()
                        payment_data = await provider.create_payment_link(
                            business_id=business_id,
                            offer_id=0,
                            title=existing_prop.title,
                            amount_usd=existing_prop.advance_required,
                            customer_email=sender_email
                        )
                        checkout_link = payment_data.get("checkout_url", "")

                        if checkout_link:
                            from app.core.config import settings
                            adv_pct = getattr(settings, "DEFAULT_ADVANCE_PERCENTAGE", 40.0)
                            if cat == ReplyClassification.PRICE_REQUEST.value:
                                suggested = (
                                    f"Hi there, thank you for following up! For {biz.domain if biz else 'your website'}, our complete {existing_prop.title} "
                                    f"is a fixed investment of ${existing_prop.total_value:,.0f} USD. We require a {int(adv_pct)}% deposit (${existing_prop.advance_required:,.0f}) "
                                    f"to initiate immediate remediation. You can review the scope and reserve your project slot here: {checkout_link}\n\n"
                                    f"Best regards,\n{settings.OUTREACH_FROM_NAME}"
                                )
                            elif cat in (ReplyClassification.INTERESTED.value, ReplyClassification.MEETING_REQUEST.value):
                                suggested = (
                                    f"Hi there, glad to hear from you! We have compiled the diagnostic findings and turnaround plan for {biz.domain if biz else 'your website'}. "
                                    f"To get started without delay, your project reservation and deposit link is ready here: {checkout_link}\n\n"
                                    f"Looking forward to helping you increase inbound inquiries!\n\nBest regards,\n{settings.OUTREACH_FROM_NAME}"
                                )
                            reply.suggested_response = suggested
                    except Exception as e:
                        logger.warning(f"[ReplyClassifier] Auto-proposal drafting note: {e}")

                # Commercial Value & Offer Resolution
                q_off = select(Offer).where(Offer.business_id == business_id).order_by(Offer.created_at.desc())
                offer = (await session.execute(q_off)).scalars().first()
                offered_val = offer.recommended_price if offer else getattr(settings, "TARGET_OFFER_MINIMUM_USD", 1000.0)

                # Objection Handling Engine Evaluation
                detected_objections = objection_detector.detect_objections(raw_body)
                sensitive_trigger = objection_detector.detect_sensitive_triggers(raw_body)
                obj_resp = None

                if sensitive_trigger.get("is_sensitive"):
                    if biz:
                        biz.human_takeover = True
                        biz.pipeline_stage = PipelineStage.APPROVAL.value

                if detected_objections or sensitive_trigger.get("is_sensitive"):
                    # Retrieve audit context for grounded response
                    q_audit = select(AuditRun).where(AuditRun.business_id == business_id).order_by(AuditRun.audited_at.desc())
                    audit_run = (await session.execute(q_audit)).scalars().first()
                    audit_ctx = {
                        "performance_score": audit_run.performance_score if audit_run else 70.0,
                        "findings": audit_run.findings if audit_run else []
                    }

                    prospect_ctx = {
                        "domain": biz.domain if biz else "your website",
                        "name": biz.name if biz else "your website",
                        "audit_results": audit_ctx,
                        "estimated_value": offered_val
                    }
                    obj_resp = objection_response_engine.generate_response(
                        prospect_context=prospect_ctx,
                        objections=detected_objections,
                        raw_reply=raw_body
                    )
                    # If reply was an objection, use the objection response draft
                    if cat not in (ReplyClassification.UNSUBSCRIBE.value, ReplyClassification.BOUNCE.value, ReplyClassification.PRICE_REQUEST.value, ReplyClassification.INTERESTED.value):
                        suggested = obj_resp.client_facing_draft
                        reply.suggested_response = suggested

                # Sync ProspectMemory
                q_mem = select(ProspectMemory).where(ProspectMemory.business_id == biz.id)
                mem = (await session.execute(q_mem)).scalars().first()
                if not mem:
                    mem = ProspectMemory(
                        business_id=biz.id,
                        domain=biz.domain,
                        contact_email=sender_email,
                        pipeline_stage=new_stage,
                        estimated_value=offered_val,
                        conversation_history=[],
                        objection_history=[]
                    )
                    session.add(mem)
                mem.pipeline_stage = new_stage
                mem.last_interaction = f"Reply received from {sender_email}: {cat}"
                mem.next_expected_action = "MEETING_CONFIRMATION" if new_stage == PipelineStage.QUALIFIED_REPLY.value else "FOLLOW_UP"
                history = list(mem.conversation_history or [])
                history.append({
                    "sender": "PROSPECT",
                    "message": raw_body,
                    "timestamp": datetime.utcnow().isoformat()
                })
                if suggested:
                    history.append({
                        "sender": "AGENT",
                        "message": suggested,
                        "intent": cat,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                mem.conversation_history = history

                if obj_resp:
                    obj_hist = list(mem.objection_history or [])
                    obj_hist.append({
                        "objections": obj_resp.objection_categories,
                        "primary": obj_resp.primary_objection,
                        "draft_response": obj_resp.client_facing_draft,
                        "reasoning": obj_resp.internal_reasoning,
                        "commercial_implications": obj_resp.commercial_implications,
                        "recommended_action": obj_resp.recommended_action,
                        "force_human_takeover": obj_resp.force_human_takeover,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    mem.objection_history = obj_hist
                    mem.updated_at = datetime.utcnow()

        await session.commit()
        logger.info(f"Processed reply from {sender_email} for business {business_id}. Classified as {cat}")
        return reply

reply_classifier = ReplyClassifier()
