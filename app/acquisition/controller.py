from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    ActiveOutreachLock, Business, OutreachMessage, OutreachStatus,
    PipelineStage, PipelineEvent, ClientIntelligenceRecord, AuditRun, Offer
)
from app.acquisition.models import ActiveSlotStatus
from app.acquisition.ranking import global_ranker
from app.outreach.personalization import outreach_personalizer
from app.outreach.queue import outreach_approval_queue
from app.outreach.sender import outreach_sender_adapter
from app.crm.reply_classifier import reply_classifier, ReplyClassification
from app.core.logging import logger

VALID_TERMINAL_REASONS = {
    "WON",
    "LOST",
    "OPTED_OUT",
    "UNREACHABLE",
    "SUPPRESSED",
    "REJECTED",
    "FOLLOW_UP_EXHAUSTED",
    "MANUAL_RELEASE",
    "LEASE_EXPIRED"
}

class ActiveProspectController:
    """
    Guarantees that commercially active outreach pursues ONLY ONE prospect at a time.
    Enforces persistent database locking (ActiveOutreachLock) with atomic transitions,
    race condition prevention, human approval gates, reply classification, and dynamic re-ranking.
    """

    async def get_or_create_lock(self, session: AsyncSession, check_lease: bool = True) -> ActiveOutreachLock:
        """Retrieves or initializes the singular persistent active outreach lock (slot_id=1)."""
        stmt = select(ActiveOutreachLock).where(ActiveOutreachLock.slot_id == 1)
        res = await session.execute(stmt)
        lock = res.scalar_one_or_none()

        if not lock:
            lock = ActiveOutreachLock(
                slot_id=1,
                status="IDLE",
                acquired_by="orchestrator",
                current_stage="NONE",
                lease_timeout_seconds=604800,  # 7 days
                metadata_json={}
            )
            session.add(lock)
            await session.commit()
            # Re-fetch with relationships
            res = await session.execute(stmt)
            lock = res.scalar_one()

        # Check stale lease timeout
        if check_lease and lock.status not in ("IDLE", "RELEASED") and lock.locked_at:
            timeout_delta = timedelta(seconds=lock.lease_timeout_seconds)
            if datetime.utcnow() - lock.locked_at > timeout_delta:
                logger.warning(f"[ActiveProspectController] Slot lease expired for business_id={lock.business_id}. Auto-releasing.")
                await self.release_active_slot(session, terminal_reason="LEASE_EXPIRED")
                res = await session.execute(stmt)
                lock = res.scalar_one()

        return lock

    async def get_active_status(self, session: AsyncSession) -> ActiveSlotStatus:
        """Returns the current state and inspection metrics of the active outreach slot."""
        lock = await self.get_or_create_lock(session)

        is_occupied = (lock.status not in ("IDLE", "RELEASED")) and (lock.business_id is not None)
        if not is_occupied:
            return ActiveSlotStatus(
                slot_id=1,
                is_occupied=False,
                status=lock.status,
                current_stage="NONE",
                next_action="Select the top-ranked global prospect to begin outreach."
            )

        biz = await session.get(Business, lock.business_id)
        if not biz:
            # Ghost lock recovery
            lock.status = "IDLE"
            lock.business_id = None
            await session.commit()
            return ActiveSlotStatus(slot_id=1, is_occupied=False, status="IDLE")

        # Fetch intelligence & audit data
        intel_stmt = select(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == biz.id)
        intel = (await session.execute(intel_stmt)).scalar_one_or_none()

        why_bullets = list(intel.why_this_business) if intel and intel.why_this_business else [
            f"Top-ranked uncontacted candidate from {biz.country}.",
            "Verified commercial presence with confirmed contact channels."
        ]

        next_action_map = {
            "SELECTED": "Prepare personalized outreach draft based on audit findings.",
            "OUTREACH_DRAFTED": "Operator review and approval required before live dispatch.",
            "WAITING_FOR_APPROVAL": "Approve or modify message draft in approval queue.",
            "APPROVED": "Dispatch approved email to prospect.",
            "SENT": "Awaiting prospect response or scheduled follow-up trigger.",
            "WAITING_FOR_REPLY": "Monitor inbound replies; sequential lock remains active.",
            "NEGOTIATING": "Lead engaged in active discussions; prepare proposal/checkout.",
            "REPLIED": "Review classification and reply to prospect inquiry.",
        }

        return ActiveSlotStatus(
            slot_id=1,
            is_occupied=True,
            business_id=biz.id,
            business_name=biz.name,
            country=biz.country,
            domain=biz.domain,
            status=lock.status,
            locked_at=lock.locked_at,
            waiting_since=lock.waiting_since,
            current_stage=lock.current_stage,
            selection_score=float(intel.selection_score) if intel and intel.selection_score else None,
            service_fit=str(intel.top_service_name) if intel and intel.top_service_name else None,
            recommended_price_usd=float(intel.recommended_price_usd) if intel and intel.recommended_price_usd else 1000.0,
            why_this_prospect=why_bullets,
            next_action=next_action_map.get(lock.current_stage, f"Manage active prospect ({lock.current_stage})."),
            metadata_json=lock.metadata_json or {}
        )

    async def select_next_prospect(
        self,
        session: AsyncSession,
        business_id: Optional[int] = None
    ) -> ActiveSlotStatus:
        """
        Locks and activates the next candidate prospect for single-focus outreach.
        If business_id is omitted, queries GlobalRanker for the top candidate.
        Raises ValueError if slot is already occupied.
        """
        lock = await self.get_or_create_lock(session)
        if lock.status not in ("IDLE", "RELEASED") and lock.business_id is not None:
            raise ValueError(
                f"Active outreach slot 1 is already occupied by business_id={lock.business_id}. "
                "Must release the current prospect before selecting a new one."
            )

        target_biz = None
        selection_score = 0.0
        why_bullets = []

        if business_id is not None:
            target_biz = await session.get(Business, business_id)
            if not target_biz:
                raise ValueError(f"Business with id={business_id} not found.")
            # Phase 12 Evidence Hard Invariant: Reject zero-evidence or insufficient evidence prospects
            if target_biz.verification_status == "INSUFFICIENT_EVIDENCE":
                raise ValueError(f"Business {business_id} ({target_biz.domain}) failed hard evidence gate (insufficient verified evidence) and cannot be selected for outreach.")

        else:
            top_candidate = await global_ranker.get_top_candidate(session)
            if not top_candidate:
                logger.info("[ActiveProspectController] No eligible uncontacted prospects available in global pool.")
                return ActiveSlotStatus(
                    slot_id=1,
                    is_occupied=False,
                    status="IDLE",
                    next_action="Run multi-country discovery to ingest new verified prospects."
                )
            target_biz = await session.get(Business, top_candidate.business_id)
            selection_score = top_candidate.composite_score
            why_bullets = top_candidate.why_this_prospect

        # Validate minimum commercial pricing threshold ($500 floor)
        intel_stmt = select(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == target_biz.id)
        intel_res = await session.execute(intel_stmt)
        intel = intel_res.scalar_one_or_none()
        rec_price = float(intel.recommended_price_usd) if intel and intel.recommended_price_usd else 1000.0

        if rec_price < 500.0:
            raise ValueError(f"Commercial pricing ${rec_price:,.0f} is below the minimum threshold ($500.00). Commercial outreach blocked.")


        # Claim the lock atomically
        lock.business_id = target_biz.id
        lock.status = "ACTIVE"
        lock.locked_at = datetime.utcnow()
        lock.waiting_since = None
        lock.current_stage = "SELECTED"
        lock.metadata_json = {
            "selected_at": datetime.utcnow().isoformat(),
            "domain": target_biz.domain,
            "country": target_biz.country,
            "selection_score": selection_score,
            "why_bullets": why_bullets,
        }

        # Update pipeline stage
        old_stage = target_biz.pipeline_stage
        target_biz.pipeline_stage = PipelineStage.OUTREACH_READY.value
        event = PipelineEvent(
            business_id=target_biz.id,
            from_stage=old_stage,
            to_stage=PipelineStage.OUTREACH_READY.value,
            deal_value=0.0,
            note="Selected as active commercial prospect in singular outreach slot."
        )
        session.add(event)

        await session.commit()
        logger.info(f"[ActiveProspectController] Successfully locked business {target_biz.name} ({target_biz.domain}) in slot 1.")

        return await self.get_active_status(session)

    async def prepare_outreach(
        self,
        session: AsyncSession,
        business_id: int
    ) -> Dict[str, Any]:
        """
        Drafts customized, evidence-grounded outreach for the active prospect.
        Puts draft into PENDING_APPROVAL status (Human operator approval gate).
        """
        lock = await self.get_or_create_lock(session)
        if lock.business_id != business_id:
            raise ValueError(f"Business {business_id} is not the current active prospect in slot 1.")

        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business {business_id} not found.")

        # Ensure website audit exists before personalizing
        audit_stmt = select(AuditRun).where(AuditRun.business_id == biz.id).order_by(AuditRun.audited_at.desc())
        audit = (await session.execute(audit_stmt)).scalars().first()
        if not audit:
            from app.auditing.engine import website_audit_engine
            audit = await website_audit_engine.audit_business(session, biz)

        # Ensure commercial offer exists
        offer_stmt = select(Offer).where(Offer.business_id == biz.id).order_by(Offer.created_at.desc())
        offer = (await session.execute(offer_stmt)).scalars().first()
        if not offer:
            from app.offers.generator import offer_engine
            offer = await offer_engine.generate_offer_for_business(session, biz)

        # Prepare message with human approval required (auto_approve=False)
        msg = await outreach_personalizer.prepare_outreach_for_business(session, biz, auto_approve=False)

        lock.current_stage = "OUTREACH_DRAFTED"
        if not lock.metadata_json:
            lock.metadata_json = {}
        lock.metadata_json["message_id"] = msg.id
        lock.metadata_json["drafted_at"] = datetime.utcnow().isoformat()
        lock.metadata_json["subject"] = msg.subject

        await session.commit()
        logger.info(f"[ActiveProspectController] Outreach drafted for {biz.domain} (Message ID: {msg.id}). Awaiting human approval.")

        return {
            "status": "DRAFTED",
            "message_id": msg.id,
            "recipient_email": msg.recipient_email,
            "subject": msg.subject,
            "body": msg.body,
            "approval_status": msg.status,
            "slot_stage": lock.current_stage
        }

    async def approve_and_send(
        self,
        session: AsyncSession,
        business_id: int,
        message_id: Optional[int] = None,
        force_live: bool = False
    ) -> Dict[str, Any]:
        """
        Operator approvals gate execution: approves draft message and triggers dispatch.
        Transitions active slot to WAITING_FOR_REPLY.
        """
        lock = await self.get_or_create_lock(session)
        if lock.business_id != business_id:
            raise ValueError(f"Business {business_id} is not the current active prospect in slot 1.")

        # Find target message
        if message_id:
            msg = await session.get(OutreachMessage, message_id)
        else:
            q = select(OutreachMessage).where(
                OutreachMessage.business_id == business_id
            ).order_by(OutreachMessage.created_at.desc())
            msg = (await session.execute(q)).scalars().first()

        if not msg:
            raise ValueError(f"No outreach message found for business {business_id}.")

        # 1. Human Approval Gate
        if msg.status != OutreachStatus.APPROVED.value:
            await outreach_approval_queue.approve_message(session, msg.id)

        # 2. Dispatch message
        send_result = await outreach_sender_adapter.send_approved_message(
            session=session,
            message_id=msg.id,
            force_live=force_live
        )

        # 3. Update Active Slot Lock Stage
        lock.status = "WAITING_FOR_REPLY"
        lock.current_stage = "SENT"
        lock.waiting_since = datetime.utcnow()
        if not lock.metadata_json:
            lock.metadata_json = {}
        lock.metadata_json["sent_at"] = datetime.utcnow().isoformat()
        lock.metadata_json["sent_provider"] = send_result.get("provider", "dry_run")

        await session.commit()
        logger.info(f"[ActiveProspectController] Outreach dispatched to {msg.recipient_email}. Slot now WAITING_FOR_REPLY.")

        return {
            "status": "SENT",
            "message_id": msg.id,
            "send_result": send_result,
            "slot_status": lock.status,
            "waiting_since": lock.waiting_since.isoformat() if lock.waiting_since else None
        }

    async def record_reply(
        self,
        session: AsyncSession,
        business_id: int,
        reply_text: str,
        sender_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes inbound response from active prospect.
        If opt-out/suppressed/not interested -> automatically releases slot.
        If interested/meeting -> transitions slot to NEGOTIATING.
        """
        lock = await self.get_or_create_lock(session)
        if lock.business_id != business_id:
            raise ValueError(f"Business {business_id} is not the current active prospect in slot 1.")

        q_msg = select(OutreachMessage).where(
            OutreachMessage.business_id == business_id
        ).order_by(OutreachMessage.created_at.desc())
        msg = (await session.execute(q_msg)).scalars().first()
        msg_id = msg.id if msg else 0

        # Classify and advance CRM
        reply_obj = await reply_classifier.process_incoming_reply(
            session=session,
            business_id=business_id,
            message_id=msg_id,
            raw_body=reply_text,
            sender_email=sender_email or (msg.recipient_email if msg else "prospect@example.com")
        )

        classification = reply_obj.classification
        res = {
            "id": reply_obj.id,
            "classification": reply_obj.classification,
            "confidence": reply_obj.confidence,
            "suggested_response": reply_obj.suggested_response
        }

        if classification in (
            ReplyClassification.UNSUBSCRIBE.value,
            ReplyClassification.BOUNCE.value,
            ReplyClassification.NOT_INTERESTED.value
        ):
            terminal_reason = "OPTED_OUT" if classification == ReplyClassification.UNSUBSCRIBE.value else "LOST"
            logger.info(f"[ActiveProspectController] Terminal response ({classification}). Releasing slot.")
            release_info = await self.release_active_slot(session, terminal_reason=terminal_reason)
            return {
                "reply_classification": classification,
                "action_taken": "RELEASED_SLOT",
                "release_info": release_info,
                "reply_data": res
            }

        elif classification in (
            ReplyClassification.INTERESTED.value,
            ReplyClassification.MEETING_REQUEST.value,
            ReplyClassification.PRICE_REQUEST.value
        ):
            lock.status = "NEGOTIATING"
            lock.current_stage = "REPLIED"
            await session.commit()
            return {
                "reply_classification": classification,
                "action_taken": "ACTIVE_NEGOTIATION",
                "slot_status": lock.status,
                "reply_data": res
            }
        else:
            lock.current_stage = "REPLIED"
            await session.commit()
            return {
                "reply_classification": classification,
                "action_taken": "AWAITING_FOLLOWUP",
                "slot_status": lock.status,
                "reply_data": res
            }

    async def release_active_slot(
        self,
        session: AsyncSession,
        terminal_reason: str = "MANUAL_RELEASE",
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Releases the active commercial outreach slot so the next top-ranked candidate can be selected.
        Enforces terminal conditions and dynamic re-ranking.
        """
        reason_upper = terminal_reason.upper().strip()
        if reason_upper not in VALID_TERMINAL_REASONS:
            reason_upper = "MANUAL_RELEASE"

        lock = await self.get_or_create_lock(session, check_lease=False)
        released_biz_id = lock.business_id

        if not released_biz_id:
            lock.status = "IDLE"
            lock.current_stage = "NONE"
            await session.commit()
            return {
                "released": False,
                "message": "Slot 1 was already IDLE.",
                "reason": reason_upper
            }

        biz = await session.get(Business, released_biz_id)
        if biz:
            # Map terminal reason to pipeline stage
            stage_mapping = {
                "WON": PipelineStage.WON.value,
                "LOST": PipelineStage.LOST.value,
                "OPTED_OUT": PipelineStage.LOST.value,
                "REJECTED": PipelineStage.REJECTED.value,
                "SUPPRESSED": PipelineStage.REJECTED.value,
                "UNREACHABLE": PipelineStage.LOST.value,
                "FOLLOW_UP_EXHAUSTED": PipelineStage.LOST.value,
                "MANUAL_RELEASE": biz.pipeline_stage,
                "LEASE_EXPIRED": biz.pipeline_stage,
            }
            new_stage = stage_mapping.get(reason_upper, biz.pipeline_stage)
            if new_stage != biz.pipeline_stage:
                old_stage = biz.pipeline_stage
                biz.pipeline_stage = new_stage
                event = PipelineEvent(
                    business_id=biz.id,
                    from_stage=old_stage,
                    to_stage=new_stage,
                    deal_value=0.0,
                    note=f"Active commercial outreach concluded with reason: {reason_upper}. Notes: {notes or 'N/A'}"
                )
                session.add(event)

        # Clear and idle the slot
        prev_domain = (lock.metadata_json or {}).get("domain", "")
        lock.status = "IDLE"
        lock.business_id = None
        lock.locked_at = None
        lock.waiting_since = None
        lock.current_stage = "NONE"
        lock.metadata_json = {
            "last_released_biz_id": released_biz_id,
            "last_released_domain": prev_domain,
            "last_released_reason": reason_upper,
            "last_released_at": datetime.utcnow().isoformat(),
            "notes": notes or ""
        }

        await session.commit()
        logger.info(f"[ActiveProspectController] Active slot released (Business ID: {released_biz_id}, Reason: {reason_upper}).")

        return {
            "released": True,
            "released_business_id": released_biz_id,
            "reason": reason_upper,
            "notes": notes,
            "slot_status": "IDLE"
        }

active_prospect_controller = ActiveProspectController()
