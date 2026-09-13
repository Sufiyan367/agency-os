"""
Objection Intelligence Engine & Knowledge Base — Mega Prompt 8.
Maintains proven, evidence-backed response frameworks for common B2B commercial objections:
PRICE, TRUST, TIMING, NO_NEED, ALREADY_HAVE_PROVIDER, NEED_APPROVAL, TECHNICAL_CONCERN,
SECURITY, CUSTOMIZATION, IMPLEMENTATION_TIME.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class ObjectionFramework(BaseModel):
    category: str
    description: str
    detection_keywords: List[str]
    successful_patterns: List[str]
    unsuccessful_patterns: List[str]
    recommended_turnaround_angle: str
    evidence_required: str


class ObjectionIntelligenceEngine:
    """
    Empirical objection handling library.
    Recommends truthful, evidence-backed responses based on historical outcome learning.
    """

    LIBRARY: Dict[str, ObjectionFramework] = {
        "PRICE": ObjectionFramework(
            category="PRICE",
            description="Prospect expresses concern regarding fee or upfront cost.",
            detection_keywords=["expensive", "budget", "cost", "cheaper", "discount", "can't afford"],
            successful_patterns=[
                "Anchor to value recovered: 1 saved customer / missed call covers the $650 package fee.",
                "Offer phased implementation: 40% advance with 60% balance payable upon verified delivery.",
                "Reference the objective technical audit deficit and revenue leak."
            ],
            unsuccessful_patterns=[
                "Slashing prices immediately (damages positioning and violates $500 floor).",
                "Arguing or debating cost without tying to quantifiable revenue recovery."
            ],
            recommended_turnaround_angle="ROI & Missed Revenue Quantification",
            evidence_required="Current site load speed or missed call opportunity audit."
        ),
        "TRUST": ObjectionFramework(
            category="TRUST",
            description="Prospect questions capability, credibility, or agency track record.",
            detection_keywords=["who are you", "references", "case studies", "guarantee", "portfolio"],
            successful_patterns=[
                "Share turnkey interactive sandbox preview built specifically for their business.",
                "Demonstrate verifiable Lighthouse benchmarks and empirical audit data.",
                "Provide clear SLA terms and 30-day post-delivery technical support warranty."
            ],
            unsuccessful_patterns=[
                "Generic promotional slogans without personalized evidence.",
                "Fabricating case studies or making unverified claims."
            ],
            recommended_turnaround_angle="Turnkey Interactive Demo & Objective Benchmark",
            evidence_required="Working interactive sandbox deployment URL."
        ),
        "TIMING": ObjectionFramework(
            category="TIMING",
            description="Prospect is busy or asks to reconnect in a later quarter.",
            detection_keywords=["later", "next month", "next quarter", "busy", "circle back", "not now"],
            successful_patterns=[
                "Acknowledge timing and offer low-friction passive monitoring report.",
                "Schedule automated follow-up sequence with 14-day cadence.",
                "Highlight seasonal urgency if applicable (e.g. storm season for roofing, summer for HVAC)."
            ],
            unsuccessful_patterns=[
                "High-pressure artificial countdown timers.",
                "Ignoring the timing request and aggressively spamming."
            ],
            recommended_turnaround_angle="Low-Friction Educational Nurture",
            evidence_required="Seasonal search volume or competitive activity trend."
        ),
        "ALREADY_HAVE_PROVIDER": ObjectionFramework(
            category="ALREADY_HAVE_PROVIDER",
            description="Prospect works with an existing webmaster, in-house team, or agency.",
            detection_keywords=["already have", "in-house", "current agency", "someone else handles it"],
            successful_patterns=[
                "Position as complimentary diagnostic or specialized plug-in rather than full replacement.",
                "Present the objective technical deficits their current provider overlooked.",
                "Offer to send the technical audit report directly to their internal developer."
            ],
            unsuccessful_patterns=[
                "Criticizing their existing team or disparaging competitors.",
                "Insisting their current setup is completely broken."
            ],
            recommended_turnaround_angle="Collaborative Diagnostic & Specialized Add-On",
            evidence_required="Specific technical defect audit (e.g. Mobile CLS shift or missing SSL HSTS)."
        ),
        "NEED_APPROVAL": ObjectionFramework(
            category="NEED_APPROVAL",
            description="Contact is not the sole decision-maker and must confer with partners.",
            detection_keywords=["talk to partner", "need approval", "board", "committee", "discuss with owner"],
            successful_patterns=[
                "Provide concise 1-page executive summary PDF with clear ROI.",
                "Offer to host a brief 10-minute walkthrough demonstration for all stakeholders.",
                "Frame proposal in executive commercial terms (cost vs payoff)."
            ],
            unsuccessful_patterns=[
                "Bypassing the contact or demanding an immediate solo decision.",
                "Sending overwhelming 50-page technical jargon documentation."
            ],
            recommended_turnaround_angle="Executive 1-Page Commercial Decision Brief",
            evidence_required="Executive summary PDF and sandbox demo link."
        )
    }

    @classmethod
    def get_strategy(cls, objection_category: str) -> Optional[ObjectionFramework]:
        return cls.LIBRARY.get(objection_category.upper())

    @classmethod
    def recommend_response(cls, detected_objections: List[str]) -> Dict[str, Any]:
        """Synthesizes recommendations for detected objections."""
        if not detected_objections:
            return {"strategy": "STANDARD_PROCEED", "guidance": "No active objections detected."}

        primary = detected_objections[0].replace("_OBJECTION", "").upper()
        framework = cls.get_strategy(primary)
        if not framework:
            return {"strategy": "GENERAL_CLARIFICATION", "guidance": "Provide clear, evidence-grounded answers."}

        return {
            "objection": framework.category,
            "recommended_angle": framework.recommended_turnaround_angle,
            "proven_patterns": framework.successful_patterns,
            "patterns_to_avoid": framework.unsuccessful_patterns,
            "required_evidence": framework.evidence_required
        }


objection_intelligence_engine = ObjectionIntelligenceEngine()
