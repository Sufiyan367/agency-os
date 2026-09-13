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

        # 3. Check Payment Status
        stmt_pay = select(Payment).where(Payment.business_id == business_id, Payment.status == "PENDING")
        pending_payment = (await session.execute(stmt_pay)).scalar_one_or_none()
        if pending_payment:
            return NextBestActionDecision(
                entity_type="business",
                entity_id=business_id,
                action=ActionType.PAYMENT_FOLLOWUP,
                confidence=0.88,
                confidence_band=ConfidenceBand.HIGH,
                priority_score=85.0,
                reasoning=f"Proposal accepted but payment ${float(pending_payment.amount):.0f} pending verification.",
                evidence=[f"Payment ID {pending_payment.id}, status: {pending_payment.status}"],
                policy_passed=True,
                policy_notes="AWAIT_VERIFIED_PAYMENT",
                commercial_value_usd=float(pending_payment.amount)
            )

        # 4. Check Replies & Inbound History
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
                    action=ActionType.SCHEDULE_CALL,
                    confidence=0.92,
                    confidence_band=ConfidenceBand.HIGH,
                    priority_score=90.0,
                    reasoning="Prospect expressed positive interest; prompt call scheduling required.",
                    evidence=[f"Reply: '{reply_preview[:100]}'"],
                    policy_passed=True,
                    policy_notes="CONVERT_HOT_LEAD"
                )
            elif cls_name in ("QUESTION", "PRICE_OBJECTION"):
                return NextBestActionDecision(
                    entity_type="business",
                    entity_id=business_id,
                    action=ActionType.ANSWER_QUESTION,
                    confidence=0.85,
                    confidence_band=ConfidenceBand.HIGH,
                    priority_score=78.0,
                    reasoning="Prospect asked a technical or pricing question.",
                    evidence=[f"Question: '{reply_preview[:100]}'"],
                    policy_passed=True,
                    policy_notes="HANDLE_INQUIRY"
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
