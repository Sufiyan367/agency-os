"""
Deterministic Context Assembler Layer for Agency OS.

Assembles lead context for AI reasoning and operator inspection:
- CURRENT INBOUND MESSAGE
- LEAD PROFILE
- RELEVANT VERIFIED BUSINESS/AUDIT FACTS [VERIFIED FACT] / [OBSERVED EVIDENCE]
- EXACT PREVIOUS OUTBOUND [AGENCY-SAID FACT]
- RECENT CONVERSATION EVENTS [CUSTOMER-SAID FACT] / [AGENCY-SAID FACT]
- PERSISTENT MEMORY SUMMARY
- OPEN COMMITMENTS (Customer & Agency)
- ACTIVE OBJECTIONS
- COMMERCIAL STATE
- CURRENT LIFECYCLE STATE
- DO-NOT-DO SAFETY CONSTRAINTS

Crucially:
- Strictly isolates facts: AI inferences are never converted into verified facts.
- Retrieves exact text from the database instead of asking LLM to remember terms.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    Business, AuditRun, Offer, OutreachMessage, ConversationEvent,
    ProspectMemory, PipelineStage, Contact
)
from app.outreach.compliance import compliance_guard
from app.core.config import settings
from app.core.logging import logger


class ContextTag:
    VERIFIED_FACT = "[VERIFIED FACT]"
    OBSERVED_EVIDENCE = "[OBSERVED EVIDENCE]"
    CUSTOMER_SAID = "[CUSTOMER-SAID FACT]"
    AGENCY_SAID = "[AGENCY-SAID FACT]"
    AI_INFERENCE = "[AI INFERENCE]"


@dataclass
class AssembledLeadContext:
    business_id: int
    lead_profile: Dict[str, Any]
    current_inbound: Optional[Dict[str, Any]]
    verified_facts: List[str]
    observed_evidence: List[str]
    exact_previous_outbound: Optional[Dict[str, Any]]
    recent_events: List[Dict[str, Any]]
    persistent_memory_summary: Dict[str, Any]
    open_commitments: List[Dict[str, Any]]
    active_objections: List[Dict[str, Any]]
    commercial_state: Dict[str, Any]
    lifecycle_state: str
    do_not_do_constraints: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_id": self.business_id,
            "lead_profile": self.lead_profile,
            "current_inbound": self.current_inbound,
            "verified_facts": self.verified_facts,
            "observed_evidence": self.observed_evidence,
            "exact_previous_outbound": self.exact_previous_outbound,
            "recent_events": self.recent_events,
            "persistent_memory_summary": self.persistent_memory_summary,
            "open_commitments": self.open_commitments,
            "active_objections": self.active_objections,
            "commercial_state": self.commercial_state,
            "lifecycle_state": self.lifecycle_state,
            "do_not_do_constraints": self.do_not_do_constraints
        }

    def to_prompt_context(self) -> str:
        """Formats context for prompt injection with explicit truth classification."""
        sections = []

        # 1. Current Inbound
        if self.current_inbound:
            sections.append(
                f"### CURRENT INBOUND MESSAGE ({ContextTag.CUSTOMER_SAID})\n"
                f"From: {self.current_inbound.get('sender', 'Unknown')}\n"
                f"Date: {self.current_inbound.get('timestamp', 'Unknown')}\n"
                f"Body:\n{self.current_inbound.get('body', '')}\n"
            )

        # 2. Lead Profile & Verified Business Facts
        profile_lines = [
            f"- Business Name: {self.lead_profile.get('name')} {ContextTag.VERIFIED_FACT}",
            f"- Domain: {self.lead_profile.get('domain')} {ContextTag.VERIFIED_FACT}",
            f"- Location: {self.lead_profile.get('city')}, {self.lead_profile.get('country')} {ContextTag.VERIFIED_FACT}",
            f"- Industry/Niche: {self.lead_profile.get('niche')} {ContextTag.VERIFIED_FACT}"
        ]
        if self.lead_profile.get("contact_email"):
            profile_lines.append(f"- Contact Email: {self.lead_profile.get('contact_email')} {ContextTag.VERIFIED_FACT}")
        if self.lead_profile.get("phone"):
            profile_lines.append(f"- Contact Phone: {self.lead_profile.get('phone')} {ContextTag.VERIFIED_FACT}")

        sections.append(
            "### LEAD PROFILE & VERIFIED BUSINESS FACTS\n" + "\n".join(profile_lines)
        )

        # 3. Verified Audit Evidence
        if self.observed_evidence:
            evidence_lines = [f"- {e} {ContextTag.OBSERVED_EVIDENCE}" for e in self.observed_evidence]
            sections.append(
                "### VERIFIED TECHNICAL AUDIT EVIDENCE\n" + "\n".join(evidence_lines)
            )

        # 4. Exact Previous Outbound
        if self.exact_previous_outbound:
            out = self.exact_previous_outbound
            sections.append(
                f"### EXACT PREVIOUS OUTBOUND DISPATCHED ({ContextTag.AGENCY_SAID})\n"
                f"Subject: {out.get('subject')}\n"
                f"Sent At: {out.get('sent_at')}\n"
                f"Offer Presented: {out.get('offer_title')} (${out.get('quoted_price', 1000):.0f})\n"
                f"Exact Message Body:\n{out.get('body')}\n"
            )

        # 5. Recent Conversation History
        if self.recent_events:
            event_lines = []
            for ev in self.recent_events[-6:]:  # Only recent relevant events
                tag = ContextTag.CUSTOMER_SAID if ev.get("direction") == "INBOUND" else ContextTag.AGENCY_SAID
                event_lines.append(f"[{ev.get('timestamp')}] {ev.get('speaker')} ({tag}): {ev.get('content')}")
            sections.append(
                "### RECENT CONVERSATION TIMELINE\n" + "\n".join(event_lines)
            )

        # 6. Open Commitments
        if self.open_commitments:
            cmt_lines = []
            for c in self.open_commitments:
                speaker = "Customer" if c.get("commitment_type") == "CUSTOMER" else "Agency"
                due = f" (Due: {c.get('due_at')})" if c.get("due_at") else ""
                cmt_lines.append(f"- {speaker} Commitment: {c.get('description')}{due} [Status: {c.get('status')}]")
            sections.append("### OPEN COMMITMENTS\n" + "\n".join(cmt_lines))

        # 7. Objections Memory
        if self.active_objections:
            obj_lines = [
                f"- [{o.get('objection_type')}] {o.get('statement')} (Status: {o.get('status')})"
                for o in self.active_objections
            ]
            sections.append("### ACTIVE OBJECTIONS\n" + "\n".join(obj_lines))

        # 8. Commercial State
        comm = self.commercial_state
        sections.append(
            f"### COMMERCIAL STATE ({ContextTag.VERIFIED_FACT})\n"
            f"- Recommended Package: {comm.get('service_type', 'Performance Turnaround')}\n"
            f"- Fixed Price: ${comm.get('price', 1000):.0f} USD (Non-negotiable commercial floor)\n"
            f"- Proposal Status: {comm.get('proposal_status', 'NOT_CREATED')}\n"
            f"- Payment Status: {comm.get('payment_status', 'PENDING')}\n"
            f"- Demo Status: {comm.get('demo_status', 'NOT_REQUESTED')}\n"
        )

        # 9. Persistent Memory Summary
        if self.persistent_memory_summary:
            mem = self.persistent_memory_summary
            summary_items = []
            if mem.get("customer_preferences"):
                summary_items.append(f"- Customer Preferences: {', '.join(mem['customer_preferences'])}")
            if mem.get("pain_points"):
                summary_items.append(f"- Observed Pain Points: {', '.join(mem['pain_points'])}")
            if mem.get("questions"):
                summary_items.append(f"- Previously Asked Questions: {', '.join(mem['questions'])}")
            if mem.get("do_not_repeat"):
                summary_items.append(f"- Do Not Repeat: {', '.join(mem['do_not_repeat'])}")
            if summary_items:
                sections.append("### PERSISTENT MEMORY SUMMARY\n" + "\n".join(summary_items))

        # 10. Do-Not-Do Constraints
        if self.do_not_do_constraints:
            rules = [f"- {r}" for r in self.do_not_do_constraints]
            sections.append("### STRICT DO-NOT-DO SAFETY CONSTRAINTS\n" + "\n".join(rules))

        return "\n\n".join(sections)


class ContextAssembler:
    """Deterministic context building engine."""

    @classmethod
    async def assemble_context(
        cls,
        session: AsyncSession,
        business_id: int,
        *,
        current_inbound_body: Optional[str] = None,
        current_inbound_sender: Optional[str] = None,
        inbound_timestamp: Optional[str] = None
    ) -> AssembledLeadContext:
        """
        Gathers verified facts, exact outbound messages, conversation timeline,
        commitments, and commercial state for a prospect into a structured context.
        """
        # 1. Lead & Profile
        biz = await session.get(Business, business_id)
        if not biz:
            raise ValueError(f"Business #{business_id} not found")

        q_mem = select(ProspectMemory).where(ProspectMemory.business_id == business_id)
        memory = (await session.execute(q_mem)).scalars().first()

        # Contacts
        q_contact = select(Contact).where(Contact.business_id == business_id)
        contacts = (await session.execute(q_contact)).scalars().all()
        contact_name = memory.contact_name if (memory and memory.contact_name) else (contacts[0].name if contacts else None)
        contact_email = memory.contact_email if (memory and memory.contact_email) else (biz.public_email or (contacts[0].email if contacts else None))
        contact_phone = memory.contact_phone if (memory and memory.contact_phone) else (biz.phone or (contacts[0].phone if contacts else None))

        lead_profile = {
            "business_id": biz.id,
            "name": biz.name or biz.domain,
            "domain": biz.domain,
            "city": biz.city or "Unknown",
            "country": biz.country or "US",
            "niche": biz.niche or "Local Business",
            "contact_name": contact_name,
            "contact_email": contact_email,
            "phone": contact_phone,
            "website_url": biz.website_url or f"https://{biz.domain}"
        }

        # 2. Verified Facts & Observed Evidence
        verified_facts = [
            f"Business name is '{biz.name or biz.domain}'",
            f"Operating in '{biz.city or 'Unknown'}, {biz.country or 'US'}' in the '{biz.niche or 'general'}' industry",
            f"Canonical domain is '{biz.domain}'"
        ]

        observed_evidence = []
        q_audit = select(AuditRun).where(AuditRun.business_id == business_id).order_by(AuditRun.audited_at.desc())
        latest_audit = (await session.execute(q_audit)).scalars().first()

        if latest_audit:
            observed_evidence.append(f"Mobile Performance score: {latest_audit.performance_score:.0f}/100")
            observed_evidence.append(f"SEO Health score: {latest_audit.seo_score:.0f}/100")
            observed_evidence.append(f"Accessibility (a11y) score: {getattr(latest_audit, 'a11y_score', 50.0):.0f}/100")
            if latest_audit.findings:
                for f in latest_audit.findings[:4]:
                    if isinstance(f, dict):
                        observed_evidence.append(f"{f.get('category', 'Technical')}: {f.get('finding', '')}")
                    elif hasattr(f, "finding"):
                        observed_evidence.append(f"{f.category}: {f.finding}")
        elif memory and memory.audit_results:
            ar = memory.audit_results
            if "performance_score" in ar:
                observed_evidence.append(f"Mobile Performance score: {ar['performance_score']}")
            if "seo_score" in ar:
                observed_evidence.append(f"SEO Health score: {ar['seo_score']}")

        # 3. Exact Previous Outbound
        exact_outbound = None
        # Check memory exact_outbound_context first
        if memory and memory.exact_outbound_context:
            exact_outbound = memory.exact_outbound_context
        else:
            # Fall back to OutreachMessage
            q_out = select(OutreachMessage).where(OutreachMessage.business_id == business_id).order_by(OutreachMessage.created_at.desc())
            latest_msg = (await session.execute(q_out)).scalars().first()
            if latest_msg:
                # Offer
                q_offer = select(Offer).where(Offer.business_id == business_id).order_by(Offer.created_at.desc())
                offer = (await session.execute(q_offer)).scalars().first()

                exact_outbound = {
                    "outreach_message_id": latest_msg.id,
                    "recipient": latest_msg.recipient_email,
                    "subject": latest_msg.subject,
                    "body": latest_msg.body,
                    "sent_at": latest_msg.sent_at.isoformat() if latest_msg.sent_at else (latest_msg.created_at.isoformat() if latest_msg.created_at else None),
                    "offer_title": offer.title if offer else "Website Performance Turnaround",
                    "quoted_price": offer.recommended_price if (offer and offer.recommended_price) else 1000.0,
                    "service_type": offer.service_type if offer else "Web Conversion Optimization"
                }

        # 4. Recent Conversation Events
        q_events = select(ConversationEvent).where(
            ConversationEvent.business_id == business_id
        ).order_by(ConversationEvent.created_at.asc())
        raw_events = (await session.execute(q_events)).scalars().all()

        recent_events = []
        for ev in raw_events:
            speaker = "Lead" if ev.direction == "INBOUND" else "Agency"
            recent_events.append({
                "id": ev.id,
                "direction": ev.direction,
                "speaker": speaker,
                "content": ev.content,
                "event_type": ev.event_type,
                "timestamp": ev.created_at.isoformat() if ev.created_at else None
            })

        # 5. Open Commitments
        open_commitments = []
        if memory and memory.commitments:
            open_commitments = [c for c in memory.commitments if c.get("status") == "OPEN"]

        # 6. Active Objections
        active_objections = []
        if memory and memory.objection_history:
            active_objections = [o for o in memory.objection_history if o.get("status") == "OPEN"]

        # 7. Commercial State
        q_offer = select(Offer).where(Offer.business_id == business_id).order_by(Offer.created_at.desc())
        latest_offer = (await session.execute(q_offer)).scalars().first()
        price = (
            latest_offer.recommended_price if (latest_offer and latest_offer.recommended_price)
            else (memory.estimated_value if (memory and memory.estimated_value) else 1000.0)
        )

        commercial_state = {
            "price": price,
            "currency": "USD",
            "service_type": latest_offer.service_type if latest_offer else "Turnaround & Optimization",
            "proposal_status": "SENT" if biz.pipeline_stage in (PipelineStage.PROPOSAL.value, PipelineStage.MEETING.value) else "NOT_SENT",
            "payment_status": "CONFIRMED" if biz.pipeline_stage == PipelineStage.WON.value else "PENDING",
            "demo_status": "REQUESTED" if biz.pipeline_stage == PipelineStage.DEMO_REQUESTED.value else ("READY" if biz.pipeline_stage in (PipelineStage.DEMO_DELIVERED.value, PipelineStage.PROPOSAL.value) else "NOT_REQUESTED")
        }

        # 8. Memory Summary
        persistent_summary = memory.memory_summary if (memory and memory.memory_summary) else {}

        # 9. Do-Not-Do Constraints
        is_suppressed = False
        if contact_email:
            is_suppressed = await compliance_guard.is_suppressed(session, contact_email)

        constraints = [
            "Never invent facts, metrics, or diagnostic defects not present in VERIFIED FACTS or OBSERVED EVIDENCE.",
            "Never offer discounts below the approved commercial price of $1,000 USD without explicit human CEO authorization.",
            "Never contradict previous commitments or statements made by the Agency.",
            "Never repeat a question that the customer has already answered.",
            "Never promise delivery timelines shorter than 48 hours for full web turnaround."
        ]
        if is_suppressed or biz.pipeline_stage == PipelineStage.LOST.value:
            constraints.insert(0, "CRITICAL: Prospect is UNSUBSCRIBED/SUPPRESSED. DO NOT SEND OUTBOUND PITCH OR PROMOTIONAL MESSAGES.")

        current_inbound = None
        if current_inbound_body:
            current_inbound = {
                "sender": current_inbound_sender or contact_email or "Prospect",
                "body": current_inbound_body,
                "timestamp": inbound_timestamp or datetime.utcnow().isoformat()
            }

        return AssembledLeadContext(
            business_id=business_id,
            lead_profile=lead_profile,
            current_inbound=current_inbound,
            verified_facts=verified_facts,
            observed_evidence=observed_evidence,
            exact_previous_outbound=exact_outbound,
            recent_events=recent_events,
            persistent_memory_summary=persistent_summary,
            open_commitments=open_commitments,
            active_objections=active_objections,
            commercial_state=commercial_state,
            lifecycle_state=biz.pipeline_stage.value if hasattr(biz.pipeline_stage, "value") else str(biz.pipeline_stage),
            do_not_do_constraints=constraints
        )


context_assembler = ContextAssembler()
