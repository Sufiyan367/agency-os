from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.models import (
    Business, AuditRun, AuditFinding, Offer, OutreachMessage,
    OutreachStatus, LeadScore, PipelineStage
)
from app.core.config import settings
from app.core.logging import logger
from app.core.security import normalize_domain
from app.outreach.compliance import compliance_guard
from app.outreach.composer import (
    CanonicalProspect, ResearchFact, SenderIdentity, ComplianceProfile,
    ComposedEmail, EntityResolver, ResearchRepository, SolutionCatalog,
    generalized_composer, PreSendValidator
)


class OutreachPersonalizer:
    """
    Generalized B2B outreach composer and stager.
    Maintains strict separation between:
    - Canonical Prospect Identity
    - Grounded Factual Research
    - Solution Catalog Matching
    - Concise Email Copy (60–140 words)
    - Sender Identity
    - Compliance Profile Policy
    - Pre-Send Factual & Semantic Validation
    """

    def resolve_sender_identity(self) -> SenderIdentity:
        """Resolves configured sender profile without inventing personas."""
        name = getattr(settings, "OUTREACH_FROM_NAME", None) or getattr(settings, "EMAIL_FROM_NAME", None) or "Agency Operations"
        email = getattr(settings, "OUTREACH_FROM_EMAIL", None) or getattr(settings, "EMAIL_FROM", "hello@automatedagencyos.tech")
        company = getattr(settings, "COMPANY_NAME", "Agency OS")
        role = getattr(settings, "SENDER_ROLE", None)
        reply_to = getattr(settings, "EMAIL_REPLY_TO", None) or email
        return SenderIdentity(
            sender_name=name,
            sender_email=email,
            sender_company=company,
            sender_role=role,
            reply_to=reply_to
        )

    def resolve_compliance_profile(self) -> ComplianceProfile:
        """Resolves compliance disclosure policy from configuration."""
        enabled = bool(getattr(settings, "COMPLIANCE_PROFILE_ENABLED", False))
        if not enabled:
            return ComplianceProfile(enabled=False)

        addr = (getattr(settings, "PHYSICAL_POSTAL_ADDRESS", None) or getattr(settings, "CAN_SPAM_POSTAL_ADDRESS", None) or "").strip()
        KNOWN_PH = ["100 innovation way", "100 congress ave", "wilmington, de", "austin, tx"]
        if any(p in addr.lower() for p in KNOWN_PH):
            addr = None

        return ComplianceProfile(
            enabled=True,
            business_name=getattr(settings, "COMPANY_NAME", "Agency OS"),
            postal_address=addr,
            unsubscribe_text="To opt out of future communications, reply 'unsubscribe'."
        )

    def generate_message_variants(
        self,
        business: Business,
        audit: Optional[AuditRun] = None,
        findings: Optional[List[AuditFinding]] = None,
        offer: Optional[Offer] = None,
        demo_url: Optional[str] = None,
        has_empirical_evidence: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Generates generalized, concise message variants for a business.
        """
        canon_domain = normalize_domain(business.domain or "")
        prospect = CanonicalProspect(
            prospect_id=business.id,
            company_name=business.name or business.domain,
            website=business.domain,
            canonical_company_domain=canon_domain,
            recipient_email=business.public_email or "",
            recipient_name=getattr(business, "contact_name", None),
            industry=business.niche or "Commercial Services",
            city=business.city,
            country=business.country or "US",
            phone=business.phone
        )

        facts: List[ResearchFact] = []
        if findings:
            for f in findings:
                facts.append(ResearchFact(
                    prospect_id=business.id,
                    fact=f.finding,
                    source=f"audit_finding:{f.id}",
                    category="conversion" if "conversion" in f.finding.lower() else "speed",
                    metric_value=f.evidence
                ))

        capabilities = ResearchRepository.analyze_capabilities(facts)
        solution = SolutionCatalog.match_solution(prospect, facts, capabilities)
        sender = self.resolve_sender_identity()
        compliance = self.resolve_compliance_profile()

        composed = generalized_composer.compose_variants(prospect, facts, solution, sender, compliance)
        return [
            {"variant": c.variant_name, "subject": c.subject, "body": c.body, "word_count": c.word_count}
            for c in composed
        ]

    async def prepare_outreach_for_business(
        self,
        session: AsyncSession,
        business: Business,
        selected_variant: int = 0,
        auto_approve: bool = False
    ) -> OutreachMessage:
        """
        Canonical entrypoint to compose, validate, and stage outreach.
        Strictly enforces entity resolution, research fact extraction, and pre-send gates.
        """
        if not business.public_email:
            raise ValueError(f"OUTREACH_VALIDATION_FAILED: {business.name} has no public contact email.")

        canon_domain = normalize_domain(business.domain or "")
        prospect = CanonicalProspect(
            prospect_id=business.id,
            company_name=business.name or business.domain,
            website=business.domain,
            canonical_company_domain=canon_domain,
            recipient_email=business.public_email,
            recipient_name=getattr(business, "contact_name", None),
            industry=business.niche or "Commercial Services",
            city=business.city,
            country=business.country or "US",
            phone=business.phone
        )

        # 1. Deterministic Entity Resolution Gate
        entity_res = EntityResolver.resolve_and_validate(prospect)
        if not entity_res.is_valid:
            raise ValueError(f"OUTREACH_VALIDATION_FAILED: {'; '.join(entity_res.errors)}")

        # 2. Suppression Check
        if await compliance_guard.is_suppressed(session, business.public_email, domain=canon_domain):
            raise ValueError(f"OUTREACH_VALIDATION_FAILED: {business.public_email} is on suppression list.")

        # 3. Grounded Research Fact Extraction
        facts = await ResearchRepository.get_facts_for_prospect(session, business)
        capabilities = ResearchRepository.analyze_capabilities(facts)

        # 4. Generalized Solution Matching
        solution = SolutionCatalog.match_solution(prospect, facts, capabilities)

        # 5. Sender & Compliance Profile Resolution
        sender = self.resolve_sender_identity()
        compliance = self.resolve_compliance_profile()

        # 6. Concise Email Composition (60–140 words, zero internal leakages)
        composed_variants = generalized_composer.compose_variants(
            prospect=prospect,
            facts=facts,
            solution=solution,
            sender=sender,
            compliance=compliance
        )
        chosen = composed_variants[min(selected_variant, len(composed_variants) - 1)]

        # 7. Pre-Send Factual & Semantic Validation
        val_res = PreSendValidator.validate_email(chosen, prospect, sender, capabilities)
        if not val_res.is_valid:
            raise ValueError(f"OUTREACH_VALIDATION_FAILED: {'; '.join(val_res.errors)}")

        # 8. Resolve or ensure commercial offer
        offer_q = select(Offer).where(Offer.business_id == business.id)
        offer = (await session.execute(offer_q)).scalars().first()
        offer_id = offer.id if offer else None

        target_status = OutreachStatus.APPROVED.value if auto_approve else OutreachStatus.PENDING_APPROVAL.value

        # Check existing outreach message
        existing_q = select(OutreachMessage).where(
            OutreachMessage.business_id == business.id,
            OutreachMessage.status.in_([OutreachStatus.PENDING_APPROVAL.value, OutreachStatus.APPROVED.value])
        )
        msg = (await session.execute(existing_q)).scalars().first()

        if not msg:
            msg = OutreachMessage(
                business_id=business.id,
                offer_id=offer_id,
                recipient_email=prospect.recipient_email,
                subject=chosen.subject,
                body=chosen.body,
                variant_name=chosen.variant_name,
                status=target_status,
                confidence=solution.confidence,
                approved_at=datetime.utcnow() if auto_approve else None
            )
            session.add(msg)
        else:
            msg.subject = chosen.subject
            msg.body = chosen.body
            msg.variant_name = chosen.variant_name
            msg.status = target_status
            msg.confidence = solution.confidence
            if target_status == OutreachStatus.PENDING_APPROVAL.value:
                msg.approved_at = None

        business.pipeline_stage = PipelineStage.OUTREACH_READY.value if auto_approve else PipelineStage.APPROVAL.value
        await session.commit()
        await session.refresh(msg)
        logger.info(
            f"[OutreachPersonalizer] Prepared generalized outreach draft #{msg.id} "
            f"for {business.name} ({chosen.word_count} words, solution: {solution.solution_key})"
        )
        return msg

    # Compatibility alias
    personalize_and_stage_outreach = prepare_outreach_for_business


outreach_personalizer = OutreachPersonalizer()
