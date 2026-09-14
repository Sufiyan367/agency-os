"""
Unified Reply Intelligence Service for Agency OS.

Executes the complete 11-step inbound reply lifecycle:
1. Identify lead from sender email, thread_id, domain, or message ID.
2. Load persistent memory (ProspectMemory).
3. Load exact prior outbound context (never hallucinated/paraphrased).
4. Store inbound event idempotently in ConversationEvent.
5. Classify the reply (POSITIVE, NEGATIVE, QUESTION, NEEDS_HUMAN, UNSUBSCRIBE, OUT_OF_OFFICE, UNKNOWN).
6. Extract commitments, objections, preferences, questions, and pain points.
7. Update memory snapshot (memory_summary & commitments).
8. Determine lifecycle transition.
9. Determine safe next action (respecting approval gates and do-not-do constraints).
10. Persist results atomically to the database.
11. Broadcast observability events.
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database.models import (
    Business, ProspectMemory, ConversationEvent, OutreachMessage,
    PipelineStage, PipelineEvent, ChannelType, EventDirection,
    ConversationEventType, Reply
)
from app.crm.memory_service import memory_service
from app.crm.reply_classifier import reply_classifier, ReplyClassification
from app.crm.commitment_service import commitment_service, CommitmentType
from app.crm.objection_service import objection_service
from app.crm.context_assembler import context_assembler, ContextTag
from app.outreach.compliance import compliance_guard
from app.followups.engine import followup_engine, FollowupStatus
from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType
from app.core.logging import logger


class ReplyIntelligenceService:
    """Orchestrates the 11-step reply intelligence and persistent memory workflow."""

    async def handle_inbound_reply(
        self,
        session: AsyncSession,
        *,
        sender_email: str,
        body: str,
        subject: Optional[str] = None,
        thread_id: Optional[str] = None,
        provider_event_id: Optional[str] = None,
        provider: str = "inbound_email",
        idempotency_key: Optional[str] = None,
        business_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Processes an incoming prospect reply end-to-end with persistent memory reconstruction.
        """
        clean_sender = sender_email.strip().lower() if sender_email else ""
        raw_body = body.strip()

        # Step 1: Identify the lead
        biz = None
        if business_id:
            biz = await session.get(Business, business_id)

        memory = None
        if biz:
            memory = await memory_service.get_memory(session, business_id=biz.id)
        else:
            memory = await memory_service.get_memory(
                session,
                email=clean_sender,
                thread_id=thread_id,
                domain=clean_sender.split("@")[-1] if "@" in clean_sender else None
            )
            if memory:
                biz = await session.get(Business, memory.business_id)

        if not biz:
            logger.warning(f"[ReplyIntelligence] Inbound email from {clean_sender} does not match any existing lead. Ignoring.")
            return {
                "status": "UNMATCHED",
                "message": f"Sender {clean_sender} not associated with any active business.",
                "sender": clean_sender
            }

        target_biz_id = biz.id

        # Step 2: Load / Ensure persistent memory
        if not memory:
            memory = await memory_service.save_memory(
                session,
                business_id=target_biz_id,
                domain=biz.domain,
                contact_email=clean_sender,
                thread_id=thread_id,
                pipeline_stage=biz.pipeline_stage or "CONTACTED"
            )

        # Broadcast memory restored event
        await activity_broadcaster.record_event(
            session=session,
            run_id=f"REPLY-{target_biz_id}",
            event_type=AgentEventType.LEAD_CONTEXT_RECONSTRUCTED.value,
            message=f"Lead context reconstructed for {biz.name or biz.domain} (#{target_biz_id}).",
            business_id=target_biz_id,
            domain=biz.domain,
            status="SUCCESS",
            metadata_json={"business_id": target_biz_id, "domain": biz.domain, "thread_id": thread_id}
        )

        # Step 3: Load exact prior outbound context
        exact_outbound = await memory_service.get_exact_outbound_context(session, target_biz_id)

        # Step 4: Store inbound event idempotently
        ik = idempotency_key or f"inbound_{target_biz_id}_{provider_event_id or hash(raw_body)}"
        
        # Check idempotency
        existing_event_q = select(ConversationEvent).where(
            ConversationEvent.provider == provider,
            ConversationEvent.idempotency_key == ik
        )
        existing_event = (await session.execute(existing_event_q)).scalars().first()
        if existing_event:
            logger.info(f"[ReplyIntelligence] Duplicate event ignored via idempotency_key={ik}")
            return {
                "status": "DUPLICATE_IGNORED",
                "business_id": target_biz_id,
                "event_id": existing_event.id
            }

        conv_event = ConversationEvent(
            business_id=target_biz_id,
            channel=ChannelType.EMAIL.value,
            direction=EventDirection.INBOUND.value,
            provider=provider,
            provider_event_id=provider_event_id,
            event_type=ConversationEventType.REPLIED.value,
            content=raw_body,
            idempotency_key=ik,
            metadata_json={
                "sender_email": clean_sender,
                "subject": subject,
                "thread_id": thread_id
            }
        )
        session.add(conv_event)
        await session.flush()

        await activity_broadcaster.record_event(
            session=session,
            run_id=f"REPLY-{target_biz_id}",
            event_type=AgentEventType.CONVERSATION_EVENT_STORED.value,
            message=f"Inbound conversation event stored for {biz.domain} (idempotency: {ik}).",
            business_id=target_biz_id,
            domain=biz.domain,
            status="INFO",
            metadata_json={"idempotency_key": ik, "sender": clean_sender}
        )

        # Step 5: Classify the reply
        classification_res = await reply_classifier.classify_text(raw_body)
        category = classification_res.get("classification", ReplyClassification.UNKNOWN.value)
        confidence = classification_res.get("confidence", 0.85)
        reasoning = classification_res.get("reasoning", "")
        suggested_draft = classification_res.get("suggested_response", "")

        # Persist reply record
        outreach_id = exact_outbound.get("outreach_message_id") if exact_outbound else None
        reply_record = Reply(
            business_id=target_biz_id,
            outreach_message_id=outreach_id,
            sender_email=clean_sender,
            raw_body=raw_body,
            classification=category,
            confidence=confidence,
            suggested_response=suggested_draft
        )
        session.add(reply_record)

        # Step 6: Extract commitments, objections, preferences, questions, pain points
        # 6a. Commitments
        detected_cmts = commitment_service.detect_commitments_from_text(raw_body, speaker_type="CUSTOMER")
        for c in detected_cmts:
            await commitment_service.add_commitment(
                session,
                business_id=target_biz_id,
                commitment_type=CommitmentType.CUSTOMER,
                description=c["description"],
                raw_statement=c.get("raw_statement", ""),
                due_at=c.get("due_at"),
                source_event_id=str(conv_event.id)
            )

        # 6b. Objections
        from app.crm.objections import objection_detector
        detected_objs = objection_detector.detect_objections(raw_body)
        for obj_cat in detected_objs:
            if obj_cat not in (obj_cat.UNKNOWN,):
                await objection_service.record_objection(
                    session,
                    business_id=target_biz_id,
                    objection_type=obj_cat,
                    statement=raw_body,
                    source_event_id=str(conv_event.id)
                )

        # 6c. Questions
        questions = []
        for line in raw_body.split("\n"):
            line_s = line.strip()
            if "?" in line_s and len(line_s) > 5:
                questions.append(line_s)

        # Step 7: Update memory snapshot
        await memory_service.update_memory_summary(
            session,
            target_biz_id,
            questions=questions if questions else None,
            objections=[o.value for o in detected_objs] if detected_objs else None,
            commitments=[c["description"] for c in detected_cmts] if detected_cmts else None
        )

        # Step 8: Determine lifecycle transition
        old_stage = biz.pipeline_stage
        new_stage = old_stage

        if category == ReplyClassification.UNSUBSCRIBE.value:
            await compliance_guard.add_to_suppression(session, clean_sender, reason="UNSUBSCRIBE")
            await followup_engine.cancel_pending_followups(session, target_biz_id, FollowupStatus.CANCELLED_UNSUB)
            new_stage = PipelineStage.LOST.value
            memory.last_interaction = "Prospect unsubscribed. Added to permanent suppression list."
            memory.next_expected_action = "NONE_SUPPRESSED"

        elif category in (ReplyClassification.NOT_INTERESTED.value, ReplyClassification.NEGATIVE.value):
            await followup_engine.cancel_pending_followups(session, target_biz_id, FollowupStatus.CANCELLED_UNSUB)
            new_stage = PipelineStage.LOST.value
            memory.last_interaction = "Prospect declined offer (NOT_INTERESTED / NEGATIVE)."
            memory.next_expected_action = "CLOSED_AS_LOST"

        elif category == ReplyClassification.OUT_OF_OFFICE.value:
            memory.last_interaction = "Out of office automatic responder received."
            memory.next_expected_action = "AWAITING_RETURN"

        else:
            # Positive or Question
            await followup_engine.cancel_pending_followups(session, target_biz_id, FollowupStatus.CANCELLED_REPLY)

            if category == ReplyClassification.DEMO_REQUEST.value:
                new_stage = PipelineStage.DEMO_REQUESTED.value
                memory.last_interaction = "Demo requested by prospect."
                memory.next_expected_action = "BUILD_DEMO"
            elif category in (ReplyClassification.POSITIVE.value, ReplyClassification.INTERESTED.value, ReplyClassification.MEETING_REQUEST.value):
                new_stage = PipelineStage.QUALIFIED_REPLY.value
                memory.last_interaction = f"Positive reply ({category}). Awaiting meeting / proposal."
                memory.next_expected_action = "SCHEDULE_MEETING"
            elif category == ReplyClassification.QUESTION.value:
                new_stage = PipelineStage.REPLIED.value
                memory.last_interaction = "Prospect asked clarifying question."
                memory.next_expected_action = "ANSWER_QUESTION"
            else:
                new_stage = PipelineStage.REPLIED.value
                memory.last_interaction = "Inbound response received."
                memory.next_expected_action = "HUMAN_OPERATOR_REVIEW"

        biz.pipeline_stage = new_stage
        memory.pipeline_stage = new_stage

        pevent = PipelineEvent(
            business_id=target_biz_id,
            from_stage=old_stage,
            to_stage=new_stage,
            deal_value=0.0,
            note=f"Inbound reply classified as {category} ({confidence*100:.0f}% confidence): {reasoning}"
        )
        session.add(pevent)

        # Step 9: Assemble deterministic context for draft / inspection
        assembled_ctx = await context_assembler.assemble_context(
            session,
            target_biz_id,
            current_inbound_body=raw_body,
            current_inbound_sender=clean_sender
        )

        await activity_broadcaster.record_event(
            session=session,
            run_id=f"REPLY-{target_biz_id}",
            event_type=AgentEventType.REPLY_CONTEXT_ASSEMBLED.value,
            message=f"Context assembled for {biz.domain}. Stage: {new_stage}.",
            business_id=target_biz_id,
            domain=biz.domain,
            status="SUCCESS",
            metadata_json={"classification": category, "new_stage": new_stage}
        )

        # Step 10: Persist
        memory.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(biz)
        await session.refresh(memory)

        return {
            "status": "SUCCESS",
            "business_id": target_biz_id,
            "domain": biz.domain,
            "classification": category,
            "confidence": confidence,
            "new_stage": new_stage,
            "exact_outbound_recovered": bool(exact_outbound),
            "commitments_detected": len(detected_cmts),
            "objections_detected": len(detected_objs),
            "suggested_response": suggested_draft,
            "context_summary": assembled_ctx.to_dict()
        }


reply_intelligence_service = ReplyIntelligenceService()
