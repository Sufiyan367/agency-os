"""
Next-Best-Action Engine — Mega Prompt 8.
Evaluates entity state, history, policy, and timing to determine the single highest-leverage next action:
WAIT, RESEARCH, OUTREACH, FOLLOW_UP, ANSWER_QUESTION, SEND_PROPOSAL, REQUEST_REQUIREMENTS,
SCHEDULE_CALL, DEMO, PAYMENT_FOLLOWUP, ONBOARD, SUPPORT, ESCALATE, NO_ACTION.
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database.models import (
    Business, PipelineStage, Reply, Proposal, Payment,
    SupportTicket, CustomerIncident, SuppressionList, ActiveOutreachLock
)
from app.intelligence.models import (
    NextBestActionDecision, ActionType, ConfidenceBand,
    EpistemicStatus
)
from app.intelligence.lead_intelligence import lead_intelligence_engine

class NextBestActionEngine:
    """
    Synthesizes current state and policy constraints to produce explainable action recommendations.
    """

    @classmethod
    async def determine_next_action(
        cls,
        session: AsyncSession,
        business_id: int
    ) -> NextBestActionDecision:
        """
        Determines the optimal next step for a given business entity.
        """
        biz = await session.get(Business, business_id)
        if not biz:
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.NO_ACTION,
                confidence=1.0,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=0.0,
                reasoning="Entity does not exist in database.",
                evidence=[],
                policy_passed=False,
                policy_notes="INVALID_ENTITY"
            )

        # 1. Suppression / Opt-Out Check (Highest precedence)
        conditions = []
        if getattr(biz, "domain", None):
            conditions.append(SuppressionList.domain == biz.domain)
        if getattr(biz, "public_email", None):
            conditions.append(SuppressionList.email == biz.public_email)
        if conditions:
            from sqlalchemy import or_
            stmt_sup = select(SuppressionList).where(or_(*conditions))
            is_suppressed = bool((await session.execute(stmt_sup)).scalar_one_or_none())
        else:
            is_suppressed = False
        if is_suppressed:
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.NO_ACTION,
                confidence=1.0,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=0.0,
                reasoning="Prospect is on suppression list (opted out or bounced).",
                evidence=["Suppression record found."],
                policy_passed=True,
                policy_notes="COMPLIANCE_SUPPRESSED"
            )

        # 2. Check Active Support Incidents (Support takes precedence over sales)
        stmt_inc = (
            select(CustomerIncident)
            .where(CustomerIncident.business_id == business_id, CustomerIncident.is_resolved == False)
        )
        active_incidents = (await session.execute(stmt_inc)).scalars().all()
        if any(i.severity in ("SEV-1", "SEV-2") for i in active_incidents):
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.ESCALATE,
                confidence=0.95,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=95.0,
                reasoning="Critical unaddressed support incident active on account.",
                evidence=[f"Incident {i.incident_number}: {i.title}" for i in active_incidents],
                policy_passed=True,
                policy_notes="ESCALATE_CRITICAL_INCIDENT"
            )
        elif active_incidents:
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.SUPPORT,
                confidence=0.90,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=75.0,
                reasoning="Active support tickets requiring customer assistance.",
                evidence=[f"Incident {i.incident_number}" for i in active_incidents],
                policy_passed=True,
                policy_notes="RESOLVE_SUPPORT_FIRST"
            )

        stage = str(biz.pipeline_stage or "").upper()

        # 3. Canonical Post-Delivery & Production Stages
        if stage in ("WON", "DELIVERY_COMPLETE", "DELIVERED"):
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.EXPANSION_ANALYSIS,
                confidence=0.92,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=85.0,
                reasoning="Client delivery complete; evaluate legitimate operational expansion opportunities.",
                evidence=[f"Pipeline stage: {stage}"],
                policy_passed=True,
                policy_notes="ANALYZE_EXPANSION"
            )

        if stage in ("PAYMENT_CONFIRMED", "PRODUCTION_BUILD_AUTHORIZED"):
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.PRODUCTION,
                confidence=0.98,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=95.0,
                reasoning="Verified advance payment confirmed; proceed with isolated production build.",
                evidence=[f"Pipeline stage: {stage}"],
                policy_passed=True,
                policy_notes="EXECUTE_PRODUCTION_BUILD"
            )

        if stage in ("PROPOSAL_ACCEPTED", "PAYMENT_PENDING", "PAYMENT_REVIEW_REQUIRED"):
            stmt_pay = select(Payment).where(Payment.business_id == business_id).order_by(desc(Payment.id))
            pending_payment = (await session.execute(stmt_pay)).scalars().first()
            amt = float(pending_payment.amount) if pending_payment and pending_payment.amount else 0.0
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.PAYMENT,
                confidence=0.90,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=90.0,
                reasoning=f"Proposal accepted; awaiting verified payment ({stage}).",
                evidence=[f"Payment status: {pending_payment.status if pending_payment else 'PENDING'}"],
                policy_passed=True,
                policy_notes="AWAIT_VERIFIED_PAYMENT",
                commercial_value_usd=amt
            )

        # 4. Demo & Proposal Stages
        if stage == "DEMO_READY":
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.PROPOSAL,
                confidence=0.92,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=88.0,
                reasoning="Custom demo verified and ready; prepare 40% milestone proposal.",
                evidence=["Demo artifact ready in sandbox."],
                policy_passed=True,
                policy_notes="GENERATE_PROPOSAL"
            )

        if stage == "DEMO_REQUESTED" or getattr(biz, "demo_requested", False):
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.DEMO_FACTORY,
                confidence=0.95,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=92.0,
                reasoning="Explicit demo requested; trigger Demo Factory build pipeline.",
                evidence=[f"demo_requested=True, stage={stage}"],
                policy_passed=True,
                policy_notes="BUILD_DEMO"
            )

        # 5. Check Replies & Inbound History
        stmt_replies = (
            select(Reply)
            .where(Reply.business_id == business_id)
            .order_by(desc(Reply.received_at))
            .limit(1)
        )
        latest_reply = (await session.execute(stmt_replies)).scalar_one_or_none()

        if latest_reply:
            cls_name = latest_reply.classification
            reply_preview = getattr(latest_reply, "raw_body", "") or ""
            if cls_name in ("MEETING_REQUEST", "POSITIVE", "INTERESTED"):
                return NextBestActionDecision(
                    entity_type="business",
                    entity_id=business_id,
                    action=ActionType.CEO_NOTIFICATION,
                    confidence=0.95,
                    confidence_band=ConfidenceBand.HIGH,
                    priority_score=94.0,
                    reasoning="Positive prospect reply received; notify CEO and schedule consultation.",
                    evidence=[f"Reply: '{reply_preview[:100]}'"],
                    policy_passed=True,
                    policy_notes="NOTIFY_OPERATOR_HOT_LEAD"
                )
            elif cls_name in ("QUESTION", "PRICE_OBJECTION"):
                return NextBestActionDecision(
                    entity_type="business",
                    entity_id=business_id,
                    action=ActionType.PREPARE_RESPONSE,
                    confidence=0.88,
                    confidence_band=ConfidenceBand.HIGH,
                    priority_score=80.0,
                    reasoning="Prospect asked technical or commercial question; prepare response.",
                    evidence=[f"Question: '{reply_preview[:100]}'"],
                    policy_passed=True,
                    policy_notes="DRAFT_INQUIRY_RESPONSE"
                )

        # 6. Check Outreach Status (Sent vs Approval Required)
        from app.database.models import OutreachMessage
        stmt_msg = (
            select(OutreachMessage)
            .where(OutreachMessage.business_id == business_id)
            .order_by(desc(OutreachMessage.id))
            .limit(1)
        )
        latest_msg = (await session.execute(stmt_msg)).scalar_one_or_none()
        if latest_msg:
            if latest_msg.status == "SENT":
                return NextBestActionDecision(
                    entity_type="business",
                    entity_id=business_id,
                    action=ActionType.WAIT_FOR_REPLY,
                    confidence=0.90,
                    confidence_band=ConfidenceBand.HIGH,
                    priority_score=50.0,
                    reasoning="Outreach dispatched; awaiting prospect reply.",
                    evidence=[f"Message ID {latest_msg.id} sent at {latest_msg.sent_at or 'today'}"],
                    policy_passed=True,
                    policy_notes="AWAIT_PROSPECT_REPLY"
                )
            elif latest_msg.status == "PENDING_APPROVAL":
                return NextBestActionDecision(
                    entity_type="business",
                    entity_id=business_id,
                    action=ActionType.CEO_REVIEW,
                    confidence=0.92,
                    confidence_band=ConfidenceBand.HIGH,
                    priority_score=75.0,
                    reasoning="Outreach staged; operator review and approval required before dispatch.",
                    evidence=[f"Message ID {latest_msg.id} awaiting approval"],
                    policy_passed=True,
                    policy_notes="OPERATOR_SIGN_OFF_REQUIRED"
                )

        # 7. Mid-Funnel Operational Stages
        if stage in ("AUDITED", "AUDIT_COMPLETED"):
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.OPPORTUNITY_ANALYSIS,
                confidence=0.90,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=70.0,
                reasoning="Audit completed; analyze commercial fit and synthesize opportunity packet.",
                evidence=["Audit records present."],
                policy_passed=True,
                policy_notes="RUN_OPPORTUNITY_ANALYSIS"
            )

        if stage in ("RESEARCHED", "RESEARCH_COMPLETED"):
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.AUDIT,
                confidence=0.88,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=68.0,
                reasoning="Research completed; execute deterministic website and digital asset audit.",
                evidence=["Research completed."],
                policy_passed=True,
                policy_notes="TRIGGER_WEBSITE_AUDIT"
            )

        if stage in ("READY", "QUALIFIED_REPLY"):
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.PERSONALIZE,
                confidence=0.88,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=72.0,
                reasoning="Prospect qualified; personalize outreach copy with verified research.",
                evidence=[f"Stage: {stage}"],
                policy_passed=True,
                policy_notes="PERSONALIZE_OUTREACH"
            )

        # 5. Lead Intelligence Scoring Evaluation
        lead_eval = await lead_intelligence_engine.evaluate_lead(session, business_id)
        score = lead_eval["overall_score"]
        components = lead_eval["components"]

        if components["contactability"] < 40.0:
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.RESEARCH,
                confidence=0.80,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=40.0,
                reasoning="Missing verified decision-maker email or phone. Deep research required.",
                evidence=["Contactability score < 40."],
                policy_passed=True,
                policy_notes="ENRICH_CONTACT_DATA"
            )

        if score >= 70.0:
            # Check Active Lock (Slot 1)
            stmt_lock = select(ActiveOutreachLock).where(ActiveOutreachLock.slot_id == 1)
            lock = (await session.execute(stmt_lock)).scalar_one_or_none()
            if lock and lock.status == "ACTIVE" and lock.business_id != business_id:
                return NextBestActionDecision(
                    entity_type="business",
                    entity_id=business_id,
                    action=ActionType.WAIT,
                    confidence=0.90,
                    confidence_band=ConfidenceBand.HIGH,
                    priority_score=60.0,
                    reasoning="High-quality lead, but another prospect currently holds the active outreach lock.",
                    evidence=[f"Locked by Business ID {lock.business_id}"],
                    policy_passed=False,
                    policy_notes="CONCURRENCY_POLICY_WAIT_LOCK"
                )

            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.OUTREACH,
                confidence=0.85,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=score,
                reasoning=f"High commercial opportunity ({score:.0f}/100) with verified contact details.",
                evidence=lead_eval["reasons"],
                policy_passed=True,
                policy_notes="ELIGIBLE_FOR_CEO_APPROVAL"
            )

        # Default low-scoring or cold lead
        return NextBestActionDecision(
            entity_type="business",
            entity_id=business_id,
            action=ActionType.WAIT,
            confidence=0.75,
            confidence_band=ConfidenceBand.MEDIUM,
            priority_score=score,
            reasoning="Lead score below active outreach threshold. Nurturing or re-audit scheduled.",
            evidence=[f"Score {score:.0f} < 70"],
            policy_passed=True,
            policy_notes="NURTURE_OR_HOLD"
        )


next_best_action_engine = NextBestActionEngine()
