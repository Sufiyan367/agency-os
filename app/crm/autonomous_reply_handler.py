"""
Autonomous Reply Handler & Escalation Engine — Phase 15.

Categorizes replies into:
1. Routine categories (automated handling allowed if policy permits).
2. Escalation categories (IMMEDIATELY stops automation, flags HUMAN_REVIEW).
3. Opt-outs (immediately suppresses prospect and releases sequential lock).
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    Business, OutreachMessage, Reply, PipelineStage, PipelineEvent,
    ActiveOutreachLock
)
from app.outreach.compliance import compliance_guard
from app.core.logging import logger


class RoutineCategory(str, Enum):
    INTERESTED = "INTERESTED"
    ASKING_PRICE = "ASKING_PRICE"
    ASKING_DETAILS = "ASKING_DETAILS"
    ASKING_TIMELINE = "ASKING_TIMELINE"
    ASKING_HOW_IT_WORKS = "ASKING_HOW_IT_WORKS"
    OBJECTION = "OBJECTION"
    NOT_INTERESTED = "NOT_INTERESTED"
    LATER = "LATER"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    WRONG_CONTACT = "WRONG_CONTACT"
    ALREADY_HAVE_SOLUTION = "ALREADY_HAVE_SOLUTION"
    WANTS_PROPOSAL = "WANTS_PROPOSAL"
    WANTS_MEETING = "WANTS_MEETING"


class EscalationCategory(str, Enum):
    LEGAL_THREAT = "LEGAL_THREAT"
    COMPLAINT = "COMPLAINT"
    REGULATORY_MATTER = "REGULATORY_MATTER"
    PRIVACY_REQUEST = "PRIVACY_REQUEST"
    REFUND_DISPUTE = "REFUND_DISPUTE"
    SECURITY_ISSUE = "SECURITY_ISSUE"
    UNUSUAL_TERMS = "UNUSUAL_TERMS"
    SENSITIVE_NEGOTIATION = "SENSITIVE_NEGOTIATION"
    EXPLICIT_HUMAN_REQUEST = "EXPLICIT_HUMAN_REQUEST"


class ReplyClassificationResult(BaseModel):
    category: str
    is_escalation: bool
    is_opt_out: bool
    confidence: float
    reasoning: str
    suggested_response: Optional[str] = None
    requires_human_intervention: bool = False


class AutonomousReplyHandler:
    """
    Evaluates prospect responses, handles routine inquiries autonomously,
    strictly halts automation on sensitive topics, and suppresses opt-outs.
    """

    def classify_text(self, text: str) -> ReplyClassificationResult:
        body = text.strip()
        lower = body.lower()

        # ==============================================================
        # 1. ESCALATION CHECKS (Priority 1: Immediate Safety Filter)
        # ==============================================================
        if re.search(r"\b(lawyer|attorney|lawsuit|legal action|litigation|sue you|court|cease and desist|harassment|damages)\b", lower):
            return ReplyClassificationResult(
                category=EscalationCategory.LEGAL_THREAT.value,
                is_escalation=True,
                is_opt_out=False,
                confidence=0.98,
                reasoning="Legal threat or attorney reference detected.",
                requires_human_intervention=True
            )

        if re.search(r"\b(gdpr|ccpa|right to be forgotten|erasure request|data privacy|ico|privacy commissioner|dpo)\b", lower):
            return ReplyClassificationResult(
                category=EscalationCategory.PRIVACY_REQUEST.value,
                is_escalation=True,
                is_opt_out=True,
                confidence=0.98,
                reasoning="Formal privacy or data erasure request.",
                requires_human_intervention=True
            )

        if re.search(r"\b(ftc|fcc|can[- ]?spam|regulator|regulatory|attorney general|police|report you)\b", lower):
            return ReplyClassificationResult(
                category=EscalationCategory.REGULATORY_MATTER.value,
                is_escalation=True,
                is_opt_out=False,
                confidence=0.95,
                reasoning="Regulatory or official agency reporting reference.",
                requires_human_intervention=True
            )

        if re.search(r"\b(scam|fraud|unacceptable|awful|complaint|terrible|spammer|spamming us)\b", lower):
            return ReplyClassificationResult(
                category=EscalationCategory.COMPLAINT.value,
                is_escalation=True,
                is_opt_out=False,
                confidence=0.94,
                reasoning="High-severity formal complaint or spam accusation.",
                requires_human_intervention=True
            )

        if re.search(r"\b(refund|money back|dispute|chargeback|billing error|unauthorized charge)\b", lower):
            return ReplyClassificationResult(
                category=EscalationCategory.REFUND_DISPUTE.value,
                is_escalation=True,
                is_opt_out=False,
                confidence=0.95,
                reasoning="Refund dispute or billing grievance.",
                requires_human_intervention=True
            )

        if re.search(r"\b(vulnerability|security breach|cve|hacked|penetration|bug bounty|exploit)\b", lower):
            return ReplyClassificationResult(
                category=EscalationCategory.SECURITY_ISSUE.value,
                is_escalation=True,
                is_opt_out=False,
                confidence=0.95,
                reasoning="Security issue or disclosure.",
                requires_human_intervention=True
            )

        if re.search(r"\b(speak to a human|talk to a person|are you an ai|are you a robot|real human|manager)\b", lower):
            return ReplyClassificationResult(
                category=EscalationCategory.EXPLICIT_HUMAN_REQUEST.value,
                is_escalation=True,
                is_opt_out=False,
                confidence=0.96,
                reasoning="Explicit demand to speak to a human operator.",
                requires_human_intervention=True
            )

        if re.search(r"\b(indemnity|unlimited liability|custom nda|master service agreement|redlines|governing law)\b", lower):
            return ReplyClassificationResult(
                category=EscalationCategory.UNUSUAL_TERMS.value,
                is_escalation=True,
                is_opt_out=False,
                confidence=0.90,
                reasoning="Complex legal terms or non-standard contractual requirements.",
                requires_human_intervention=True
            )

        # ==============================================================
        # 2. OPT-OUT / UNSUBSCRIBE (Priority 2: Suppression)
        # ==============================================================
        if re.search(r"\b(unsubscribe|remove (?:me|us)|stop emailing|opt[- ]?out|take (?:me|us) off|do not contact|never email)\b", lower):
            return ReplyClassificationResult(
                category=RoutineCategory.UNSUBSCRIBE.value,
                is_escalation=False,
                is_opt_out=True,
                confidence=0.99,
                reasoning="Explicit unsubscribe or opt-out request.",
                suggested_response="Understood. You have been removed from our list."
            )

        # ==============================================================
        # 3. ROUTINE CLASSIFICATIONS
        # ==============================================================
        if re.search(r"\b(schedule|call|calendar|calendly|meet|zoom|thursday|monday|tuesday|wednesday|friday|tomorrow)\b", lower) and            any(w in lower for w in ["time", "talk", "chat", "discuss", "available", "morning", "afternoon", "connect"]):
            return ReplyClassificationResult(
                category=RoutineCategory.WANTS_MEETING.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.95,
                reasoning="Prospect requested or proposed a discussion time.",
                suggested_response="Thank you! I can do Thursday at 10:00 AM or 2:30 PM. Would either time work for a brief 10-minute overview?"
            )

        if re.search(r"\b(send (?:a )?proposal|send contract|formal quote|scope of work|sow|agreement|send invoice)\b", lower):
            return ReplyClassificationResult(
                category=RoutineCategory.WANTS_PROPOSAL.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.95,
                reasoning="Prospect requested formal commercial proposal or SOW.",
                suggested_response="I will prepare our formal implementation agreement and send it over shortly."
            )

        if re.search(r"\b(cost|pricing|price|how much|fee|quote|rates|estimate|what does it run)\b", lower):
            return ReplyClassificationResult(
                category=RoutineCategory.ASKING_PRICE.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.94,
                reasoning="Inquiry regarding service price and investment.",
                suggested_response="Our turnkey implementation packages start at $1,000 as a fixed one-time fee. Would you like to review the specific deliverables?"
            )

        if re.search(r"\b(timeline|how long|time frame|turnaround|how quickly|start date)\b", lower):
            return ReplyClassificationResult(
                category=RoutineCategory.ASKING_TIMELINE.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.92,
                reasoning="Inquiry regarding turnaround and project timeline.",
                suggested_response="Turnkey deployment typically takes 3 to 5 business days from contract authorization."
            )

        if re.search(r"\b(how does it work|what is the process|walk me through|explain how|what do you do)\b", lower):
            return ReplyClassificationResult(
                category=RoutineCategory.ASKING_HOW_IT_WORKS.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.90,
                reasoning="Inquiry regarding technical or operational process.",
                suggested_response="We conduct a non-invasive diagnostic, prepare the necessary automation assets, test in staging, and push live with zero downtime."
            )

        if re.search(r"\b(more details|more info|send information|breakdown|specifications)\b", lower):
            return ReplyClassificationResult(
                category=RoutineCategory.ASKING_DETAILS.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.90,
                reasoning="General information and specification request.",
                suggested_response="Certainly! I can provide the complete technical diagnostic and line-by-line solution breakdown."
            )

        if re.search(r"\b(wrong person|not me|not responsible|contact (?:someone|our)|reach out to)\b", lower):
            return ReplyClassificationResult(
                category=RoutineCategory.WRONG_CONTACT.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.92,
                reasoning="Recipient indicates they are not the appropriate stakeholder.",
                suggested_response="Thank you for letting me know. Could you share who handles digital infrastructure or marketing at your firm?"
            )

        if any(w in lower for w in ["already have", "already working with", "in-house", "handled internally", "have a vendor"]):
            return ReplyClassificationResult(
                category=RoutineCategory.ALREADY_HAVE_SOLUTION.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.90,
                reasoning="Prospect has an existing solution or internal team.",
                suggested_response="Understood! Glad to hear it is covered. Wishing you and your team continued success."
            )

        if any(w in lower for w in ["next quarter", "next year", "not right now", "busy right now", "check back", "in a few months"]):
            return ReplyClassificationResult(
                category=RoutineCategory.LATER.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.88,
                reasoning="Timing objection; prospect requested delayed follow-up.",
                suggested_response="Completely understand. I will make a note to follow up next quarter."
            )

        if any(w in lower for w in ["too expensive", "no budget", "tight budget", "can't afford", "cheaper"]):
            return ReplyClassificationResult(
                category=RoutineCategory.OBJECTION.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.90,
                reasoning="Budget or price objection.",
                suggested_response="We focus strictly on high-ROI remediation with predictable payback. We can discuss phased milestones if that helps."
            )

        if any(w in lower for w in ["not interested", "no thanks", "pass", "not for us", "no thank you"]):
            return ReplyClassificationResult(
                category=RoutineCategory.NOT_INTERESTED.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.92,
                reasoning="Polite or direct decline.",
                suggested_response="Thank you for considering our observation. All the best!"
            )

        if any(w in lower for w in ["interested", "sounds good", "send more", "send video", "sure", "love to see", "yes please", "tell me more"]):
            return ReplyClassificationResult(
                category=RoutineCategory.INTERESTED.value,
                is_escalation=False,
                is_opt_out=False,
                confidence=0.92,
                reasoning="Positive sentiment demonstrating interest.",
                suggested_response="Excellent. Here is our itemized diagnostic summary and proposed action plan."
            )

        # Default fallback
        return ReplyClassificationResult(
            category=RoutineCategory.ASKING_DETAILS.value,
            is_escalation=False,
            is_opt_out=False,
            confidence=0.60,
            reasoning="Unclassified routine response; default to technical details.",
            suggested_response="Thank you for the reply. How can we best assist with your technical questions?"
        )

    async def handle_incoming_reply(
        self,
        session: AsyncSession,
        business_id: int,
        raw_body: str,
        sender_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes the business workflow for an inbound reply.
        Enforces immediate escalation or opt-out suppression where appropriate.
        """
        classification = self.classify_text(raw_body)
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business {business_id} not found.")

        # Persist reply in database
        reply = Reply(
            business_id=business_id,
            channel="email",
            sender=sender_email or biz.public_email or "prospect@example.com",
            raw_body=raw_body,
            classification=classification.category,
            confidence=classification.confidence,
            suggested_response=classification.suggested_response or ""
        )
        session.add(reply)
        await session.flush()

        # Update ActiveOutreachLock
        lock_stmt = select(ActiveOutreachLock).where(ActiveOutreachLock.slot_id == 1)
        lock = (await session.execute(lock_stmt)).scalar_one_or_none()

        action_taken = "NOOP"

        # Case A: Escalation Trigger (HALT AUTOMATION)
        if classification.is_escalation:
            logger.warning(
                f"[AutonomousReplyHandler] ESCALATION triggered for {biz.domain}: {classification.category}. "
                "Halting automated communications. Requiring HUMAN_REVIEW."
            )
            old_stage = biz.pipeline_stage
            biz.pipeline_stage = PipelineStage.APPROVAL.value  # Holds for human operator
            if lock and lock.business_id == business_id:
                lock.status = "HUMAN_REVIEW"
                lock.current_stage = "ESCALATED"
                if not lock.metadata_json:
                    lock.metadata_json = {}
                lock.metadata_json["escalation_reason"] = classification.category
                lock.metadata_json["escalated_at"] = reply.created_at.isoformat()

            event = PipelineEvent(
                business_id=biz.id,
                from_stage=old_stage,
                to_stage=biz.pipeline_stage,
                deal_value=0.0,
                note=f"Automated communications halted: Escalated to human operator due to {classification.category}."
            )
            session.add(event)
            action_taken = "ESCALATED_TO_HUMAN"

        # Case B: Opt-out / Suppression
        elif classification.is_opt_out:
            logger.info(f"[AutonomousReplyHandler] Suppressing prospect {biz.domain} due to {classification.category}.")
            await compliance_guard.add_suppression(
                session=session,
                email=sender_email or biz.public_email,
                domain=biz.domain,
                reason=classification.category
            )
            old_stage = biz.pipeline_stage
            biz.pipeline_stage = PipelineStage.LOST.value
            event = PipelineEvent(
                business_id=biz.id,
                from_stage=old_stage,
                to_stage=PipelineStage.LOST.value,
                deal_value=0.0,
                note=f"Opt-out received ({classification.category}). Prospect globally suppressed."
            )
            session.add(event)

            if lock and lock.business_id == business_id:
                from app.acquisition.controller import active_prospect_controller
                await active_prospect_controller.release_active_slot(session, terminal_reason="OPTED_OUT", notes=classification.category)

            action_taken = "SUPPRESSED_AND_RELEASED"

        # Case C: Positive Intent / Commercial Interest
        elif classification.category in (
            RoutineCategory.INTERESTED.value,
            RoutineCategory.WANTS_PROPOSAL.value,
            RoutineCategory.WANTS_MEETING.value,
            RoutineCategory.ASKING_PRICE.value
        ):
            if lock and lock.business_id == business_id:
                lock.status = "NEGOTIATING"
                lock.current_stage = "REPLIED"
            old_stage = biz.pipeline_stage
            biz.pipeline_stage = PipelineStage.MEETING.value if classification.category == RoutineCategory.WANTS_MEETING.value else PipelineStage.PROPOSAL.value
            event = PipelineEvent(
                business_id=biz.id,
                from_stage=old_stage,
                to_stage=biz.pipeline_stage,
                deal_value=1000.0,
                note=f"Inbound positive reply received: {classification.category}."
            )
            session.add(event)
            action_taken = "ADVANCED_TO_NEGOTIATION"

        # Case D: Decline without formal suppression
        elif classification.category in (
            RoutineCategory.NOT_INTERESTED.value,
            RoutineCategory.ALREADY_HAVE_SOLUTION.value
        ):
            old_stage = biz.pipeline_stage
            biz.pipeline_stage = PipelineStage.LOST.value
            event = PipelineEvent(
                business_id=biz.id,
                from_stage=old_stage,
                to_stage=PipelineStage.LOST.value,
                deal_value=0.0,
                note=f"Declined with reason: {classification.category}."
            )
            session.add(event)
            if lock and lock.business_id == business_id:
                from app.acquisition.controller import active_prospect_controller
                await active_prospect_controller.release_active_slot(session, terminal_reason="LOST", notes=classification.category)
            action_taken = "SLOT_RELEASED_LOST"

        else:
            if lock and lock.business_id == business_id:
                lock.current_stage = "REPLIED"
            action_taken = "ROUTINE_FOLLOWUP_REQUIRED"

        await session.commit()

        return {
            "reply_id": reply.id,
            "classification": classification.model_dump(),
            "action_taken": action_taken,
            "pipeline_stage": biz.pipeline_stage
        }


autonomous_reply_handler = AutonomousReplyHandler()