"""
Event-Driven Prospect Memory Service.
Persists complete prospect memory upon initial outreach:
- business_id, contact info, audit results, buyer/opportunity scores,
- offer/proposal, outreach message, channel used, timestamp,
- pipeline stage, thread/call identifiers, last interaction, next expected action.

When an inbound event (reply, voice transcript, meeting, payment) arrives later,
identifies the prospect from stored identifiers, restores the context,
handles the event via agent logic, and saves the updated state
WITHOUT interrupting the background prospecting worker.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database.models import (
    Business, Contact, AuditRun, LeadScore, Offer, OutreachMessage,
    PipelineStage, PipelineEvent, ProspectMemory, Meeting
)
from app.agents.conversation_agent import ConversationAgent
from app.crm.reply_classifier import reply_classifier, ReplyClassification
from app.outreach.compliance import compliance_guard

logger = logging.getLogger(__name__)


class ProspectMemoryService:
    """Manages persistent prospect memory and event-driven state resumption."""

    @classmethod
    async def save_memory(
        cls,
        session: AsyncSession,
        *,
        business_id: int,
        domain: str,
        contact_name: Optional[str] = None,
        contact_email: Optional[str] = None,
        contact_phone: Optional[str] = None,
        thread_id: Optional[str] = None,
        call_sid: Optional[str] = None,
        payment_link_id: Optional[str] = None,
        channel_used: str = "EMAIL",
        pipeline_stage: str = "CONTACTED",
        audit_results: Optional[Dict[str, Any]] = None,
        buyer_score: float = 0.0,
        opportunity_score: float = 0.0,
        estimated_value: float = 500.0,
        offer_proposal: Optional[Dict[str, Any]] = None,
        outreach_message: Optional[Dict[str, Any]] = None,
        last_interaction: str = "",
        next_expected_action: str = "AWAITING_INBOUND_EVENT",
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> ProspectMemory:
        """Saves or updates the persistent snapshot for a prospect."""
        q = select(ProspectMemory).where(
            or_(
                ProspectMemory.business_id == business_id,
                ProspectMemory.domain == domain
            )
        )
        res = await session.execute(q)
        memory = res.scalar_one_or_none()

        clean_audit = audit_results or {}
        clean_offer = offer_proposal or {}
        clean_outreach = outreach_message or {}
        clean_history = conversation_history or []

        if not memory:
            memory = ProspectMemory(
                business_id=business_id,
                domain=domain,
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                thread_id=thread_id,
                call_sid=call_sid,
                payment_link_id=payment_link_id,
                channel_used=channel_used,
                pipeline_stage=pipeline_stage,
                audit_results=clean_audit,
                buyer_score=buyer_score,
                opportunity_score=opportunity_score,
                estimated_value=estimated_value,
                offer_proposal=clean_offer,
                outreach_message=clean_outreach,
                last_interaction=last_interaction or f"Outreach dispatched via {channel_used}",
                next_expected_action=next_expected_action,
                conversation_history=clean_history,
                timestamp=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.add(memory)
        else:
            if contact_name:
                memory.contact_name = contact_name
            if contact_email:
                memory.contact_email = contact_email
            if contact_phone:
                memory.contact_phone = contact_phone
            if thread_id:
                memory.thread_id = thread_id
            if call_sid:
                memory.call_sid = call_sid
            if payment_link_id:
                memory.payment_link_id = payment_link_id
            memory.channel_used = channel_used
            memory.pipeline_stage = pipeline_stage
            if clean_audit:
                memory.audit_results = clean_audit
            if buyer_score > 0:
                memory.buyer_score = buyer_score
            if opportunity_score > 0:
                memory.opportunity_score = opportunity_score
            if estimated_value > 0:
                memory.estimated_value = estimated_value
            if clean_offer:
                memory.offer_proposal = clean_offer
            if clean_outreach:
                memory.outreach_message = clean_outreach
            if last_interaction:
                memory.last_interaction = last_interaction
            if next_expected_action:
                memory.next_expected_action = next_expected_action
            if clean_history:
                memory.conversation_history = clean_history
            memory.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(memory)
        return memory

    @classmethod
    async def get_memory(
        cls,
        session: AsyncSession,
        *,
        business_id: Optional[int] = None,
        domain: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        thread_id: Optional[str] = None,
        call_sid: Optional[str] = None,
        payment_link_id: Optional[str] = None
    ) -> Optional[ProspectMemory]:
        """Looks up persistent prospect memory by any recognized identifier."""
        filters = []
        if business_id:
            filters.append(ProspectMemory.business_id == business_id)
        if domain:
            filters.append(ProspectMemory.domain.ilike(domain.strip()))
        if email:
            clean_email = email.strip().lower()
            filters.append(ProspectMemory.contact_email.ilike(clean_email))
            if "@" in clean_email:
                email_domain = clean_email.split("@")[-1]
                filters.append(ProspectMemory.domain.ilike(email_domain))
        if phone:
            clean_phone = phone.strip()
            filters.append(ProspectMemory.contact_phone == clean_phone)
        if thread_id:
            filters.append(ProspectMemory.thread_id == thread_id)
        if call_sid:
            filters.append(ProspectMemory.call_sid == call_sid)
        if payment_link_id:
            filters.append(ProspectMemory.payment_link_id == payment_link_id)

        if not filters:
            return None

        q = select(ProspectMemory).where(or_(*filters)).order_by(ProspectMemory.updated_at.desc())
        res = await session.execute(q)
        memory = res.scalars().first()
        if memory:
            return memory

        # Fallback: if no ProspectMemory record yet, check Business table
        biz = None
        if business_id:
            biz = await session.get(Business, business_id)
        elif domain:
            res_biz = await session.execute(select(Business).where(Business.domain.ilike(domain.strip())))
            biz = res_biz.scalars().first()
        elif email:
            res_biz = await session.execute(select(Business).where(Business.public_email.ilike(email.strip())))
            biz = res_biz.scalars().first()

        if biz:
            return await cls.save_memory(
                session,
                business_id=biz.id,
                domain=biz.domain,
                contact_email=biz.public_email,
                contact_phone=biz.phone,
                channel_used="EMAIL" if biz.public_email else "VOICE",
                pipeline_stage=biz.pipeline_stage or "CONTACTED",
                estimated_value=750.0,
                last_interaction="Synthesized from business record"
            )

        return None

    @classmethod
    async def handle_inbound_event(
        cls,
        session: AsyncSession,
        event_type: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handles an incoming event (EMAIL_REPLY, VOICE_OUTCOME, MEETING, PAYMENT)
        by looking up the stored prospect memory, restoring context, executing
        reasoning, and persisting the updated stage without halting prospecting.
        """
        biz_id = payload.get("business_id")
        domain = payload.get("domain")
        email = payload.get("email") or payload.get("sender_email")
        phone = payload.get("phone") or payload.get("prospect_phone")
        thread_id = payload.get("thread_id") or payload.get("message_id")
        call_sid = payload.get("call_sid")
        payment_link_id = payload.get("payment_link_id") or payload.get("plink_id")

        memory = await cls.get_memory(
            session,
            business_id=biz_id,
            domain=domain,
            email=email,
            phone=phone,
            thread_id=thread_id,
            call_sid=call_sid,
            payment_link_id=payment_link_id
        )

        if not memory:
            logger.info(f"[ProspectMemoryService] Event {event_type} could not be matched to any stored prospect memory.")
            return {"status": "UNMATCHED", "event_type": event_type}

        audit_results = memory.audit_results or {}
        offered_value = memory.estimated_value or 500.0
        domain = memory.domain
        biz = await session.get(Business, memory.business_id)

        result: Dict[str, Any] = {
            "status": "PROCESSED",
            "event_type": event_type,
            "prospect_domain": domain,
            "business_id": memory.business_id,
            "restored_context": {
                "audit_results": audit_results,
                "offered_value": offered_value,
                "buyer_score": memory.buyer_score,
                "opportunity_score": memory.opportunity_score,
                "offer_proposal": memory.offer_proposal,
                "outreach_message": memory.outreach_message,
                "channel_used": memory.channel_used
            }
        }

        if event_type in ("EMAIL_REPLY", "REPLY"):
            body = payload.get("body", "") or payload.get("raw_body", "")
            conversation_response = ConversationAgent.process_reply(
                incoming_message=body,
                audit_evidence=audit_results,
                offered_service_value=offered_value
            )

            history = list(memory.conversation_history or [])
            history.append({
                "sender": "PROSPECT",
                "message": body,
                "timestamp": datetime.utcnow().isoformat()
            })
            history.append({
                "sender": "AGENT",
                "message": conversation_response.reply_text,
                "intent": conversation_response.intent_detected,
                "timestamp": datetime.utcnow().isoformat()
            })
            memory.conversation_history = history

            if conversation_response.intent_detected == "UNSUBSCRIBE":
                memory.pipeline_stage = PipelineStage.LOST.value
                memory.last_interaction = "Prospect unsubscribed. Suppressed."
                memory.next_expected_action = "NONE"
                if memory.contact_email:
                    await compliance_guard.add_to_suppression(session, memory.contact_email, reason="UNSUBSCRIBE")
            elif conversation_response.handoff_to_human:
                memory.pipeline_stage = "HUMAN_TAKEOVER"
                memory.last_interaction = f"Handoff requested ({conversation_response.intent_detected})."
                memory.next_expected_action = "HUMAN_OPERATOR_REVIEW"
            elif conversation_response.propose_meeting or conversation_response.intent_detected in ("INTERESTED", "MEETING_REQUEST"):
                memory.pipeline_stage = PipelineStage.QUALIFIED_REPLY.value
                memory.last_interaction = f"Positive reply ({conversation_response.intent_detected}). Meeting proposed."
                memory.next_expected_action = "AWAITING_MEETING_CONFIRMATION"
            else:
                memory.pipeline_stage = PipelineStage.REPLIED.value
                memory.last_interaction = f"Reply received ({conversation_response.intent_detected})."
                memory.next_expected_action = "FOLLOW_UP"

            result["agent_reply"] = conversation_response.reply_text
            result["intent"] = conversation_response.intent_detected
            result["new_stage"] = memory.pipeline_stage

        elif event_type in ("VOICE_CALL", "CALL_STATUS", "TRANSCRIPT"):
            call_outcome = payload.get("outcome", "COMPLETED")
            booked = payload.get("meeting_booked", False)
            escalated = payload.get("escalated", False)
            call_sid_val = payload.get("call_sid")
            if call_sid_val:
                memory.call_sid = call_sid_val

            if booked:
                memory.pipeline_stage = PipelineStage.MEETING.value
                memory.last_interaction = "Autonomous voice call scheduled diagnostic consultation."
                memory.next_expected_action = "ATTEND_MEETING"
            elif escalated:
                memory.pipeline_stage = "HUMAN_TAKEOVER"
                memory.last_interaction = "Voice call escalated to human specialist."
                memory.next_expected_action = "OPERATOR_CALLBACK"
            else:
                memory.last_interaction = f"Voice call completed ({call_outcome})."
                memory.next_expected_action = "AWAITING_RESPONSE"

            result["new_stage"] = memory.pipeline_stage

        elif event_type in ("MEETING_BOOKED", "MEETING_COMPLETED"):
            if event_type == "MEETING_BOOKED":
                memory.pipeline_stage = PipelineStage.MEETING.value
                memory.last_interaction = "Diagnostic consultation meeting scheduled."
                memory.next_expected_action = "ATTEND_MEETING"
            else:
                memory.pipeline_stage = PipelineStage.PROPOSAL.value
                memory.last_interaction = "Diagnostic consultation completed. Proposal presented."
                memory.next_expected_action = "AWAITING_PAYMENT"
            result["new_stage"] = memory.pipeline_stage

        elif event_type in ("PAYMENT_RECEIVED", "PAYMENT_CONFIRMED", "PAYMENT_LINK_PAID"):
            memory.pipeline_stage = PipelineStage.WON.value
            memory.last_interaction = f"Payment verified ({payload.get('amount_usd', offered_value)}$). Client onboarded."
            memory.next_expected_action = "DELIVERY_IN_PROGRESS"
            result["new_stage"] = memory.pipeline_stage

        if biz:
            biz.pipeline_stage = memory.pipeline_stage

        memory.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(memory)

        logger.info(f"[ProspectMemoryService] Handled {event_type} for {domain}. New stage: {memory.pipeline_stage}")
        return result


memory_service = ProspectMemoryService()
