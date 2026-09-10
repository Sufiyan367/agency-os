from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import Business, AuditRun, AuditFinding, Offer, OutreachMessage, OutreachStatus, LeadScore, PipelineStage
from app.core.config import settings
from app.core.llm import llm_client
from app.outreach.compliance import compliance_guard

class OutreachPersonalizer:
    """
    Crafts hyper-personalized, evidence-grounded B2B outreach variants
    using specific technical findings from website audits.
    """

    def generate_message_variants(
        self,
        business: Business,
        audit: AuditRun,
        findings: List[AuditFinding],
        offer: Offer,
        demo_url: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        top_finding = findings[0] if findings else None
        second_finding = findings[1] if len(findings) > 1 else None

        finding_text = top_finding.finding if top_finding else "Mobile conversion pathway friction"
        evidence_text = top_finding.evidence if top_finding else "Primary call-to-action is delayed below the fold."
        fix_text = top_finding.recommended_fix if top_finding else "Deploy high-contrast sticky mobile CTA header."
        impact_text = top_finding.estimated_business_impact if top_finding else "Causes lost inbound calls and estimate requests."

        # If this is an AI Receptionist & Missed-Call Recovery offer, generate outcome-focused call recovery variants
        is_receptionist_offer = (
            offer.service_type == "AI Voice & Inbound Lead Recovery" or
            "Receptionist" in offer.title or
            "Missed-Call" in offer.title
        )

        if is_receptionist_offer:
            # Extract observable evidence
            call_evidence = evidence_text
            if "potential missed-call opportunity" in evidence_text.lower():
                evidence_summary = evidence_text.split(".")[0].strip()
            else:
                evidence_summary = f"your primary contact path relies heavily on direct telephone inquiries"

            if demo_url:
                cta_1 = f"We've set up an interactive preview showing how this would work for {business.name}: {demo_url}\n\nWould you be open to taking a brief look?"
                cta_2 = f"We can share an interactive preview of how this operates for {business.name} ({demo_url}). Would you be interested in taking a look?"
                cta_3 = f"We have an interactive preview for {business.name} available here: {demo_url}\n\nAre you the right person to review a quick 2-minute walkthrough?"
            else:
                cta_1 = f"Would you be open to exploring what an after-hours automated call recovery flow would look like for {business.name}? No obligation either way."
                cta_2 = f"Would you be open to exploring how an after-hours call recovery flow would operate for {business.name}? No obligation either way."
                cta_3 = f"Are you the right person to discuss what an after-hours call recovery setup would look like for {business.name}?"

            subj_1 = f"Question regarding inbound call handling on {business.domain}"
            body_1 = (
                f"Hi {business.name} team,\n\n"
                f"While reviewing {business.niche.replace('-', ' ')} providers in {business.city or business.country}, I was looking at {business.domain}.\n\n"
                f"We noticed that {evidence_summary}.\n\n"
                f"For a business like yours, unanswered inbound calls during busy periods or after-hours represent potential missed-call opportunities.\n\n"
                f"We build an AI receptionist that can answer, qualify, and book incoming calls when your team can't, with instant text follow-up to the caller.\n\n"
                f"{cta_1}"
            )

            subj_2 = f"Inbound inquiry recovery for {business.name}"
            body_2 = (
                f"Hi there,\n\n"
                f"I was reviewing {business.domain} and noticed your published contact flow relies directly on telephone calls.\n\n"
                f"For established businesses in {business.city or business.country}, unanswered inbound calls during peak hours or evenings can lead high-intent clients to call competing providers.\n\n"
                f"We implement an AI receptionist ({offer.title}) that answers 24/7, answers service FAQs, and books appointments directly into your schedule.\n\n"
                f"{cta_2}"
            )

            subj_3 = f"{business.name}: after-hours call capture inquiry"
            body_3 = (
                f"Hello,\n\n"
                f"I wanted to share a brief operational observation regarding {business.domain}.\n\n"
                f"We noted that {evidence_summary}.\n\n"
                f"For high-value services, unanswered inquiries represent potential missed-call opportunities. We build an AI receptionist that answers, qualifies customer inquiries, and books appointments when your staff are occupied.\n\n"
                f"{cta_3}"
            )

            return [
                {"variant": "Value-First Call Opportunity", "subject": subj_1, "body": body_1},
                {"variant": "Executive Inquiry Recovery", "subject": subj_2, "body": body_2},
                {"variant": "Direct Problem-Solution", "subject": subj_3, "body": body_3}
            ]

        # Standard variants for digital turnaround / performance offers
        subj_1 = f"Technical note on {business.domain} ({finding_text.lower()})"
        body_1 = (
            f"Hi {business.name} team,\n\n"
            f"While reviewing local websites in the {business.niche.replace('-', ' ')} space, I ran an automated diagnostic on {business.domain}.\n\n"
            f"One actionable item stood out immediately: {finding_text}.\n"
            f"Specifically: {evidence_text}\n\n"
            f"In practical terms: {impact_text}\n\n"
            f"The fix is straightforward: {fix_text}\n\n"
            f"We specialize in rapid digital remediation for firms like yours without requiring a prolonged redesign. "
            f"Would you be open to a quick 3-minute Loom video walking through our diagnostic findings and exact line-by-line recommendations?"
        )

        subj_2 = f"Quick question regarding mobile inquiries on {business.domain}"
        body_2 = (
            f"Hi there,\n\n"
            f"I was recently looking at {business.domain} on mobile and noticed a friction point that is likely depressing your inbound contact rate:\n\n"
            f"• Observation: {finding_text}\n"
            f"• Evidence: {evidence_text}\n"
            f"{f'• Secondary factor: {second_finding.finding}' if second_finding else ''}\n\n"
            f"For businesses in {business.city or business.country}, resolving high-friction mobile bottlenecks helps capture high-intent visitors who would otherwise navigate away.\n\n"
            f"We have packaged a turnkey fix ({offer.title}) that addresses this in {offer.estimated_delivery_days} days.\n\n"
            f"Would you like me to send over the full PDF audit report for your internal review? No obligation either way."
        )

        subj_3 = f"{business.name}: {finding_text}"
        body_3 = (
            f"Hello,\n\n"
            f"I wanted to share a brief technical observation regarding {business.domain}.\n\n"
            f"Our automated website audit identified {len(findings)} technical opportunities, with the most critical being:\n"
            f"\"{finding_text}\"\n\n"
            f"Details: {evidence_text}\n"
            f"Recommended solution: {fix_text}\n\n"
            f"We help commercial businesses solve these specific bottlenecks on a fixed-fee basis (${offer.recommended_price:.0f}) with transparent, fixed-scope delivery.\n\n"
            f"Are you the right person to review our technical audit summary for {business.name}?"
        )

        return [
            {"variant": "Value-First Insight", "subject": subj_1, "body": body_1},
            {"variant": "Executive Conversion Bottleneck", "subject": subj_2, "body": body_2},
            {"variant": "Direct Problem-Solution", "subject": subj_3, "body": body_3}
        ]

    async def prepare_outreach_for_business(
        self,
        session: AsyncSession,
        business: Business,
        selected_variant: int = 0,
        auto_approve: bool = False
    ) -> OutreachMessage:
        if not business.public_email:
            raise ValueError(f"Cannot generate outreach: {business.name} has no public contact email.")

        # Check suppression
        if await compliance_guard.is_suppressed(session, business.public_email):
            raise ValueError(f"Cannot generate outreach: {business.public_email} is on suppression list.")

        audit_q = select(AuditRun).where(AuditRun.business_id == business.id).order_by(AuditRun.audited_at.desc())
        audit = (await session.execute(audit_q)).scalars().first()
        if not audit:
            raise ValueError(f"Business {business.id} has not been audited yet.")

        findings_q = select(AuditFinding).where(AuditFinding.audit_id == audit.id)
        findings = (await session.execute(findings_q)).scalars().all()

        offer_q = select(Offer).where(Offer.business_id == business.id)
        offer = (await session.execute(offer_q)).scalars().first()
        if not offer:
            raise ValueError(f"Business {business.id} has no generated offer.")

        offer_price = getattr(offer, "recommended_price", 500.0) or 500.0
        if offer_price < 500.0:
            raise ValueError(f"Cannot prepare outreach: Offer value (${offer_price:.0f}) is below the $500 commercial floor.")

        # Resolve externally accessible demo URL only if configured and valid
        demo_url = None
        public_base = getattr(settings, "PUBLIC_DEMO_BASE_URL", None)
        if public_base and (public_base.startswith("http://") or public_base.startswith("https://")):
            from app.database.models import Artifact
            art_q = select(Artifact).where(
                Artifact.business_id == business.id,
                Artifact.artifact_type == "DEMO_PACKAGE"
            ).order_by(Artifact.created_at.desc())
            art = (await session.execute(art_q)).scalars().first()
            if art and art.preview_url:
                demo_url = f"{public_base.rstrip('/')}/{art.preview_url.lstrip('/')}"

        variants = self.generate_message_variants(business, audit, findings, offer, demo_url=demo_url)
        chosen = variants[min(selected_variant, len(variants) - 1)]

        # Append compliance footer
        full_body = chosen["body"] + compliance_guard.format_compliance_footer(business.name, business.public_email)

        target_status = OutreachStatus.APPROVED.value if auto_approve else OutreachStatus.PENDING_APPROVAL.value

        # Check if outreach already prepared
        existing_q = select(OutreachMessage).where(
            OutreachMessage.business_id == business.id,
            OutreachMessage.status.in_([OutreachStatus.PENDING_APPROVAL.value, OutreachStatus.APPROVED.value])
        )
        msg = (await session.execute(existing_q)).scalars().first()

        if not msg:
            msg = OutreachMessage(
                business_id=business.id,
                offer_id=offer.id,
                recipient_email=business.public_email,
                subject=chosen["subject"],
                body=full_body,
                variant_name=chosen["variant"],
                status=target_status,
                confidence=0.92
            )
            session.add(msg)
        else:
            msg.subject = chosen["subject"]
            msg.body = full_body
            msg.variant_name = chosen["variant"]
            msg.status = target_status

        business.pipeline_stage = PipelineStage.OUTREACH_READY.value if auto_approve else PipelineStage.APPROVAL.value
        await session.commit()
        return msg

    # Compatibility alias
    personalize_and_stage_outreach = prepare_outreach_for_business

outreach_personalizer = OutreachPersonalizer()
