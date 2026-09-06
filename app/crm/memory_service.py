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
    PipelineStage, PipelineEvent, ProspectMemory, Meeting, Reply, Proposal, Payment
)
from app.agents.conversation_agent import ConversationAgent
from app.crm.reply_classifier import reply_classifier, ReplyClassification
from app.outreach.compliance import compliance_guard
from app.followups.engine import followup_engine, FollowupStatus
from app.crm.objections import (
    objection_detector, objection_response_engine, ObjectionCategory, ObjectionResponse
)

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
            if memory.domain != domain:
                # Recycled business_id across test runs or database resets: purge stale history from old domain
                memory.domain = domain
                memory.conversation_history = []
                memory.audit_results = {}
                memory.offer_proposal = {}
                memory.outreach_message = {}
                memory.last_interaction = ""

            memory.business_id = business_id
            memory.domain = domain
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
            if conversation_history is not None:
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
        """Looks up persistent prospect memory by prioritizing exact identifiers."""
        if domain:
            res = await session.execute(
                select(ProspectMemory).where(ProspectMemory.domain.ilike(domain.strip())).order_by(ProspectMemory.updated_at.desc())
            )
            mem = res.scalars().first()
            if mem:
                return mem

        if email:
            clean_email = email.strip().lower()
            res = await session.execute(
                select(ProspectMemory).where(ProspectMemory.contact_email.ilike(clean_email)).order_by(ProspectMemory.updated_at.desc())
            )
            mem = res.scalars().first()
            if mem:
                return mem
            if "@" in clean_email:
                email_domain = clean_email.split("@")[-1]
                res = await session.execute(
                    select(ProspectMemory).where(ProspectMemory.domain.ilike(email_domain)).order_by(ProspectMemory.updated_at.desc())
                )
                mem = res.scalars().first()
                if mem:
                    return mem

        if thread_id:
            res = await session.execute(
                select(ProspectMemory).where(ProspectMemory.thread_id == thread_id).order_by(ProspectMemory.updated_at.desc())
            )
            mem = res.scalars().first()
            if mem:
                return mem

        if call_sid:
            res = await session.execute(
                select(ProspectMemory).where(ProspectMemory.call_sid == call_sid).order_by(ProspectMemory.updated_at.desc())
            )
            mem = res.scalars().first()
            if mem:
                return mem

        if payment_link_id:
            res = await session.execute(
                select(ProspectMemory).where(ProspectMemory.payment_link_id == payment_link_id).order_by(ProspectMemory.updated_at.desc())
            )
            mem = res.scalars().first()
            if mem:
                return mem

        if phone:
            res = await session.execute(
                select(ProspectMemory).where(ProspectMemory.contact_phone == phone.strip()).order_by(ProspectMemory.updated_at.desc())
            )
            mem = res.scalars().first()
            if mem:
                return mem

        if business_id:
            res = await session.execute(
                select(ProspectMemory).where(ProspectMemory.business_id == business_id).order_by(ProspectMemory.updated_at.desc())
            )
            mem = res.scalars().first()
            if mem:
                return mem

        # Fallback: if no ProspectMemory record yet, check Business table
        biz = None
        if domain:
            res_biz = await session.execute(select(Business).where(Business.domain.ilike(domain.strip())))
            biz = res_biz.scalars().first()
        elif business_id:
            biz = await session.get(Business, business_id)
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

        from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType

        await activity_broadcaster.record_event(
            session=session,
            run_id=f"INB-{memory.business_id}",
            event_type=AgentEventType.INBOUND_EVENT_RECEIVED.value,
            message=f"Inbound {event_type} event received for prospect {domain}.",
            business_id=memory.business_id,
            domain=domain,
            status="INFO",
            metadata_json={"event_type": event_type, "matched_domain": domain}
        )

        await activity_broadcaster.record_event(
            session=session,
            run_id=f"INB-{memory.business_id}",
            event_type=AgentEventType.PROSPECT_MEMORY_RESTORED.value,
            message=f"Prospect memory restored for {domain}. Previous audit ({audit_results.get('performance_score', 50)}/100) & offer (${offered_value:.0f}) loaded.",
            business_id=memory.business_id,
            domain=domain,
            status="SUCCESS",
            metadata_json={"audit_results": audit_results, "offered_value": offered_value}
        )

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

            # 1. Automatic Follow-Up Control: Cancel all pending follow-ups immediately
            await followup_engine.cancel_pending_followups(session, memory.business_id, FollowupStatus.CANCELLED_REPLY)

            # 2. Objection & Sensitive Trigger Detection
            detected_objections = objection_detector.detect_objections(body)
            sensitive_trigger = objection_detector.detect_sensitive_triggers(body)

            prospect_ctx = {
                "domain": domain,
                "name": getattr(biz, "name", domain) if biz else domain,
                "audit_results": audit_results,
                "estimated_value": offered_value,
                "offer_proposal": memory.offer_proposal
            }

            obj_resp = objection_response_engine.generate_response(
                prospect_context=prospect_ctx,
                objections=detected_objections,
                raw_reply=body
            )

            # Record in conversation history
            history = list(memory.conversation_history or [])
            history.append({
                "sender": "PROSPECT",
                "message": body,
                "timestamp": datetime.utcnow().isoformat()
            })
            history.append({
                "sender": "AGENT",
                "message": obj_resp.client_facing_draft,
                "intent": obj_resp.primary_objection,
                "objections": obj_resp.objection_categories,
                "recommended_action": obj_resp.recommended_action,
                "approval_required": obj_resp.approval_required,
                "timestamp": datetime.utcnow().isoformat()
            })
            memory.conversation_history = history

            # Record in objection history
            obj_hist = list(memory.objection_history or [])
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
            memory.objection_history = obj_hist

            # 3. State & Lifecycle Advancement
            if ObjectionCategory.OPT_OUT in detected_objections or obj_resp.primary_objection == ObjectionCategory.OPT_OUT.value:
                memory.pipeline_stage = PipelineStage.LOST.value
                memory.last_interaction = "Prospect opted out. Suppressed permanently."
                memory.next_expected_action = "NONE"
                if memory.contact_email:
                    await compliance_guard.add_to_suppression(session, memory.contact_email, reason="OPT_OUT")
                await followup_engine.cancel_pending_followups(session, memory.business_id, FollowupStatus.CANCELLED_UNSUB)
            elif obj_resp.force_human_takeover or sensitive_trigger.get("is_sensitive"):
                memory.pipeline_stage = "HUMAN_TAKEOVER"
                memory.last_interaction = f"Handoff requested ({obj_resp.primary_objection}): {sensitive_trigger.get('reason')}"
                memory.next_expected_action = "HUMAN_OPERATOR_REVIEW"
                if biz:
                    biz.human_takeover = True
                    biz.pipeline_stage = PipelineStage.APPROVAL.value
                await activity_broadcaster.record_event(
                    session=session,
                    run_id=f"INB-{memory.business_id}",
                    event_type=AgentEventType.HUMAN_TAKEOVER.value,
                    message=f"Human operator takeover triggered for {domain}: {obj_resp.primary_objection}.",
                    business_id=memory.business_id,
                    domain=domain,
                    status="WARNING",
                    metadata_json={"intent": obj_resp.primary_objection, "reason": sensitive_trigger.get("reason")}
                )
            elif ObjectionCategory.NOT_INTERESTED in detected_objections and len(detected_objections) == 1:
                memory.pipeline_stage = PipelineStage.LOST.value
                memory.last_interaction = "Prospect declined offer (NOT_INTERESTED)."
                memory.next_expected_action = "CLOSED_AS_LOST"
            elif any(w in body.lower() for w in ["schedule", "call", "meet", "calendar", "zoom", "interested", "yes"]):
                memory.pipeline_stage = PipelineStage.QUALIFIED_REPLY.value
                memory.last_interaction = f"Positive reply ({obj_resp.primary_objection}). Meeting proposed."
                memory.next_expected_action = "AWAITING_MEETING_CONFIRMATION"
            else:
                memory.pipeline_stage = PipelineStage.REPLIED.value
                memory.last_interaction = f"Reply received with objections: {', '.join(obj_resp.objection_categories) or 'general'}."
                memory.next_expected_action = obj_resp.recommended_action

            result["agent_reply"] = obj_resp.client_facing_draft
            if any(w in body.lower() for w in ["schedule", "call", "meet", "calendar", "zoom"]):
                result["intent"] = "MEETING_REQUEST"
            elif any(w in body.lower() for w in ["interested", "sounds good", "send details"]):
                result["intent"] = "INTERESTED"
            elif obj_resp.primary_objection and obj_resp.primary_objection != "UNKNOWN":
                result["intent"] = obj_resp.primary_objection
            else:
                conv_resp = ConversationAgent.process_reply(
                    incoming_message=body,
                    audit_evidence=audit_results,
                    offered_service_value=offered_value
                )
                result["intent"] = conv_resp.intent_detected
            result["objections"] = obj_resp.objection_categories
            result["recommended_action"] = obj_resp.recommended_action
            result["commercial_implications"] = obj_resp.commercial_implications
            result["internal_reasoning"] = obj_resp.internal_reasoning
            result["force_human_takeover"] = obj_resp.force_human_takeover
            result["new_stage"] = memory.pipeline_stage

            await activity_broadcaster.record_event(
                session=session,
                run_id=f"INB-{memory.business_id}",
                event_type=AgentEventType.REPLY_CLASSIFIED.value,
                message=f"Inbound reply classified with objections ({', '.join(obj_resp.objection_categories) or 'none'}) for {domain}.",
                business_id=memory.business_id,
                domain=domain,
                status="INFO",
                metadata_json={"objections": obj_resp.objection_categories, "primary": obj_resp.primary_objection, "body": body}
            )

            await activity_broadcaster.record_event(
                session=session,
                run_id=f"INB-{memory.business_id}",
                event_type=AgentEventType.CONVERSATION_RESPONSE_GENERATED.value,
                message=f"Autonomous objection response drafted for {domain} (Evidence-grounded).",
                business_id=memory.business_id,
                domain=domain,
                status="SUCCESS",
                metadata_json={
                    "agent_reply": obj_resp.client_facing_draft,
                    "new_stage": memory.pipeline_stage,
                    "recommended_action": obj_resp.recommended_action
                }
            )

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

    @classmethod
    async def get_full_commercial_context(
        cls,
        session: AsyncSession,
        business_id: int
    ) -> Dict[str, Any]:
        """
        Reconstructs complete multi-touch commercial memory for a prospect across all database entities.
        """
        biz = await session.get(Business, business_id)
        if not biz:
            return {"error": "Business not found", "business_id": business_id}

        from app.core.config import settings
        # Prospect memory snapshot
        q_mem = select(ProspectMemory).where(ProspectMemory.business_id == business_id)
        memory = (await session.execute(q_mem)).scalars().first()

        # Audit runs
        q_audit = select(AuditRun).where(AuditRun.business_id == business_id).order_by(AuditRun.audited_at.desc())
        audit_runs = (await session.execute(q_audit)).scalars().all()
        latest_audit = audit_runs[0] if audit_runs else None

        # Lead scores
        q_score = select(LeadScore).where(LeadScore.business_id == business_id).order_by(LeadScore.created_at.desc())
        scores = (await session.execute(q_score)).scalars().all()
        latest_score = scores[0] if scores else None

        # Offers
        q_offer = select(Offer).where(Offer.business_id == business_id).order_by(Offer.created_at.desc())
        offers = (await session.execute(q_offer)).scalars().all()
        latest_offer = offers[0] if offers else None

        # Outreach messages
        q_out = select(OutreachMessage).where(OutreachMessage.business_id == business_id).order_by(OutreachMessage.created_at.desc())
        outreach_msgs = (await session.execute(q_out)).scalars().all()

        # Replies
        q_reply = select(Reply).where(Reply.business_id == business_id).order_by(Reply.received_at.desc())
        replies = (await session.execute(q_reply)).scalars().all()

        # Proposals
        q_prop = select(Proposal).where(Proposal.business_id == business_id).order_by(Proposal.created_at.desc())
        proposals = (await session.execute(q_prop)).scalars().all()

        # Payments
        q_pay = select(Payment).where(Payment.business_id == business_id).order_by(Payment.created_at.desc())
        payments = (await session.execute(q_pay)).scalars().all()

        # Meetings
        q_meet = select(Meeting).where(Meeting.business_id == business_id).order_by(Meeting.created_at.desc())
        meetings = (await session.execute(q_meet)).scalars().all()

        # Suppression check
        is_suppressed = False
        if biz.public_email:
            is_suppressed = await compliance_guard.is_suppressed(session, biz.public_email)

        target_val = latest_offer.recommended_price if latest_offer else getattr(settings, "TARGET_OFFER_MINIMUM_USD", 1000.0)
        target_val = max(target_val, getattr(settings, "TARGET_OFFER_MINIMUM_USD", 1000.0))

        audit_data = {}
        if latest_audit:
            audit_findings = []
            for f in (latest_audit.findings or []):
                if hasattr(f, "finding"):
                    audit_findings.append({
                        "finding": f.finding,
                        "category": f.category,
                        "severity": f.severity,
                        "recommended_fix": f.recommended_fix
                    })
                elif isinstance(f, dict):
                    audit_findings.append(f)
            audit_data = {
                "id": latest_audit.id,
                "performance_score": latest_audit.performance_score,
                "accessibility_score": getattr(latest_audit, "a11y_score", 50.0),
                "a11y_score": getattr(latest_audit, "a11y_score", 50.0),
                "seo_score": latest_audit.seo_score,
                "findings": audit_findings,
                "audited_at": latest_audit.audited_at.isoformat() if latest_audit.audited_at else None,
                "created_at": latest_audit.audited_at.isoformat() if latest_audit.audited_at else None
            }
        elif memory and memory.audit_results:
            audit_data = memory.audit_results

        # Assemble conversation history with fallback to outreach messages and replies
        conv_hist = list(memory.conversation_history) if (memory and memory.conversation_history) else []
        if not conv_hist:
            for msg in sorted(outreach_msgs, key=lambda m: m.created_at or datetime.min):
                conv_hist.append({
                    "sender": "AGENT",
                    "message": msg.body,
                    "subject": msg.subject,
                    "timestamp": msg.sent_at.isoformat() if msg.sent_at else (msg.created_at.isoformat() if msg.created_at else None)
                })
            for rep in sorted(replies, key=lambda r: r.received_at or datetime.min):
                conv_hist.append({
                    "sender": "PROSPECT",
                    "message": rep.raw_body,
                    "timestamp": rep.received_at.isoformat() if rep.received_at else None
                })
                if rep.suggested_response:
                    conv_hist.append({
                        "sender": "AGENT",
                        "message": rep.suggested_response,
                        "intent": rep.classification,
                        "timestamp": rep.received_at.isoformat() if rep.received_at else None
                    })

        snapshot = {
            "business_id": biz.id,
            "name": biz.name,
            "domain": biz.domain,
            "niche": biz.niche,
            "city": biz.city,
            "country": biz.country,
            "public_email": biz.public_email,
            "phone": biz.phone,
            "website_url": biz.website_url,
            "pipeline_stage": biz.pipeline_stage.value if hasattr(biz.pipeline_stage, "value") else str(biz.pipeline_stage),
            "human_takeover": getattr(biz, "human_takeover", False),
            "verification_status": biz.verification_status.value if hasattr(biz.verification_status, "value") else str(biz.verification_status),
            "is_suppressed": is_suppressed,
            "audit": audit_data,
            "latest_score": {
                "total_score": latest_score.total_score if latest_score else (memory.buyer_score if memory else 0.0),
                "buyer_intent_score": getattr(latest_score, "buyer_intent_score", getattr(latest_score, "ability_to_pay_subscore", 0.0)) if latest_score else 0.0,
                "opportunity_score": getattr(latest_score, "opportunity_score", getattr(latest_score, "conversion_opportunity_subscore", (memory.opportunity_score if memory else 0.0))) if latest_score else (memory.opportunity_score if memory else 0.0),
                "priority": getattr(latest_score, "priority", "LOW") if latest_score else "LOW"
            } if (latest_score or memory) else None,
            "current_offer": {
                "title": latest_offer.title if latest_offer else (memory.offer_proposal.get("title") if memory and memory.offer_proposal else "Turnaround & Optimization Package"),
                "recommended_price": target_val,
                "service_type": latest_offer.service_type if latest_offer else "Performance Turnaround",
                "deliverables": latest_offer.deliverables if latest_offer else ["Core Web Vitals remediation", "Mobile CTA optimization"],
            },
            "conversation": {
                "last_interaction": memory.last_interaction if memory else "",
                "next_expected_action": memory.next_expected_action if memory else "AWAITING_INBOUND_EVENT",
                "history": conv_hist,
            },
            "objections": {
                "history": memory.objection_history if memory else [],
            },
            "proposals": [
                {
                    "id": p.id,
                    "title": p.title,
                    "total_value": p.total_value,
                    "advance_required": p.advance_required,
                    "status": p.status,
                    "created_at": p.created_at.isoformat() if p.created_at else None
                }
                for p in proposals
            ],
            "payments": [
                {
                    "id": pay.id,
                    "amount": pay.amount,
                    "currency": pay.currency,
                    "status": pay.status,
                    "reference_id": pay.reference_id,
                    "created_at": pay.created_at.isoformat() if pay.created_at else None
                }
                for pay in payments
            ],
            "meetings": [
                {
                    "id": m.id,
                    "title": m.title,
                    "scheduled_time": m.scheduled_time.isoformat() if m.scheduled_time else None,
                    "status": m.status,
                    "notes": m.notes
                }
                for m in meetings
            ],
            "human_decisions": memory.human_decisions if memory else [],
            "outreach_count": len(outreach_msgs),
            "reply_count": len(replies),
            "updated_at": memory.updated_at.isoformat() if memory and memory.updated_at else datetime.utcnow().isoformat()
        }
        return snapshot

    @classmethod
    async def record_human_decision(
        cls,
        session: AsyncSession,
        *,
        business_id: int,
        decision: str,  # APPROVE, EDIT, REJECT, TAKE_OVER
        edited_text: Optional[str] = None,
        operator: str = "owner"
    ) -> Dict[str, Any]:
        """Records owner decision on AI-drafted reply."""
        biz = await session.get(Business, business_id)
        if not biz:
            return {"status": "ERROR", "message": f"Business #{business_id} not found."}

        q_mem = select(ProspectMemory).where(ProspectMemory.business_id == business_id)
        memory = (await session.execute(q_mem)).scalars().first()
        if not memory:
            memory = await cls.save_memory(session, business_id=biz.id, domain=biz.domain)

        dec_record = {
            "decision": decision,
            "operator": operator,
            "edited_text": edited_text,
            "timestamp": datetime.utcnow().isoformat()
        }
        dec_list = list(memory.human_decisions or [])
        dec_list.append(dec_record)
        memory.human_decisions = dec_list

        if decision == "TAKE_OVER":
            biz.human_takeover = True
            biz.pipeline_stage = PipelineStage.APPROVAL.value
            memory.pipeline_stage = "HUMAN_TAKEOVER"
            memory.last_interaction = f"Human operator ({operator}) took over communications."
            memory.next_expected_action = "OPERATOR_DIRECT_ENGAGEMENT"
        elif decision == "APPROVE":
            memory.last_interaction = f"Draft approved by {operator}."
            memory.next_expected_action = "AWAITING_CLIENT_RESPONSE"
        elif decision == "EDIT":
            memory.last_interaction = f"Draft edited and approved by {operator}."
            memory.next_expected_action = "AWAITING_CLIENT_RESPONSE"
        elif decision == "REJECT":
            memory.last_interaction = f"Draft rejected by {operator}."
            memory.next_expected_action = "AWAITING_OPERATOR_INSTRUCTION"

        memory.updated_at = datetime.utcnow()
        await session.commit()
        return {"status": "SUCCESS", "decision": decision, "business_id": business_id}


memory_service = ProspectMemoryService()

