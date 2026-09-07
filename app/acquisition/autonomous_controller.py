"""
Autonomous Acquisition Controller — Phase 15 Master State Machine.

Coordinates the continuous autonomous client-acquisition lifecycle:
RESEARCH -> QUALIFY -> SELECT -> APPROVE -> OUTREACH -> WAIT -> PROCESS_REPLY -> NEGOTIATE -> PROPOSE -> PAYMENT -> ONBOARD.

Enforces:
- MAX_ACTIVE_OUTREACH_PROSPECTS = 1 (Sequential commercial locking).
- Parallel background research across countries/niches.
- $500 absolute commercial floor.
- Automatic approval for >= $1,000 when all 16 safety checks pass.
- Restart recovery and zero duplicate outreach via idempotency keys.
- Complete decision logging in AutonomousDecisionLog.
- Emergency stop kill switch.
"""

import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, Offer, ClientIntelligenceRecord,
    OutreachMessage, OutreachStatus, PipelineStage, PipelineEvent,
    ActiveOutreachLock, AutonomousDecisionLog, Reply, Proposal, FollowupStatus,
    Artifact
)
from app.acquisition.approval_policy import auto_approval_policy, PolicyEvaluationResult
from app.acquisition.controller import active_prospect_controller
from app.acquisition.ranking import global_ranker
from app.acquisition.pool import global_prospect_pool
from app.outreach.personalization import outreach_personalizer
from app.outreach.sender import outreach_sender_adapter
from app.crm.autonomous_reply_handler import autonomous_reply_handler
from app.sales.payment_flow import payment_workflow_manager
from app.delivery.requirements_engine import requirements_engine
from app.delivery.demo_factory import demo_factory
from app.delivery.demo_qa import demo_qa_engine
from app.payments.deal_service import deal_closing_service
from app.orchestrator.pipeline_router import PaymentHandoffObject
from app.followups.engine import followup_engine
from app.core.logging import logger


class AutonomousStage(str):
    RESEARCH = "RESEARCH"
    QUALIFY = "QUALIFY"
    SELECT = "SELECT"
    APPROVE = "APPROVE"
    OUTREACH = "OUTREACH"
    WAIT = "WAIT"
    PROCESS_REPLY = "PROCESS_REPLY"
    NEGOTIATING = "NEGOTIATE"
    PROPOSE = "PROPOSE"
    PAYMENT = "PAYMENT"
    ONBOARD = "ONBOARD"


class AutonomousAcquisitionController:
    """
    Master controller executing the autonomous acquisition lifecycle.
    """

    def __init__(self):
        self.is_running: bool = False
        self.is_paused: bool = False
        self.kill_switch_active: bool = False
        self._task: Optional[asyncio.Task] = None
        self.poll_interval_seconds: float = 3.0
        self.current_action: str = "Standby"
        self.last_decision: Optional[Dict[str, Any]] = None

    async def log_decision(
        self,
        session: AsyncSession,
        action: str,
        decision: str,
        business_id: Optional[int] = None,
        policy_result: Optional[PolicyEvaluationResult] = None,
        reasons: Optional[List[str]] = None,
        evidence_ids: Optional[List[int]] = None,
        score_inputs: Optional[Dict[str, Any]] = None,
        service_id: Optional[str] = None,
        service_name: Optional[str] = None,
        price_usd: Optional[float] = None,
        previous_stage: Optional[str] = None,
        next_stage: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None
    ) -> AutonomousDecisionLog:
        """Records an auditable autonomous decision in the database."""
        log = AutonomousDecisionLog(
            business_id=business_id,
            action=action,
            decision=decision,
            policy_checklist=policy_result.checklist if policy_result else {},
            reasons=reasons or (policy_result.reasons if policy_result else []),
            evidence_ids=evidence_ids or [],
            score_inputs=score_inputs or {},
            service_id=service_id,
            service_name=service_name or (policy_result.service_name if policy_result else None),
            price_usd=price_usd or (policy_result.price_usd if policy_result else None),
            previous_stage=previous_stage,
            next_stage=next_stage,
            metadata_json=metadata_json or {}
        )
        session.add(log)
        await session.commit()
        return log

    async def get_live_status(self, session: AsyncSession) -> Dict[str, Any]:
        """Returns comprehensive live observability telemetry."""
        lock = await active_prospect_controller.get_or_create_lock(session)
        biz = await session.get(Business, lock.business_id) if lock.business_id else None

        intel = None
        offer = None
        audit = None
        if biz:
            i_stmt = select(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == biz.id)
            intel = (await session.execute(i_stmt)).scalar_one_or_none()
            o_stmt = select(Offer).where(Offer.business_id == biz.id)
            offer = (await session.execute(o_stmt)).scalars().first()
            a_stmt = select(AuditRun).where(AuditRun.business_id == biz.id).order_by(AuditRun.audited_at.desc())
            audit = (await session.execute(a_stmt)).scalars().first()

        # Revenue collected count
        from app.database.models import Payment
        rev_stmt = select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
            Payment.status.in_(["PAID", "COMPLETED"])
        )
        actual_rev = float((await session.execute(rev_stmt)).scalar() or 0.0)

        return {
            "current_action": self.current_action,
            "controller_status": "KILLED" if self.kill_switch_active else ("PAUSED" if self.is_paused else ("RUNNING" if self.is_running else "IDLE")),
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "kill_switch_active": self.kill_switch_active,
            "research_only": getattr(settings, "RESEARCH_ONLY", True),
            "autonomous_first_client": getattr(settings, "AUTONOMOUS_FIRST_CLIENT", False),
            "commercial_floor_usd": getattr(settings, "COMMERCIAL_FLOOR_USD", 500.0),
            "target_offer_minimum_usd": getattr(settings, "TARGET_OFFER_MINIMUM_USD", 1000.0),
            "slot_id": 1,
            "slot_status": lock.status,
            "slot_stage": lock.current_stage,
            "current_prospect": {
                "id": biz.id if biz else None,
                "name": biz.name if biz else "None (Standby)",
                "domain": biz.domain if biz else "None",
                "country": biz.country if biz else "None",
                "niche": biz.niche if biz else "None",
                "pipeline_stage": biz.pipeline_stage if biz else "NONE"
            },
            "evidence_status": biz.verification_status if biz else "NONE",
            "audit_status": "AUDITED" if audit else "PENDING_AUDIT",
            "audit_health_score": audit.overall_health_score if audit else None,
            "service": offer.title if offer else (intel.top_service_name if intel else "None"),
            "offer": {
                "title": offer.title if offer else None,
                "price_usd": float(offer.recommended_price) if offer and offer.recommended_price else (float(intel.recommended_price_usd) if intel and intel.recommended_price_usd else 1000.0)
            },
            "approval_reason": (lock.metadata_json or {}).get("approval_reason", "Awaiting evaluation"),
            "outreach_status": (lock.metadata_json or {}).get("outreach_status", "IDLE"),
            "reply_status": (lock.metadata_json or {}).get("reply_status", "NONE"),
            "pipeline_status": biz.pipeline_stage if biz else "IDLE",
            "payment_status": (lock.metadata_json or {}).get("payment_status", "NONE"),
            "revenue": actual_rev
        }

    async def advance_cycle_step(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Safely evaluates and advances one atomic step of the autonomous loop.
        Guarantees restart survival and idempotency.
        """
        if self.kill_switch_active or getattr(settings, "EMERGENCY_STOP", False):
            self.current_action = "Halted by emergency kill switch"
            return {"status": "HALTED", "reason": "KILL_SWITCH_ACTIVE"}

        if self.is_paused:
            self.current_action = "Paused by operator"
            return {"status": "PAUSED", "reason": "OPERATOR_PAUSE"}

        lock = await active_prospect_controller.get_or_create_lock(session)

        # -------------------------------------------------------------
        # STEP 1: If slot is IDLE -> SELECT next best prospect
        # -------------------------------------------------------------
        if lock.status in ("IDLE", "RELEASED") or lock.business_id is None:
            self.current_action = "Selecting highest-EV qualified candidate from global pool"
            logger.info("[AutonomousController] Slot 1 is idle. Querying top candidate.")
            top_cand = await global_ranker.get_top_candidate(session)
            if not top_cand:
                self.current_action = "Global pool idle; triggering background research"
                logger.info("[AutonomousController] No candidate in pool. Researching.")
                return {"status": "NO_CANDIDATE", "action": "RESEARCH_REQUIRED"}

            # Claim slot
            slot_status = await active_prospect_controller.select_next_prospect(session, business_id=top_cand.business_id)
            biz = await session.get(Business, top_cand.business_id)
            await self.log_decision(
                session=session,
                action="SELECT",
                decision="SLOT_CLAIMED",
                business_id=biz.id,
                service_id="SERVICE_001",
                reasons=top_cand.why_this_prospect,
                previous_stage="IDLE",
                next_stage=slot_status.current_stage
            )
            return {"status": "SELECTED", "business_id": biz.id, "domain": biz.domain}

        # -------------------------------------------------------------
        # STEP 2: An active prospect occupies the slot -> Check current stage
        # -------------------------------------------------------------
        biz = await session.get(Business, lock.business_id)
        if not biz:
            await active_prospect_controller.release_active_slot(session, terminal_reason="LOST", notes="Ghost lock purged")
            return {"status": "RECOVERED", "action": "PURGED_GHOST_LOCK"}

        # STAGE: SELECTED -> QUALIFY & AUTO-APPROVE
        if lock.current_stage == "SELECTED":
            self.current_action = f"Evaluating auto-approval policy for {biz.domain}"
            offer_q = select(Offer).where(Offer.business_id == biz.id).order_by(Offer.id.desc())
            offer = (await session.execute(offer_q)).scalars().first()
            if not offer:
                from app.offers.generator import offer_engine
                offer = await offer_engine.generate_offer_for_business(session, biz)

            eval_res = await auto_approval_policy.evaluate_prospect(session, biz, offer)
            self.last_decision = eval_res.model_dump()

            await self.log_decision(
                session=session,
                action="POLICY_EVALUATION",
                decision=eval_res.decision,
                business_id=biz.id,
                policy_result=eval_res,
                price_usd=eval_res.price_usd,
                service_name=eval_res.service_name,
                previous_stage="SELECTED",
                next_stage="APPROVED" if eval_res.is_auto_approved else eval_res.decision
            )

            if eval_res.decision == "BLOCK":
                logger.info(f"[AutonomousController] Prospect {biz.domain} blocked by policy: {eval_res.reasons}")
                await active_prospect_controller.release_active_slot(session, terminal_reason="REJECTED", notes="; ".join(eval_res.reasons))
                return {"status": "BLOCKED", "reasons": eval_res.reasons}

            if eval_res.decision == "HUMAN_APPROVAL_REQUIRED":
                lock.status = "WAITING_FOR_APPROVAL"
                lock.current_stage = "WAITING_FOR_APPROVAL"
                if not lock.metadata_json:
                    lock.metadata_json = {}
                lock.metadata_json["approval_reason"] = f"Price ${eval_res.price_usd:,.2f} requires human approval."
                await session.commit()
                return {"status": "AWAITING_OPERATOR_APPROVAL", "price_usd": eval_res.price_usd}

            if eval_res.is_auto_approved:
                # AUTO_APPROVE: Generate personalized outreach
                self.current_action = f"Auto-approved: Drafting outreach for {biz.domain}"
                msg = await outreach_personalizer.prepare_outreach_for_business(session, biz, auto_approve=True)
                lock.status = "APPROVED"
                lock.current_stage = "APPROVED"
                if not lock.metadata_json:
                    lock.metadata_json = {}
                lock.metadata_json["message_id"] = msg.id
                lock.metadata_json["approval_reason"] = "All 16 policy safety checks passed; offer >= $1,000."
                await session.commit()
                return {"status": "AUTO_APPROVED", "message_id": msg.id}

        # STAGE: APPROVED -> OUTREACH DISPATCH
        if lock.current_stage == "APPROVED":
            msg_id = (lock.metadata_json or {}).get("message_id")
            self.current_action = f"Dispatching outreach message {msg_id} to {biz.domain}"

            # Idempotency Guard: Verify outreach not already sent
            msg = await session.get(OutreachMessage, msg_id) if msg_id else None
            if msg and msg.status == OutreachStatus.SENT.value:
                logger.warning(f"[AutonomousController] Outreach {msg_id} already marked SENT. Skipping dispatch to prevent duplicate.")
                lock.status = "WAITING_FOR_REPLY"
                lock.current_stage = "SENT"
                await session.commit()
                return {"status": "ALREADY_SENT", "message_id": msg_id}

            send_res = await active_prospect_controller.approve_and_send(
                session=session,
                business_id=biz.id,
                message_id=msg_id,
                force_live=not getattr(settings, "RESEARCH_ONLY", True)
            )

            await self.log_decision(
                session=session,
                action="OUTREACH_DISPATCH",
                decision="SENT",
                business_id=biz.id,
                price_usd=float(biz.pipeline_events[-1].deal_value) if biz.pipeline_events else 1000.0,
                reasons=[f"Dispatched via provider: {send_res.get('send_result', {}).get('provider', 'dry_run')}"],
                previous_stage="APPROVED",
                next_stage="SENT",
                metadata_json={"research_only": getattr(settings, "RESEARCH_ONLY", True)}
            )

            return {"status": "DISPATCHED", "send_result": send_res}

        # STAGE: WAITING_FOR_REPLY / SENT -> Waiting or Process Reply
        if lock.current_stage in ("SENT", "WAITING_FOR_REPLY"):
            reply_q = select(Reply).where(Reply.business_id == biz.id).order_by(Reply.id.desc())
            latest_reply = (await session.execute(reply_q)).scalars().first()
            if latest_reply and latest_reply.classification == "INTERESTED":
                return await self._step_process_reply(
                    session=session,
                    business_id=biz.id,
                    reply_category=latest_reply.classification,
                    reply_body=latest_reply.raw_body
                )

            self.current_action = f"Awaiting prospect reply from {biz.domain} (sequential slot locked)"
            return {"status": "WAITING_FOR_REPLY", "domain": biz.domain}

        # STAGE: NEGOTIATING / PROPOSAL_READY -> Awaiting proposal acceptance
        if lock.current_stage in ("REPLIED", "NEGOTIATING", "PROPOSAL_READY"):
            self.current_action = f"Active commercial dialogue with {biz.domain}"
            return {"status": "NEGOTIATING", "domain": biz.domain}

        return {"status": "HOLDING", "current_stage": lock.current_stage}

    async def _step_process_reply(
        self,
        session: AsyncSession,
        business_id: int,
        reply_category: str = "INTERESTED",
        reply_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes an inbound prospect reply in the autonomous acquisition lifecycle.
        When reply_category is INTERESTED:
        INTERESTED -> RequirementsEngine -> DemoFactory -> DemoQAEngine -> DealClosingService -> Payment Handoff
        Enforces:
        - Proposal created ONLY if DemoQA passes.
        - Payments safely disabled (dry_run mode).
        - Database PipelineStage updated appropriately.
        """
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business {business_id} not found.")

        # Non-interested categories delegate to existing autonomous reply handler
        if reply_category.upper() not in ("INTERESTED", "WANTS_PROPOSAL", "WANTS_MEETING", "QUALIFIED"):
            if reply_body:
                handler_res = await autonomous_reply_handler.handle_reply(
                    session=session,
                    business_id=biz.id,
                    reply_text=reply_body
                )
                return {
                    "status": "HANDLED_NON_INTERESTED",
                    "business_id": biz.id,
                    "category": reply_category,
                    "handler_result": handler_res
                }
            return {"status": "SKIPPED_NON_INTERESTED", "business_id": biz.id, "category": reply_category}

        # -------------------------------------------------------------
        # 1. State Transition: QUALIFIED_REPLY & Follow-up Halting
        # -------------------------------------------------------------
        self.current_action = f"Processing INTERESTED reply for {biz.domain}"
        await followup_engine.cancel_pending_followups(session, business_id=biz.id, reason_status=FollowupStatus.CANCELLED_REPLY)
        biz.pipeline_stage = PipelineStage.QUALIFIED_REPLY.value
        await session.commit()

        # Query existing offer if any for pricing and context
        offer_q = select(Offer).where(Offer.business_id == biz.id).order_by(Offer.id.desc())
        offer = (await session.execute(offer_q)).scalars().first()

        # Alert event
        ceo_event = PipelineEvent(
            business_id=biz.id,
            from_stage=PipelineStage.CONTACTED.value,
            to_stage=biz.pipeline_stage,
            deal_value=float(offer.recommended_price) if offer and offer.recommended_price else 1000.0,
            note=f"[CEO ALERT] Commercial inquiry received from {biz.name}. Advancing to requirements and demo generation."
        )
        session.add(ceo_event)
        await session.commit()

        # -------------------------------------------------------------
        # 2. Requirements Synthesis via RequirementsEngine
        # -------------------------------------------------------------
        self.current_action = f"Synthesizing requirements packet for {biz.domain}"
        packet = await requirements_engine.build_requirements_packet(session, biz.id)

        # -------------------------------------------------------------
        # 3. Turnkey Demo Generation via DemoFactory
        # -------------------------------------------------------------
        self.current_action = f"Generating turnkey demo package for {biz.domain}"
        demo_result = await demo_factory.generate_demo_package(session, biz.id, packet)

        # -------------------------------------------------------------
        # 4. Automated Deterministic Quality Assurance via DemoQAEngine
        # -------------------------------------------------------------
        self.current_action = f"Running automated QA on demo for {biz.domain}"
        qa_result = demo_qa_engine.validate_demo(demo_result, packet)

        # Attach QA result directly to the persistent artifact record metadata
        if demo_result.artifact_id:
            art = await session.get(Artifact, demo_result.artifact_id)
            if art:
                meta = dict(art.metadata_json or {})
                meta["qa_result"] = qa_result.model_dump()
                art.metadata_json = meta
                await session.commit()

        # Gate: A failed QA strictly prevents proposal creation
        if not qa_result.overall_passed:
            logger.warning(
                f"[AutonomousController] Demo QA failed for {biz.domain}: {qa_result.error_summary}. Proposal creation blocked."
            )
            await self.log_decision(
                session=session,
                action="DEMO_QA_EVALUATION",
                decision="QA_FAILED",
                business_id=biz.id,
                reasons=[qa_result.error_summary or "Quality gates failed"],
                previous_stage=PipelineStage.QUALIFIED_REPLY.value,
                next_stage=biz.pipeline_stage,
                metadata_json={"demo_id": demo_result.demo_id, "failed_checks": qa_result.failed_checks}
            )
            return {
                "status": "QA_FAILED",
                "business_id": biz.id,
                "domain": biz.domain,
                "requirements_generated": True,
                "requirements_packet": packet,
                "demo_generated": True,
                "demo_result": demo_result,
                "qa_passed": False,
                "qa_result": qa_result,
                "error_summary": qa_result.error_summary,
                "proposal_created": False,
                "proposal_id": None,
                "payment_handoff": None
            }

        # -------------------------------------------------------------
        # 5. Commercial Proposal Creation (Only after QA passes!)
        # -------------------------------------------------------------
        self.current_action = f"Preparing commercial proposal for {biz.domain}"
        biz.pipeline_stage = PipelineStage.PROPOSAL.value
        await session.commit()

        proposal_title = offer.title if offer else packet.service_title
        catalog_price = float(offer.recommended_price) if offer and offer.recommended_price else packet.catalog_price_usd

        prop_q = select(Proposal).where(Proposal.business_id == biz.id).order_by(Proposal.created_at.desc())
        proposal = (await session.execute(prop_q)).scalars().first()
        if not proposal:
            proposal = await deal_closing_service.create_proposal(
                session=session,
                business_id=biz.id,
                title=proposal_title,
                total_value=catalog_price,
                advance_required=packet.advance_amount_usd,
                service_type=getattr(offer, "service_type", "Speed Optimization") if offer else "Speed Optimization",
                is_mock=True
            )

        # -------------------------------------------------------------
        # 6. Payment Handoff (Safe, payments disabled, dry_run mode)
        # -------------------------------------------------------------
        handoff = PaymentHandoffObject(
            business_id=biz.id,
            business_name=biz.name or biz.domain,
            domain=biz.domain,
            service_title=proposal_title,
            catalog_price_usd=catalog_price,
            advance_required_usd=packet.advance_amount_usd,
            currency="USD",
            proposal_id=proposal.id,
            proposal_status=proposal.status,
            payment_status="PENDING_AUTHORIZATION",
            payments_enabled=settings.PAYMENTS_ENABLED,
            payment_provider="dry_run",
            approval_requirements="HUMAN_APPROVAL_REQUIRED"
        )

        lock = await active_prospect_controller.get_or_create_lock(session)
        if lock.business_id == biz.id:
            lock.current_stage = "PROPOSAL_READY"
            if not lock.metadata_json:
                lock.metadata_json = {}
            lock.metadata_json["proposal_id"] = proposal.id
            lock.metadata_json["demo_id"] = demo_result.demo_id
            lock.metadata_json["qa_signature"] = qa_result.qa_signature
            await session.commit()

        await self.log_decision(
            session=session,
            action="PROCESS_REPLY",
            decision="PROPOSAL_AND_PAYMENT_READY",
            business_id=biz.id,
            price_usd=catalog_price,
            reasons=[f"Processed {reply_category} reply; QA passed ({qa_result.passed_checks}/{qa_result.total_checks}); Proposal #{proposal.id} prepared."],
            previous_stage=PipelineStage.QUALIFIED_REPLY.value,
            next_stage=PipelineStage.PROPOSAL.value,
            metadata_json={"proposal_id": proposal.id, "demo_id": demo_result.demo_id}
        )

        return {
            "status": "SUCCESS",
            "business_id": biz.id,
            "domain": biz.domain,
            "reply_category": reply_category,
            "requirements_generated": True,
            "requirements_packet": packet,
            "demo_generated": True,
            "demo_result": demo_result,
            "qa_passed": True,
            "qa_result": qa_result,
            "proposal_created": True,
            "proposal_id": proposal.id,
            "payment_handoff": handoff
        }

    def start(self):
        """Launches continuous autonomous background controller."""
        self.is_running = True
        self.is_paused = False
        self.kill_switch_active = False
        settings.EMERGENCY_STOP = False
        self.current_action = "Autonomous controller started"
        logger.info("[AutonomousAcquisitionController] Controller started.")

    def pause(self):
        """Pauses autonomous operations."""
        self.is_paused = True
        self.current_action = "Paused by operator"
        logger.info("[AutonomousAcquisitionController] Controller paused.")

    def resume(self):
        """Resumes autonomous operations."""
        self.is_paused = False
        self.current_action = "Resumed by operator"
        logger.info("[AutonomousAcquisitionController] Controller resumed.")

    def stop(self):
        """Stops autonomous operations cleanly."""
        self.is_running = False
        self.is_paused = False
        self.current_action = "Stopped"
        logger.info("[AutonomousAcquisitionController] Controller stopped.")

    def emergency_stop(self, reason: str = "Operator Kill Switch Activated"):
        """Emergency kill switch halting all actions immediately."""
        self.is_running = False
        self.is_paused = False
        self.kill_switch_active = True
        settings.EMERGENCY_STOP = True
        settings.AUTONOMOUS_OUTREACH = False
        self.current_action = f"EMERGENCY STOP: {reason}"
        logger.warning(f"[AutonomousAcquisitionController] {self.current_action}")
        return {"status": "KILLED", "reason": reason}


autonomous_acquisition_controller = AutonomousAcquisitionController()