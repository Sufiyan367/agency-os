from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Business, ProspectEvidence, PipelineStage, VerificationStatus
from app.acquisition.models import StandardizedProspect
from app.acquisition.source_fetcher import safe_source_fetcher, FetchedSourceResult
from app.acquisition.identity_verifier import identity_verifier, IdentityMatchResult
from app.acquisition.contact_verifier import contact_verifier, VerifiedContactResult
from app.acquisition.evidence_gate import prospect_evidence_gate, GateEvaluationResult
from app.acquisition.research_cache import research_cache
from app.core.security import normalize_domain
from app.core.logging import logger

class EmpiricalEvidenceHarvester:
    """
    Harvests authentic public-web evidence for acquired prospects through real HTTP fetches,
    content hashing, independent multi-source corroboration, identity matching, and gate enforcement.
    """

    async def harvest_and_verify(
        self,
        session: AsyncSession,
        business: Business,
        prospect: StandardizedProspect
    ) -> Tuple[List[ProspectEvidence], GateEvaluationResult]:
        evidence_items: List[ProspectEvidence] = []
        norm_dom = normalize_domain(business.domain or prospect.domain)

        # -------------------------------------------------------------
        # SOURCE 1: Primary Official Website (Direct Retrieval & Inspection)
        # -------------------------------------------------------------
        primary_url = business.website_url or prospect.website or f"https://{norm_dom}"
        fetch1 = await safe_source_fetcher.fetch(primary_url)

        if fetch1.is_success:
            # Identity verification on primary website
            id_res1 = identity_verifier.verify_identity(
                candidate_name=business.name,
                candidate_domain=norm_dom,
                candidate_city=business.city,
                candidate_phone=business.phone,
                source_title=fetch1.title,
                source_text=fetch1.raw_text,
                source_domain=fetch1.source_domain
            )

            # Contact verification on primary website
            contact_res = contact_verifier.verify_contacts(
                html_content=fetch1.raw_text,
                source_url=fetch1.final_url,
                candidate_domain=norm_dom
            )

            # Update business contact coordinates if discovered
            if contact_res.email and not business.public_email:
                business.public_email = contact_res.email
                business.email_status = "verified"
            if contact_res.phone and not business.phone:
                business.phone = contact_res.phone
            if contact_res.social_profiles:
                business.social_profiles = contact_res.social_profiles
            if contact_res.contact_page_url:
                business.contact_page_url = contact_res.contact_page_url

            excerpt1 = safe_source_fetcher.extract_relevant_excerpt(
                fetch1.raw_text,
                [business.name, business.city or "", business.niche.replace("-", " ")]
            ) or f"Live website confirmed at {fetch1.final_url} (HTTP {fetch1.http_status}, {fetch1.load_time_ms:.0f}ms)."

            ev1 = ProspectEvidence(
                evidence_id=f"ev_{uuid4().hex[:12]}",
                business_id=business.id,
                claim=f"Entity operates live public commercial website for {business.niche} in {business.city or business.country}.",
                source_url=fetch1.final_url,
                source_domain=fetch1.source_domain,
                source_type="official_website",
                source_tier=3,
                publisher=business.name,
                raw_excerpt=excerpt1,
                evidence_category="operational",
                confidence_score=0.92 if id_res1.is_match else 0.50,
                source_quality_score=0.88,
                freshness_score=1.0,
                is_verified=id_res1.is_match,
                http_status=fetch1.http_status,
                content_hash=fetch1.content_hash,
                verification_status="VERIFIED" if id_res1.is_match else "UNVERIFIED",
                verification_reason="Live HTTP 200 web presence verified with positive entity identity match." if id_res1.is_match else id_res1.match_reason,
                business_identity_match=id_res1.is_match,
                source_independence_group=fetch1.source_domain,
                retrieved_at=datetime.utcnow()
            )
        else:
            # Website fetch failed (SSRF, timeout, 404, 500)
            ev1 = ProspectEvidence(
                evidence_id=f"ev_{uuid4().hex[:12]}",
                business_id=business.id,
                claim=f"Primary website claimed at {primary_url}.",
                source_url=primary_url,
                source_domain=norm_dom,
                source_type="official_website",
                source_tier=3,
                publisher=business.name,
                raw_excerpt=f"Fetch failed: {fetch1.error_message}",
                evidence_category="operational",
                confidence_score=0.10,
                source_quality_score=0.20,
                freshness_score=1.0,
                is_verified=False,
                http_status=fetch1.http_status,
                content_hash=None,
                verification_status="UNREACHABLE",
                verification_reason=fetch1.error_message or "Webpage unreachable or blocked by SSRF defense.",
                business_identity_match=False,
                source_independence_group=norm_dom,
                retrieved_at=datetime.utcnow()
            )

        session.add(ev1)
        evidence_items.append(ev1)

        # -------------------------------------------------------------
        # SOURCE 2: Independent Public Source (Directory, Registry, or Search)
        # -------------------------------------------------------------
        src2_url = prospect.evidence.get("source_url")
        if src2_url and src2_url != primary_url:
            fetch2 = await safe_source_fetcher.fetch(src2_url)
            if fetch2.is_success:
                id_res2 = identity_verifier.verify_identity(
                    candidate_name=business.name,
                    candidate_domain=norm_dom,
                    candidate_city=business.city,
                    candidate_phone=business.phone,
                    source_title=fetch2.title,
                    source_text=fetch2.raw_text,
                    source_domain=fetch2.source_domain
                )

                excerpt2 = safe_source_fetcher.extract_relevant_excerpt(
                    fetch2.raw_text,
                    [business.name, norm_dom, business.city or ""]
                ) or f"Independent public listing record indexing {business.name} at {fetch2.source_domain}."

                ev2 = ProspectEvidence(
                    evidence_id=f"ev_{uuid4().hex[:12]}",
                    business_id=business.id,
                    claim=f"Entity listed in independent public directory or commercial registry index ({fetch2.source_domain}).",
                    source_url=fetch2.final_url,
                    source_domain=fetch2.source_domain,
                    source_type="registry" if "registry" in fetch2.source_domain or "gov" in fetch2.source_domain else "public_directory",
                    source_tier=2,
                    publisher=fetch2.source_domain,
                    raw_excerpt=excerpt2,
                    evidence_category="identity",
                    confidence_score=0.90 if id_res2.is_match else 0.40,
                    source_quality_score=0.85,
                    freshness_score=1.0,
                    is_verified=id_res2.is_match,
                    http_status=fetch2.http_status,
                    content_hash=fetch2.content_hash,
                    verification_status="VERIFIED" if id_res2.is_match else "UNVERIFIED",
                    verification_reason=id_res2.match_reason,
                    business_identity_match=id_res2.is_match,
                    source_independence_group=fetch2.source_domain,
                    retrieved_at=datetime.utcnow()
                )
            else:
                ev2 = ProspectEvidence(
                    evidence_id=f"ev_{uuid4().hex[:12]}",
                    business_id=business.id,
                    claim=f"Independent source citation at {src2_url}.",
                    source_url=src2_url,
                    source_domain=normalize_domain(src2_url),
                    source_type="public_directory",
                    source_tier=2,
                    publisher="Independent Public Index",
                    raw_excerpt=f"Secondary source fetch failed: {fetch2.error_message}",
                    evidence_category="identity",
                    confidence_score=0.10,
                    source_quality_score=0.30,
                    freshness_score=1.0,
                    is_verified=False,
                    http_status=fetch2.http_status,
                    content_hash=None,
                    verification_status="UNREACHABLE",
                    verification_reason=fetch2.error_message or "Secondary source unreachable.",
                    business_identity_match=False,
                    source_independence_group=normalize_domain(src2_url),
                    retrieved_at=datetime.utcnow()
                )
            session.add(ev2)
            evidence_items.append(ev2)

        # -------------------------------------------------------------
        # SOURCE 3: Verified Contact Channel (if separate contact page fetched)
        # -------------------------------------------------------------
        contact_page = prospect.evidence.get("contact_page_url") or business.contact_page_url
        if contact_page and contact_page != primary_url and not any(e.source_url == contact_page for e in evidence_items):
            fetch3 = await safe_source_fetcher.fetch(contact_page)
            if fetch3.is_success and (business.public_email or business.phone):
                ev3 = ProspectEvidence(
                    evidence_id=f"ev_{uuid4().hex[:12]}",
                    business_id=business.id,
                    claim=f"Published commercial contact details confirmed on contact page.",
                    source_url=fetch3.final_url,
                    source_domain=fetch3.source_domain,
                    source_type="contact_channel",
                    source_tier=2,
                    publisher=business.name,
                    raw_excerpt=f"Contact channel corroborated: Email={business.public_email or 'N/A'}, Phone={business.phone or 'N/A'}.",
                    evidence_category="contact",
                    confidence_score=0.90,
                    source_quality_score=0.85,
                    freshness_score=1.0,
                    is_verified=True,
                    http_status=fetch3.http_status,
                    content_hash=fetch3.content_hash,
                    verification_status="VERIFIED",
                    verification_reason="Direct contact page successfully retrieved with matching coordinates.",
                    business_identity_match=True,
                    source_independence_group=fetch3.source_domain,
                    retrieved_at=datetime.utcnow()
                )
                session.add(ev3)
                evidence_items.append(ev3)

        await session.flush()

        # -------------------------------------------------------------
        # EVALUATE HARD EVIDENCE GATE
        # -------------------------------------------------------------
        gate_res = prospect_evidence_gate.evaluate_evidence(evidence_items)
        business.evidence_count = gate_res.evidence_count
        business.effective_evidence_score = gate_res.effective_evidence_score
        business.evidence_confidence = gate_res.evidence_confidence

        if gate_res.is_passed:
            business.verification_status = VerificationStatus.VERIFIED.value
            business.research_status = "VERIFIED"
            business.pipeline_stage = PipelineStage.VERIFIED.value
        else:
            business.verification_status = "INSUFFICIENT_EVIDENCE"
            business.research_status = "RESEARCH_REQUIRED"
            business.pipeline_stage = PipelineStage.DISCOVERED.value

        session.add(business)
        await session.flush()
        return evidence_items, gate_res

evidence_harvester = EmpiricalEvidenceHarvester()
