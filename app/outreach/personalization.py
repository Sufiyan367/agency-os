from typing import List, Dict, Any, Tuple
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
        offer: Offer
    ) -> List[Dict[str, Any]]:
        top_finding = findings[0] if findings else None
        second_finding = findings[1] if len(findings) > 1 else None

        finding_text = top_finding.finding if top_finding else "Mobile conversion pathway friction"
        evidence_text = top_finding.evidence if top_finding else "Primary call-to-action is delayed below the fold."
        fix_text = top_finding.recommended_fix if top_finding else "Deploy high-contrast sticky mobile CTA header."
        impact_text = top_finding.estimated_business_impact if top_finding else "Causes lost inbound calls and estimate requests."

        # Variant 1: Value-First Technical Insight
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

        # Variant 2: Executive Conversion Bottleneck
        subj_2 = f"Quick question regarding mobile inquiries on {business.domain}"
        body_2 = (
            f"Hi there,\n\n"
            f"I was recently looking at {business.domain} on mobile and noticed a friction point that is likely depressing your inbound contact rate:\n\n"
            f"• Observation: {finding_text}\n"
            f"• Evidence: {evidence_text}\n"
            f"{f'• Secondary factor: {second_finding.finding}' if second_finding else ''}\n\n"
            f"For businesses in {business.city or business.country}, addressing this typically recaptures 15-20% of high-intent mobile visitors who otherwise bounce to a competitor.\n\n"
            f"We have packaged a turnkey fix ({offer.title}) that addresses this in {offer.estimated_delivery_days} days.\n\n"
            f"Would you like me to send over the full PDF audit report for your internal review? No obligation either way."
        )

        # Variant 3: Direct Problem-Solution
        subj_3 = f"{business.name}: {finding_text}"
        body_3 = (
            f"Hello,\n\n"
            f"I wanted to share a brief technical observation regarding {business.domain}.\n\n"
            f"Our automated website audit identified {len(findings)} technical opportunities, with the most critical being:\n"
            f"\"{finding_text}\"\n\n"
            f"Details: {evidence_text}\n"
            f"Recommended solution: {fix_text}\n\n"
            f"We help commercial businesses solve these specific bottlenecks on a fixed-fee basis (${offer.recommended_price:.0f}) with guaranteed delivery.\n\n"
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

        variants = self.generate_message_variants(business, audit, findings, offer)
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

outreach_personalizer = OutreachPersonalizer()
