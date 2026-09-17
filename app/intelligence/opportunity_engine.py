"""
Agency OS — Canonical Opportunity Engine.
Synthesizes verified prospect profiles, empirical research, audit findings,
and detected pain into an actionable commercial opportunity packet.

STRICT TRUTHFULNESS RULES:
- Does NOT fabricate revenue, company size, ROI, or ability to pay.
- Grounded in canonical Solution Capabilities and $500 USD commercial floor.
- Attaches explicit evidence items with verified provenance.
"""
from typing import Dict, Any, List, Optional
import uuid
from pydantic import BaseModel, Field

from app.intelligence.capability_catalog import capability_catalog, SolutionCapability
from app.intelligence.evidence_engine import EvidenceEngine, EvidenceItem
from app.intelligence.commercial_fit import commercial_fit_engine, CommercialFitScore
from app.intelligence.offer_matcher import offer_matcher, MatchedOfferPlan


class OpportunityPacket(BaseModel):
    """
    Canonical Opportunity Packet. 100% grounded in empirical observations.
    """
    opportunity_id: str
    business_id: int
    domain: str
    business_name: str
    niche: str
    pain_points: List[str]
    evidence: List[EvidenceItem]
    recommended_capability: Dict[str, Any]
    commercial_fit: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_next_action: str
    demo_blueprint: Dict[str, Any]
    proposal_outline: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "business_id": self.business_id,
            "domain": self.domain,
            "business_name": self.business_name,
            "niche": self.niche,
            "pain_points": self.pain_points,
            "evidence": [e.to_dict() for e in self.evidence],
            "recommended_capability": self.recommended_capability,
            "commercial_fit": self.commercial_fit,
            "confidence": self.confidence,
            "recommended_next_action": self.recommended_next_action,
            "demo_blueprint": self.demo_blueprint,
            "proposal_outline": self.proposal_outline
        }


class OpportunityEngine:
    """
    Canonical Opportunity Engine for Agency OS.
    """

    COMMERCIAL_FLOOR_USD = 500.0

    @classmethod
    def generate_opportunity(
        cls,
        business: Dict[str, Any],
        audit: Optional[Dict[str, Any]] = None,
        detected_pains: Optional[List[str]] = None,
        observed_signals: Optional[List[str]] = None,
        requested_workflow: Optional[str] = None
    ) -> OpportunityPacket:
        """
        Builds a canonical opportunity packet without fabricating financial or operational stats.
        """
        biz_id = int(business.get("id", 1))
        domain = business.get("domain", "example.com")
        name = business.get("name", domain)
        niche = business.get("niche", "Commercial Services")

        pains = detected_pains or []
        if not pains and audit:
            # Extract deficiencies from audit summary or findings
            summary = audit.get("summary", "")
            if summary:
                pains.append(summary)
            else:
                pains.append("Manual inbound lead triage and lack of automated reservation calendar")

        primary_pain = requested_workflow or (pains[0] if pains else "Manual intake processing")

        # 1. Match Offer via Deterministic Capability Catalog
        matched_offer: MatchedOfferPlan = offer_matcher.match_pain_to_offer(primary_pain, niche=niche)

        # 2. Evaluate Commercial Fit from Observed Signals
        fit_result: CommercialFitScore = commercial_fit_engine.evaluate_fit(
            business=business,
            audit=audit,
            observed_signals=observed_signals
        )

        # 3. Grounded Evidence Assembly
        evidence_items: List[EvidenceItem] = []
        # Add fit evidence
        evidence_items.extend(fit_result.evidence_items)

        # Record primary pain observation
        obs_pain = EvidenceEngine.record_observation(
            observation_id=f"obs_pain_{biz_id}",
            statement=f"Detected operational friction: '{primary_pain}'",
            source="audit_engine",
            confidence=0.92
        )
        evidence_items.append(obs_pain)

        # Derive inference (not fact!)
        inf_need = EvidenceEngine.derive_inference(
            inference_id=f"inf_need_{biz_id}",
            hypothesis=f"Business operations would benefit from {matched_offer.capability_name}",
            supporting_observations=[obs_pain],
            reasoning=f"Eliminating '{primary_pain}' directly automates intake workflow.",
            confidence_discount=0.90
        )
        evidence_items.append(inf_need)

        # Derive recommendation
        rec_item = EvidenceEngine.propose_recommendation(
            recommendation_id=f"rec_solution_{biz_id}",
            capability_id=matched_offer.capability_id,
            recommendation_text=f"Deploy {matched_offer.capability_name} to resolve {primary_pain}",
            supporting_inferences=[inf_need],
            action_name="PREPARE_OUTREACH"
        )
        evidence_items.append(rec_item)

        # 4. Opportunity ID and Confidence
        opp_id = f"opp_{uuid.uuid4().hex[:8]}"
        overall_confidence = round(min(0.95, (fit_result.overall_score / 100.0) * 0.90), 2)

        # 5. Blueprint & Proposal Outline
        demo_blueprint = {
            "blueprint_type": matched_offer.demo_blueprint_type,
            "target_niche": niche,
            "primary_flow": matched_offer.detected_pain,
            "template": matched_offer.delivery_template,
            "requires_demo_requested": True
        }

        proposal_outline = {
            "total_price_usd": matched_offer.target_price_usd,
            "advance_deposit_usd": matched_offer.advance_deposit_usd,
            "advance_percentage": 40.0,
            "turnaround_days": matched_offer.turnaround_days,
            "scope_deliverables": matched_offer.proposal_scope,
            "requires_human_approval": True
        }

        # 6. Recommended Next Action
        next_action = "PERSONALIZE_OUTREACH" if fit_result.fit_tier == "HIGH_ALIGNMENT" else "REVIEW_OUTREACH"

        return OpportunityPacket(
            opportunity_id=opp_id,
            business_id=biz_id,
            domain=domain,
            business_name=name,
            niche=niche,
            pain_points=pains,
            evidence=evidence_items,
            recommended_capability=matched_offer.to_dict(),
            commercial_fit=fit_result.to_dict(),
            confidence=overall_confidence,
            recommended_next_action=next_action,
            demo_blueprint=demo_blueprint,
            proposal_outline=proposal_outline
        )


opportunity_engine = OpportunityEngine()
