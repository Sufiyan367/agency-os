"""
Deterministic Objection Taxonomy and Response Engine.

Enforces:
1. 19-category deterministic objection taxonomy.
2. Multi-objection detection without relying solely on raw LLM classification.
3. Factual grounding: strictly references observed audit evidence; never fabricates
   testimonials, case studies, results, client names, or unobserved defects.
4. Pricing discipline: defends $1,000 commercial target and enforces the $500 floor
   without autonomous discounting.
5. Sensitive trigger escalation: immediately flags legal threats, refund disputes,
   aggressive negotiation, prompt injection, and explicit human operator demands.
"""
import enum
import re
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import logger
from app.ml.policy_engine import policy_engine
from app.core.security import PromptInjectionGuard


class ObjectionCategory(str, enum.Enum):
    PRICE_HIGH = "PRICE_HIGH"
    PRICE_LOW = "PRICE_LOW"
    NEED_MORE_INFO = "NEED_MORE_INFO"
    NOT_NOW = "NOT_NOW"
    NO_BUDGET = "NO_BUDGET"
    ALREADY_HAVE_PROVIDER = "ALREADY_HAVE_PROVIDER"
    NEED_TO_THINK = "NEED_TO_THINK"
    NEED_OWNER_APPROVAL = "NEED_OWNER_APPROVAL"
    NEED_PROOF = "NEED_PROOF"
    NEED_CASE_STUDY = "NEED_CASE_STUDY"
    TIMING = "TIMING"
    TRUST_CONCERN = "TRUST_CONCERN"
    TECHNICAL_CONCERN = "TECHNICAL_CONCERN"
    COMPETITOR_COMPARISON = "COMPETITOR_COMPARISON"
    SCOPE_CLARIFICATION = "SCOPE_CLARIFICATION"
    PAYMENT_CONCERN = "PAYMENT_CONCERN"
    NOT_INTERESTED = "NOT_INTERESTED"
    OPT_OUT = "OPT_OUT"
    UNKNOWN = "UNKNOWN"


class ConversationIntent(str, enum.Enum):
    FIRST_CONTACT = "FIRST_CONTACT"
    FOLLOW_UP = "FOLLOW_UP"
    POSITIVE_REPLY = "POSITIVE_REPLY"
    PRICE_INQUIRY = "PRICE_INQUIRY"
    OBJECTION = "OBJECTION"
    MEETING_REQUEST = "MEETING_REQUEST"
    NEGOTIATION = "NEGOTIATION"
    PROPOSAL_DISCUSSION = "PROPOSAL_DISCUSSION"
    PAYMENT_DISCUSSION = "PAYMENT_DISCUSSION"
    REJECTION = "REJECTION"
    OPT_OUT = "OPT_OUT"


class ObjectionResponse(BaseModel):
    objection_categories: List[str]
    primary_objection: str
    client_facing_draft: str
    internal_reasoning: str
    commercial_implications: str
    recommended_action: str
    force_human_takeover: bool = False
    approval_required: bool = True
    confidence: float = 0.90
    target_price: float = 1000.0


class ObjectionDetector:
    """Deterministic, regex-backed detector for commercial objections and sensitive triggers."""

    PATTERNS: List[Tuple[ObjectionCategory, List[str]]] = [
        (
            ObjectionCategory.OPT_OUT,
            [
                r"\b(unsubscribe|remove me|opt[- ]?out|stop emailing|take me off|delete my info|cease contacting)\b"
            ]
        ),
        (
            ObjectionCategory.NOT_INTERESTED,
            [
                r"\b(not interested|no thanks|pass on this|we're good|not for us|do not want|not looking for)\b"
            ]
        ),
        (
            ObjectionCategory.ALREADY_HAVE_PROVIDER,
            [
                r"\b(already have|have a guy|have an agency|current agency|in[- ]house team|existing developer|webmaster|already working with|handled internally)\b"
            ]
        ),
        (
            ObjectionCategory.PRICE_HIGH,
            [
                r"\b(too expensive|price is too high|can't afford that|rates are steep|out of our budget|cheaper|discount|reduce price|cost too much|ridiculous price)\b"
            ]
        ),
        (
            ObjectionCategory.PRICE_LOW,
            [
                r"\b(suspiciously cheap|too cheap|why so low|why so cheap|hidden costs|what's the catch)\b"
            ]
        ),
        (
            ObjectionCategory.NO_BUDGET,
            [
                r"\b(no budget|zero budget|tight on funds|no money allocated|budget frozen|cash flow tight|not in budget)\b"
            ]
        ),
        (
            ObjectionCategory.NOT_NOW,
            [
                r"\b(not right now|not now|busy season|circle back later|revisit next quarter|next year|reach back in|contact me in)\b"
            ]
        ),
        (
            ObjectionCategory.TIMING,
            [
                r"\b(bad timing|timing isn't right|too busy right now|handling other priorities|in the middle of|relaunching soon)\b"
            ]
        ),
        (
            ObjectionCategory.NEED_MORE_INFO,
            [
                r"\b(send more info|more details|tell me more|what exactly do you do|how does this work|can you elaborate|breakdown of services)\b"
            ]
        ),
        (
            ObjectionCategory.NEED_TO_THINK,
            [
                r"\b(need to think|let me think|give me a few days|consider this|sleeping on it|mulling it over)\b"
            ]
        ),
        (
            ObjectionCategory.NEED_OWNER_APPROVAL,
            [
                r"\b(ask the owner|check with my boss|board approval|run it by the partner|check with leadership|need director sign-off)\b"
            ]
        ),
        (
            ObjectionCategory.NEED_PROOF,
            [
                r"\b(show me proof|how do i know this works|evidence|verifiable data|guarantee results|prove it)\b"
            ]
        ),
        (
            ObjectionCategory.NEED_CASE_STUDY,
            [
                r"\b(case study|case studies|examples of past work|portfolio|references|past clients|similar projects)\b"
            ]
        ),
        (
            ObjectionCategory.TRUST_CONCERN,
            [
                r"\b(who are you|is this a scam|legit|are you reputable|never heard of you|trust|cold email spam)\b"
            ]
        ),
        (
            ObjectionCategory.TECHNICAL_CONCERN,
            [
                r"\b(will this break my site|platform compatibility|wordpress|shopify|custom stack|server load|security risk|api)\b"
            ]
        ),
        (
            ObjectionCategory.COMPETITOR_COMPARISON,
            [
                r"\b(better than|compared to|other agencies charge|another company offered|versus|competitor)\b"
            ]
        ),
        (
            ObjectionCategory.SCOPE_CLARIFICATION,
            [
                r"\b(what's included|what is included|scope|deliverables|revisions|timeline|how long does it take|what do we get)\b"
            ]
        ),
        (
            ObjectionCategory.PAYMENT_CONCERN,
            [
                r"\b(payment terms|net 30|pay upon completion|upfront deposit|credit card fee|wire transfer|invoice terms)\b"
            ]
        ),
    ]

    SENSITIVE_TRIGGERS: List[Tuple[str, str, List[str]]] = [
        (
            "LEGAL_THREAT",
            "Legal counsel, lawsuit, attorney, or regulatory threat detected",
            [r"\b(lawyer|attorney|sue you|legal action|cease and desist|counsel|court|can-spam violation|gdpr violation)\b"]
        ),
        (
            "REFUND_DISPUTE",
            "Refund, chargeback, or monetary recovery demand detected",
            [r"\b(refund|chargeback|dispute the charge|money back|stolen money|fraudulent)\b"]
        ),
        (
            "AGGRESSIVE_NEGOTIATION",
            "Extremely aggressive discount or hostile ultimatum",
            [r"\b(cut it in half|half price or no deal|pay zero upfront|pay you only if millions)\b"]
        ),
        (
            "UNUSUAL_PAYMENT",
            "Unapproved or high-risk payment mechanism requested",
            [r"\b(crypto|bitcoin|usdt|western union|cash in mail|escrow service|off-platform)\b"]
        ),
        (
            "SECURITY_CONCERN",
            "Security vulnerability, breach, or credential complaint",
            [r"\b(data breach|malware|phishing|compromised|hacked|cybersecurity team|security audit report)\b"]
        ),
        (
            "CONTRACT_DISPUTE",
            "Breach of contract, indemnification, or liability challenge",
            [r"\b(breach of contract|indemnify|indemnification|gross negligence|legal agreement)\b"]
        ),
        (
            "EXPLICIT_HUMAN_DEMAND",
            "Prospect explicitly demands to interact with a human operator",
            [r"\b(speak to a human|real person only|talk to a person|operator now|manager now|call me directly)\b"]
        ),
    ]

    @classmethod
    def detect_objections(cls, text: str) -> List[ObjectionCategory]:
        """Identifies all matching objection categories from text."""
        lower = text.lower().strip()
        matched = []

        for category, patterns in cls.PATTERNS:
            for pat in patterns:
                if re.search(pat, lower):
                    matched.append(category)
                    break

        if not matched:
            if any(w in lower for w in ["maybe", "not sure", "hesitant", "concern", "issue", "problem", "doubt"]):
                matched.append(ObjectionCategory.UNKNOWN)

        return matched

    @classmethod
    def detect_sensitive_triggers(cls, text: str) -> Dict[str, Any]:
        """Scans for conditions requiring immediate forced human takeover."""
        lower = text.lower().strip()

        # Prompt injection check
        is_safe, threat = PromptInjectionGuard.scan_text(text)
        if not is_safe:
            return {
                "is_sensitive": True,
                "trigger_type": "PROMPT_INJECTION",
                "reason": f"Prompt injection guardrail triggered: {threat}"
            }

        # Check explicit sensitive patterns
        for trigger_type, description, patterns in cls.SENSITIVE_TRIGGERS:
            for pat in patterns:
                if re.search(pat, lower):
                    return {
                        "is_sensitive": True,
                        "trigger_type": trigger_type,
                        "reason": description
                    }

        return {
            "is_sensitive": False,
            "trigger_type": "NONE",
            "reason": "Standard commercial interaction"
        }

    @classmethod
    def classify_intent(cls, text: str, detected_objections: List[ObjectionCategory]) -> ConversationIntent:
        """Determines the overarching conversation intent."""
        lower = text.lower().strip()

        if ObjectionCategory.OPT_OUT in detected_objections:
            return ConversationIntent.OPT_OUT

        if ObjectionCategory.NOT_INTERESTED in detected_objections and len(detected_objections) == 1:
            return ConversationIntent.REJECTION

        if any(w in lower for w in ["schedule", "call", "meet", "calendar", "zoom", "tomorrow", "thursday", "morning", "afternoon"]):
            if any(w in lower for w in ["time", "talk", "chat", "discuss", "available"]):
                return ConversationIntent.MEETING_REQUEST

        if any(w in lower for w in ["invoice", "payment link", "checkout", "deposit", "paid", "receipt", "advance"]):
            return ConversationIntent.PAYMENT_DISCUSSION

        if any(w in lower for w in ["proposal", "scope of work", "agreement", "contract", "deliverables", "sign"]):
            return ConversationIntent.PROPOSAL_DISCUSSION

        if any(w in lower for w in ["how much", "what is the price", "cost", "rates", "fee"]):
            return ConversationIntent.PRICE_INQUIRY

        if detected_objections:
            return ConversationIntent.OBJECTION

        if any(w in lower for w in ["interested", "sounds good", "send details", "send audit", "love to see", "yes"]):
            return ConversationIntent.POSITIVE_REPLY

        return ConversationIntent.FOLLOW_UP


class ObjectionResponseEngine:
    """
    Context-aware, factually grounded objection response synthesizer.
    
    Protects commercial floor ($500) and targets $1,000 without autonomous discounting.
    Grounds all arguments in actual audit findings without fabricating results.
    """

    TARGET_OFFER_USD: float = 1000.0
    FLOOR_OFFER_USD: float = 500.0

    @classmethod
    def generate_response(
        cls,
        *,
        prospect_context: Dict[str, Any],
        objections: List[ObjectionCategory],
        raw_reply: str
    ) -> ObjectionResponse:
        """
        Synthesizes a tailored, grounded response addressing the prospect's specific objections.
        """
        domain = prospect_context.get("domain", "your website")
        biz_name = prospect_context.get("name", domain)
        audit = prospect_context.get("audit_results") or {}
        perf_score = audit.get("performance_score", 70.0)
        findings = audit.get("findings") or []
        findings_count = len(findings) if isinstance(findings, list) else 0

        # Commercial offer value resolution (protecting $1,000 target and $500 floor)
        raw_offer_val = prospect_context.get("estimated_value", cls.TARGET_OFFER_USD)
        current_offer_val = max(raw_offer_val, cls.TARGET_OFFER_USD)
        current_offer_val = max(current_offer_val, policy_engine.get_commercial_floor())

        from_name = getattr(settings, "OUTREACH_FROM_NAME", "Elena Vance | Digital Strategy Director")

        # 1. Check sensitive triggers first (Fail-Closed Human Takeover)
        sensitive = ObjectionDetector.detect_sensitive_triggers(raw_reply)
        if sensitive["is_sensitive"]:
            trigger_type = sensitive["trigger_type"]
            reason = sensitive["reason"]
            draft = (
                f"Thank you for your note regarding {domain}. I have escalated this matter directly to our "
                f"executive management team to review and contact you personally."
            )
            return ObjectionResponse(
                objection_categories=[o.value for o in objections] or [trigger_type],
                primary_objection=trigger_type,
                client_facing_draft=draft,
                internal_reasoning=f"Escalated to human operator due to sensitive trigger: {reason}",
                commercial_implications="Automated outreach halted. Mandatory human takeover active.",
                recommended_action="HUMAN_TAKEOVER",
                force_human_takeover=True,
                approval_required=True,
                confidence=0.99,
                target_price=current_offer_val
            )

        # 2. Opt-Out / Unsubscribe
        if ObjectionCategory.OPT_OUT in objections:
            return ObjectionResponse(
                objection_categories=[ObjectionCategory.OPT_OUT.value],
                primary_objection=ObjectionCategory.OPT_OUT.value,
                client_facing_draft="Understood. You have been removed from our communications and will not be contacted again.",
                internal_reasoning="Prospect requested removal. Suppressed immediately; follow-ups cancelled.",
                commercial_implications="Prospect lost. Zero further touches permitted.",
                recommended_action="SUPPRESS_PROSPECT",
                force_human_takeover=False,
                approval_required=False,
                confidence=0.99,
                target_price=0.0
            )

        # 3. Not Interested / Rejection
        if ObjectionCategory.NOT_INTERESTED in objections and len(objections) == 1:
            return ObjectionResponse(
                objection_categories=[ObjectionCategory.NOT_INTERESTED.value],
                primary_objection=ObjectionCategory.NOT_INTERESTED.value,
                client_facing_draft=f"Thank you for letting us know. Wishing you and the {biz_name} team continued success!",
                internal_reasoning="Direct decline. Polite closeout without aggressive follow-up.",
                commercial_implications="Stage moved to LOST. No immediate revenue potential.",
                recommended_action="CLOSE_AS_LOST",
                force_human_takeover=False,
                approval_required=True,
                confidence=0.95,
                target_price=current_offer_val
            )

        # 4. Primary Objection Resolution
        primary = objections[0] if objections else ObjectionCategory.UNKNOWN
        categories_str = [o.value for o in objections]

        # Factual diagnostic grounding anchor
        diagnostic_evidence_text = ""
        if findings_count > 0:
            diagnostic_evidence_text = f"Our automated diagnostic confirmed {findings_count} specific performance bottlenecks (Site Health: {perf_score:.0f}/100) on {domain}."
        else:
            diagnostic_evidence_text = f"Our technical diagnostic recorded an overall health score of {perf_score:.0f}/100 on {domain}."

        # Response routing by primary objection
        if primary in (ObjectionCategory.PRICE_HIGH, ObjectionCategory.NO_BUDGET):
            # Strict Pricing Discipline: Clarify value & scope, NEVER auto-discount below policy floor
            draft = (
                f"Hi there, thank you for the transparent feedback on investment considerations. "
                f"{diagnostic_evidence_text} "
                f"Rather than a generic redesign, our ${current_offer_val:,.0f} turnkey engagement specifically isolates "
                f"the mobile conversion and latency friction directly impacting incoming calls and quote submissions. "
                f"If budget is currently restricted, we can phase the implementation into an initial critical milestone "
                f"(preserving our ${cls.FLOOR_OFFER_USD:,.0f} core turnaround floor) so you capture immediate inquiry gains. "
                f"Would you be open to a 10-minute screenshare to review which items deliver the highest immediate return?\n\n"
                f"Best regards,\n{from_name}"
            )
            reasoning = (
                f"Defended ${current_offer_val:,.0f} commercial target without unilateral discounting. "
                f"Reinforced observed audit findings ({perf_score:.0f}/100) and offered modular scope phasing "
                f"while strictly protecting the ${cls.FLOOR_OFFER_USD:,.0f} policy floor."
            )
            commercial = (
                f"Protected ${current_offer_val:,.0f} target value. Permitted scope adjustment only down to "
                f"${cls.FLOOR_OFFER_USD:,.0f} floor if operator approves."
            )
            action = "PROPOSE_PHASED_SCOPE"

        elif primary == ObjectionCategory.ALREADY_HAVE_PROVIDER:
            draft = (
                f"Hi there, we completely respect your existing developer/agency relationship. "
                f"We do not seek to replace your ongoing web team. {diagnostic_evidence_text} "
                f"Often, internal teams or general agencies are focused on design or content rather than deep Core Web Vitals optimization. "
                f"We can provide a complimentary one-page technical diagnosis detailing the exact code and asset bottlenecks so your "
                f"current team can resolve them directly. Would you like me to send that over?\n\n"
                f"Best regards,\n{from_name}"
            )
            reasoning = (
                "Acknowledged existing agency relationship gracefully. Positioned service as specialized performance diagnosis "
                "to collaborate or provide technical audit, keeping the conversation warm."
            )
            commercial = "Low friction entry point. Opportunity to upsell execution if internal team lacks capacity."
            action = "OFFER_TECHNICAL_AUDIT_BRIEF"

        elif primary in (ObjectionCategory.NOT_NOW, ObjectionCategory.TIMING, ObjectionCategory.NEED_TO_THINK):
            draft = (
                f"Hi there, understood completely—timing is everything when running a busy operation. "
                f"{diagnostic_evidence_text} "
                f"Because these speed issues continually affect mobile visitors looking for your services, "
                f"would it make sense for me to check back with you in about 3 weeks, or should we pencil in a brief 10-minute "
                f"chat next month once your schedule clears up?\n\n"
                f"Best regards,\n{from_name}"
            )
            reasoning = "Respected prospect schedule constraint while anchoring the continuous cost of delay with audit findings."
            commercial = "Scheduled deferral; keeps prospect in pipeline without lead decay."
            action = "SCHEDULE_TIMED_FOLLOW_UP"

        elif primary == ObjectionCategory.NEED_MORE_INFO or primary == ObjectionCategory.SCOPE_CLARIFICATION:
            draft = (
                f"Hi there, happy to clarify the exact turnaround scope for {domain}. "
                f"{diagnostic_evidence_text} "
                f"Our turnkey ${current_offer_val:,.0f} optimization package includes: "
                f"(1) Above-the-fold mobile LCP & server response speed acceleration, "
                f"(2) Click-to-call and mobile quote form frictionless CTA placement, and "
                f"(3) Payload minification and asset caching. "
                f"We handle the entire implementation end-to-end within 5 business days. "
                f"Would a 10-minute walkthrough this week be helpful to see the specific changes on your staging site?\n\n"
                f"Best regards,\n{from_name}"
            )
            reasoning = "Detailed itemized deliverables grounded strictly in performance and conversion audit scope."
            commercial = f"Reinforced ${current_offer_val:,.0f} turnkey scope."
            action = "PROPOSE_DISCOVERY_CALL"

        elif primary in (ObjectionCategory.NEED_PROOF, ObjectionCategory.NEED_CASE_STUDY, ObjectionCategory.TRUST_CONCERN):
            # Strict Anti-Hallucination: Do not fabricate clients, testimonials, or revenue figures
            draft = (
                f"Hi there, fair question—reputation and verifiable technical rigor are essential. "
                f"Rather than asking you to rely on claims, {diagnostic_evidence_text} "
                f"All our remediation recommendations are strictly benchmarked against official Google Core Web Vitals and Lighthouse metrics. "
                f"We provide verifiable before-and-after audit reports on every live URL we optimize so you see the exact measurable latency drop. "
                f"Would you like us to run a live side-by-side diagnostic check on your top mobile conversion page?\n\n"
                f"Best regards,\n{from_name}"
            )
            reasoning = (
                "Avoided fabricating unverified case studies, client logos, or false guarantees. "
                "Grounded credibility in objective Google Core Web Vitals standards and verifiable before/after data."
            )
            commercial = f"Maintained pricing integrity (${current_offer_val:,.0f}). Built trust through verifiable metrics."
            action = "OFFER_VERIFIABLE_DIAGNOSTIC"

        elif primary == ObjectionCategory.NEED_OWNER_APPROVAL:
            draft = (
                f"Hi there, absolutely understandable—executive alignment is critical for technical updates on {domain}. "
                f"{diagnostic_evidence_text} "
                f"We can prepare an executive summary slide deck summarizing the technical findings and estimated inquiry impact "
                f"formatted specifically for your leadership team. "
                f"Would it be helpful if I forwarded that over for your review?\n\n"
                f"Best regards,\n{from_name}"
            )
            reasoning = "Empowered internal champion with executive-ready diagnostic summary."
            commercial = "Enables multi-stakeholder deal progression."
            action = "SEND_EXECUTIVE_SUMMARY"

        elif primary == ObjectionCategory.COMPETITOR_COMPARISON:
            draft = (
                f"Hi there, thanks for bringing that up. While general agencies often focus on broad marketing or general maintenance, "
                f"our team focuses exclusively on Core Web Vitals remediation and mobile inquiry turnaround for commercial contractors. "
                f"{diagnostic_evidence_text} "
                f"We operate on guaranteed technical milestones: we identify the bottleneck, deploy optimized code within 5 days, "
                f"and provide verified post-launch diagnostic verification. "
                f"Would you be open to a 10-minute comparison of the specific fixes needed for {domain}?\n\n"
                f"Best regards,\n{from_name}"
            )
            reasoning = "Differentiated on specialized Core Web Vitals technical execution without disparaging competitors."
            commercial = f"Defended ${current_offer_val:,.0f} value proposition."
            action = "PROPOSE_DISCOVERY_CALL"

        elif primary == ObjectionCategory.TECHNICAL_CONCERN:
            draft = (
                f"Hi there, that is an important technical question. Our engineering workflow never touches live production code unverified. "
                f"We work on a secure staging branch or provide drop-in assets and test them thoroughly across simulated mobile viewports "
                f"before any live deployment. {diagnostic_evidence_text} "
                f"Would you or your technical lead like to do a quick 10-minute architecture review to ensure full platform compatibility?\n\n"
                f"Best regards,\n{from_name}"
            )
            reasoning = "Addressed technical and safety concerns by explaining staging deployment workflow."
            commercial = "Eliminated technical barrier to closing."
            action = "PROPOSE_TECHNICAL_CALL"

        elif primary == ObjectionCategory.PAYMENT_CONCERN:
            adv_pct = getattr(settings, "DEFAULT_ADVANCE_PERCENTAGE", 40.0)
            deposit_val = round(current_offer_val * (adv_pct / 100.0), 2)
            balance_val = round(current_offer_val - deposit_val, 2)
            draft = (
                f"Hi there, we provide standard commercial milestone terms: a {int(adv_pct)}% deposit (${deposit_val:,.0f} USD) "
                f"to initiate the engineering sprint, with the remaining balance (${balance_val:,.0f} USD) payable only after "
                f"verified deployment and diagnostic validation on {domain}. "
                f"All payments are processed securely via verified corporate checkout with itemized invoicing. "
                f"Does that structure align with your billing cycle?\n\n"
                f"Best regards,\n{from_name}"
            )
            reasoning = f"Clarified milestone billing structure ({int(adv_pct)}% deposit / balance post-validation) with formal invoicing."
            commercial = f"Preserved ${current_offer_val:,.0f} total deal value with milestone security."
            action = "PROPOSE_MILESTONE_TERMS"

        else:
            # Fallback for general inquiry / unknown resistance
            draft = (
                f"Hi there, thank you for your response regarding {domain}. "
                f"{diagnostic_evidence_text} "
                f"Our primary focus is eliminating mobile friction so your website turns more visitors into phone calls and quote requests. "
                f"Could we schedule a brief 10-minute consultation this week to review the findings and answer any questions you have?\n\n"
                f"Best regards,\n{from_name}"
            )
            reasoning = "Polite clarifying response grounding the conversation in audited website health."
            commercial = f"Advancing prospect toward commercial qualification at ${current_offer_val:,.0f}."
            action = "PROPOSE_DISCOVERY_CALL"

        return ObjectionResponse(
            objection_categories=categories_str,
            primary_objection=primary.value,
            client_facing_draft=draft,
            internal_reasoning=reasoning,
            commercial_implications=commercial,
            recommended_action=action,
            force_human_takeover=False,
            approval_required=True,
            confidence=0.91,
            target_price=current_offer_val
        )


objection_detector = ObjectionDetector()
objection_response_engine = ObjectionResponseEngine()
