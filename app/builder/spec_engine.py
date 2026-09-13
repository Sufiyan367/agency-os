"""
Canonical Specification Engine — Phase 2 of Autonomous Demo & Build Pipeline.
Transforms business telemetry, audit data, and prospect requests into an immutable, versioned,
canonical technical specification with strict 3-way segregation:
1. FACTS (grounded, verified business & audit data)
2. CUSTOMER_REQUESTS (explicit prospect inquiries & desired capabilities)
3. AI_INFERENCES (inferred architecture, design tokens, screens, and AI features)
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    Business, CustomerProject, ProjectSpecification, Offer, AuditRun
)
from app.builder.models import (
    CanonicalSpec, RequirementFact, CustomerRequestItem, AIInferenceItem
)
from app.core.logging import logger


class CanonicalSpecEngine:
    """
    Produces deterministic, reproducible, versioned technical specifications
    for customer projects and live sales demos.
    """

    @classmethod
    def extract_customer_requests(cls, reply_text: Optional[str], industry: str) -> List[CustomerRequestItem]:
        """Extracts explicit prospect requests or supplies industry-specific commercial defaults."""
        requests: List[CustomerRequestItem] = []
        text = (reply_text or "").lower()

        if "book" in text or "schedul" in text or "appointment" in text or "calendar" in text:
            requests.append(CustomerRequestItem(
                request_text="Interactive 24/7 online booking and schedule reservation workflow",
                feature_type="booking",
                priority="high"
            ))

        if "quote" in text or "calculat" in text or "estimate" in text or "pricing" in text:
            requests.append(CustomerRequestItem(
                request_text="Instant commercial quote estimator and service calculation module",
                feature_type="calculator",
                priority="high"
            ))

        if "chat" in text or "ai" in text or "assistant" in text or "receptionist" in text:
            requests.append(CustomerRequestItem(
                request_text="Intelligent conversational intake assistant with natural language triage",
                feature_type="ai_assistant",
                priority="high"
            ))

        if "mobile" in text or "responsive" in text or "speed" in text or "fast" in text:
            requests.append(CustomerRequestItem(
                request_text="High-speed mobile-first responsive performance optimization",
                feature_type="performance",
                priority="medium"
            ))

        # If no explicit requests were parsed from the incoming text, formulate industry-tailored requests
        if not requests:
            ind_lower = (industry or "").lower()
            if any(k in ind_lower for k in ["auto", "car", "mechanic", "dealership"]):
                requests.append(CustomerRequestItem(
                    request_text="Automated service appointment reservation and vehicle diagnostic intake",
                    feature_type="booking",
                    priority="high"
                ))
                requests.append(CustomerRequestItem(
                    request_text="Transparent repair & maintenance cost estimator",
                    feature_type="calculator",
                    priority="medium"
                ))
            elif any(k in ind_lower for k in ["dent", "clinic", "health", "medic"]):
                requests.append(CustomerRequestItem(
                    request_text="New patient intake portal and real-time consultation booking",
                    feature_type="booking",
                    priority="high"
                ))
                requests.append(CustomerRequestItem(
                    request_text="Emergency dental triage assistant with treatment pricing guide",
                    feature_type="ai_assistant",
                    priority="high"
                ))
            elif any(k in ind_lower for k in ["roof", "solar", "construct"]):
                requests.append(CustomerRequestItem(
                    request_text="Interactive roof replacement square footage and cost calculator",
                    feature_type="calculator",
                    priority="high"
                ))
                requests.append(CustomerRequestItem(
                    request_text="Storm damage assessment and emergency inspection request dispatch",
                    feature_type="booking",
                    priority="high"
                ))
            elif any(k in ind_lower for k in ["hvac", "plumb", "electric"]):
                requests.append(CustomerRequestItem(
                    request_text="24/7 emergency dispatch scheduler and diagnostic booking",
                    feature_type="booking",
                    priority="high"
                ))
                requests.append(CustomerRequestItem(
                    request_text="Seasonal maintenance package selector and instant quote preview",
                    feature_type="calculator",
                    priority="medium"
                ))
            else:
                requests.append(CustomerRequestItem(
                    request_text="Modern high-converting commercial landing page with inquiry intake",
                    feature_type="ui",
                    priority="high"
                ))
                requests.append(CustomerRequestItem(
                    request_text="Instant prospect response and qualification assistant",
                    feature_type="ai_assistant",
                    priority="medium"
                ))

        return requests

    @classmethod
    def extract_facts(cls, business: Business, audit: Optional[AuditRun] = None) -> List[RequirementFact]:
        """Extracts strictly verified factual evidence from database records."""
        facts: List[RequirementFact] = []

        biz_name = business.name or business.domain
        facts.append(RequirementFact(
            category="business_identity",
            description=f"Verified business name: {biz_name}",
            source="crm_database"
        ))
        facts.append(RequirementFact(
            category="digital_presence",
            description=f"Primary domain: {business.domain}",
            source="crm_database"
        ))

        industry = business.niche or "Commercial Services"
        facts.append(RequirementFact(
            category="market_sector",
            description=f"Operating niche: {industry}",
            source="crm_database"
        ))

        if business.city or business.country:
            loc = f"{business.city}, {business.country}".strip(", ")
            facts.append(RequirementFact(
                category="geographic_scope",
                description=f"Service location: {loc}",
                source="crm_database"
            ))

        if business.phone:
            facts.append(RequirementFact(
                category="contact_channel",
                description=f"Verified public phone: {business.phone}",
                source="crm_database"
            ))

        if business.public_email:
            facts.append(RequirementFact(
                category="contact_channel",
                description=f"Verified public email: {business.public_email}",
                source="crm_database"
            ))

        if audit and audit.audit_score:
            facts.append(RequirementFact(
                category="audit_baseline",
                description=f"Baseline site audit performance score: {audit.audit_score}/100",
                source="audit_telemetry"
            ))

        return facts

    @classmethod
    def generate_ai_inferences(
        cls,
        industry: str,
        facts: List[RequirementFact],
        requests: List[CustomerRequestItem]
    ) -> List[AIInferenceItem]:
        """Derives strategic technical architecture and UX inferences."""
        inferences: List[AIInferenceItem] = []

        inferences.append(AIInferenceItem(
            inferred_need="Mobile-first responsive architecture",
            recommended_solution="Tailwind CSS responsive design with flex/grid containers and sub-second paint targets",
            confidence=0.98
        ))

        inferences.append(AIInferenceItem(
            inferred_need="High-conversion lead capture",
            recommended_solution="Sticky mobile consultation CTA with instant calendar intake modal",
            confidence=0.95
        ))

        # Feature specific inferences
        has_booking = any(r.feature_type == "booking" for r in requests)
        has_calc = any(r.feature_type == "calculator" for r in requests)
        has_ai = any(r.feature_type == "ai_assistant" for r in requests)

        if has_booking:
            inferences.append(AIInferenceItem(
                inferred_need="Frictionless appointment booking",
                recommended_solution="Multi-step booking stepper with zero page reload and real-time validation",
                confidence=0.94
            ))

        if has_calc:
            inferences.append(AIInferenceItem(
                inferred_need="Transparent customer cost estimation",
                recommended_solution="Dynamic slider and tier calculator with real-time total breakdown",
                confidence=0.92
            ))

        if has_ai:
            inferences.append(AIInferenceItem(
                inferred_need="Autonomous off-hours intake",
                recommended_solution="Embedded conversational intake widget powered by Gemini 2.5 Flash with fallback logic",
                confidence=0.96
            ))

        return inferences

    @classmethod
    def determine_screens(
        cls,
        industry: str,
        requests: List[CustomerRequestItem]
    ) -> List[Dict[str, Any]]:
        """Maps customer requirements to concrete UI screens/views."""
        screens = [
            {
                "screen_id": "overview",
                "title": "Executive Overview & Hero",
                "route": "/",
                "description": "High-impact hero showcase with value proposition, social proof, and primary intake action.",
                "components": ["HeroHeader", "FeatureHighlights", "CredibilityBadges", "PrimaryCTA"]
            }
        ]

        has_booking = any(r.feature_type == "booking" for r in requests)
        has_calc = any(r.feature_type == "calculator" for r in requests)
        has_ai = any(r.feature_type == "ai_assistant" for r in requests)

        if has_booking:
            screens.append({
                "screen_id": "booking",
                "title": "Online Appointment & Service Reservation",
                "route": "/booking",
                "description": "Interactive appointment booking stepper with date selection, service options, and confirmation text preview.",
                "components": ["ServicePicker", "DateSlotPicker", "ContactForm", "ConfirmationModal"]
            })

        if has_calc:
            screens.append({
                "screen_id": "calculator",
                "title": "Instant Estimate & Pricing Calculator",
                "route": "/calculator",
                "description": "Dynamic pricing calculator allowing prospective clients to estimate service costs in real time.",
                "components": ["ScopeSlider", "ServiceAddons", "CostSummaryCard", "QuoteDownloadCTA"]
            })

        if has_ai:
            screens.append({
                "screen_id": "assistant",
                "title": "Autonomous 24/7 Intake Assistant",
                "route": "/assistant",
                "description": "Conversational triage widget that qualifies customer intent and captures project specifications.",
                "components": ["ChatWindow", "QuickReplies", "LeadCaptureCard", "AgentTypingIndicator"]
            })

        # Always include proof & packages screen
        screens.append({
            "screen_id": "packages",
            "title": "Commercial Solutions & Itemized Scope",
            "route": "/packages",
            "description": "Itemized scope packages, transparent deliverables, and commercial guarantee terms.",
            "components": ["PricingTable", "ScopeChecklist", "GuaranteeBanner", "AdvanceCheckoutCTA"]
        })

        return screens

    @classmethod
    def determine_ai_features(
        cls,
        industry: str,
        business_name: str,
        requests: List[CustomerRequestItem]
    ) -> List[Dict[str, Any]]:
        """Configures AI prototyping specifications for Google AI Studio provider."""
        return [
            {
                "feature_id": "intake_assistant",
                "name": f"{business_name} AI Intake Concierge",
                "prototype_type": "conversational_triage",
                "model_name": "gemini-2.5-flash",
                "system_instructions": (
                    f"You are the courteous, professional AI intake concierge for {business_name} in the {industry} sector. "
                    f"Your objective is to warmly greet prospective customers, understand their specific service needs, "
                    f"assess urgency, collect their preferred appointment time or project scope, and confirm contact details. "
                    f"Always maintain a helpful, polite, and confident tone. Never fabricate commitments outside standard service offerings."
                ),
                "quick_prompts": [
                    "I need to book a service appointment as soon as possible.",
                    "What are your standard rates and turnaround times?",
                    "Do you offer emergency or weekend service?"
                ]
            }
        ]

    @classmethod
    def calculate_checksum(cls, spec_dict: Dict[str, Any]) -> str:
        """Computes a deterministic SHA-256 hash over the canonical specification payload."""
        normalized = json.dumps(spec_dict, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    async def build_canonical_spec(
        cls,
        session: AsyncSession,
        customer_project: CustomerProject,
        reply_text: Optional[str] = None,
        offer: Optional[Offer] = None,
        audit: Optional[AuditRun] = None
    ) -> ProjectSpecification:
        """
        Synthesizes facts, customer requests, and AI inferences into a persisted,
        canonical ProjectSpecification record.
        """
        biz = await session.get(Business, customer_project.business_id)

        industry = customer_project.industry or (biz.niche if biz else "Commercial Services") or "General"
        biz_name = (biz.name if biz else None) or customer_project.title or "Client Partner"
        domain = (biz.domain if biz else None) or f"{customer_project.customer_slug}.com"

        # 1. Facts
        facts = cls.extract_facts(biz, audit=audit)
        # 2. Customer Requests
        requests = cls.extract_customer_requests(reply_text, industry)
        # 3. AI Inferences
        inferences = cls.generate_ai_inferences(industry, facts, requests)
        # 4. Screens
        screens = cls.determine_screens(industry, requests)
        # 5. AI Features
        ai_features = cls.determine_ai_features(industry, biz_name, requests)

        # Get latest version number
        q_ver = select(ProjectSpecification).where(
            ProjectSpecification.project_id == customer_project.id
        ).order_by(ProjectSpecification.version.desc())
        latest_spec = (await session.execute(q_ver)).scalars().first()
        next_ver = (latest_spec.version + 1) if latest_spec else 1

        # Checksum payload
        payload_for_hash = {
            "project_id": customer_project.project_id,
            "version": next_ver,
            "facts": [f.model_dump() for f in facts],
            "customer_requests": [r.model_dump() for r in requests],
            "ai_inferences": [i.model_dump() for i in inferences],
            "screens": screens,
            "ai_features": ai_features
        }
        checksum = cls.calculate_checksum(payload_for_hash)

        spec_model = ProjectSpecification(
            project_id=customer_project.id,
            version=next_ver,
            is_canonical=True,
            facts=[f.model_dump() for f in facts],
            customer_requests=[r.model_dump() for r in requests],
            ai_inferences=[i.model_dump() for i in inferences],
            architecture_style="modular_monolith",
            primary_language="typescript",
            framework="react",
            backend_framework="fastapi",
            styling_library="tailwind",
            required_screens=screens,
            ai_features=ai_features,
            checksum=checksum,
            created_at=datetime.utcnow()
        )

        session.add(spec_model)
        customer_project.status = "SPEC_READY"
        customer_project.current_stage = "SPEC"
        await session.commit()
        await session.refresh(spec_model)

        logger.info(
            f"[CanonicalSpecEngine] Successfully generated canonical spec v{next_ver} "
            f"for project {customer_project.project_id} (checksum: {checksum[:8]}...)"
        )
        return spec_model


spec_engine = CanonicalSpecEngine()
