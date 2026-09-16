"""
Agency OS — Solution Capability Catalog.
Defines canonical software & automation capabilities offered by the agency,
including requirements, dependencies, cost profiles, risk levels, and compatible n8n/Demo blueprints.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class SolutionCapability(BaseModel):
    """
    Structured definition of a commercial agency capability.
    """
    capability_id: str
    name: str
    category: str
    description: str
    requirements: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    cost_profile_usd: float = 25.0
    target_price_usd: float = 1000.0
    complexity_level: str = "MODERATE"  # LOW, MODERATE, HIGH, ENTERPRISE
    risk_level: str = "LOW"             # LOW, MEDIUM, HIGH
    compatible_n8n_templates: List[str] = Field(default_factory=list)
    demo_blueprint_type: str = "booking_flow"
    expected_outcomes: List[str] = Field(default_factory=list)


CAPABILITY_REGISTRY: List[SolutionCapability] = [
    SolutionCapability(
        capability_id="CAP-001-LEAD-CAPTURE",
        name="High-Conversion Intake & Qualification Flow",
        category="Lead Response",
        description="Frictionless multi-step inquiry intake with instant qualification scoring, lead routing, and immediate notification.",
        requirements=["Web intake form or chat embed", "Notification webhook/SMS", "Qualification rubric"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.code", "n8n-nodes-base.httpRequest"],
        cost_profile_usd=15.0,
        target_price_usd=850.0,
        complexity_level="LOW",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-SCORE-LeadQualification-CommercialFloor-v1.0"],
        demo_blueprint_type="intake_portal",
        expected_outcomes=["Reduce response latency to < 60 seconds", "Filter unqualified inquiries before manual rep review"]
    ),
    SolutionCapability(
        capability_id="CAP-002-BOOKING-AUTOMATION",
        name="24/7 Self-Serve Appointment & Dispatch Engine",
        category="Appointment Scheduling",
        description="Interactive scheduling stepper with live calendar synchronization, timezone handling, and automated reminders.",
        requirements=["Calendar integration (Google/Outlook/Cal)", "Time-slot validation", "Cancellation/rescheduling link generation"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.dateTime", "n8n-nodes-base.httpRequest"],
        cost_profile_usd=20.0,
        target_price_usd=1200.0,
        complexity_level="MODERATE",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-CRM-InboundReply-IntentClassifier-v1.0"],
        demo_blueprint_type="booking_flow",
        expected_outcomes=["Eliminate phone-tag scheduling delays", "Capture after-hours high-intent bookings"]
    ),
    SolutionCapability(
        capability_id="CAP-003-PRICING-ESTIMATOR",
        name="Instant Cost & Project Estimator Widget",
        category="Website Conversion",
        description="Dynamic client-facing pricing calculator estimating project tiers in real-time, capturing contact details before estimate delivery.",
        requirements=["Pricing matrix / formula parameters", "Gated result email delivery", "PDF estimate generator"],
        dependencies=["n8n-nodes-base.code", "n8n-nodes-base.respondToWebhook"],
        cost_profile_usd=10.0,
        target_price_usd=1000.0,
        complexity_level="LOW",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-AUDIT-DomainEnrichment-DiagnosticVector-v1.0"],
        demo_blueprint_type="calculator",
        expected_outcomes=["Increase website visitor-to-lead conversion by 2-3x", "Anchor buyer price expectations early"]
    ),
    SolutionCapability(
        capability_id="CAP-004-CRM-PIPELINE-SYNC",
        name="Bi-Directional CRM & Pipeline Data Synchronizer",
        category="CRM/Data Entry",
        description="Deterministic webhook and event-driven synchronization between website forms, email replies, and CRM records.",
        requirements=["CRM API access (HubSpot, Pipedrive, or Custom)", "Event deduplication", "Error queue with retries"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.httpRequest", "n8n-nodes-base.splitInBatches"],
        cost_profile_usd=30.0,
        target_price_usd=1500.0,
        complexity_level="HIGH",
        risk_level="MEDIUM",
        compatible_n8n_templates=["AGY-CRM-InboundReply-IntentClassifier-v1.0"],
        demo_blueprint_type="crm_pipeline",
        expected_outcomes=["Eliminate manual copy-paste between tools", "Ensure zero lost lead attribution"]
    ),
    SolutionCapability(
        capability_id="CAP-005-AI-CONCIERGE",
        name="AI Knowledge & Customer Service Concierge",
        category="Customer Support",
        description="Grounded conversational assistant answering service inquiries, company policies, and routing complex cases to humans.",
        requirements=["Service FAQs and business profile docs", "Gemini AI model integration", "Confidence threshold fallback"],
        dependencies=["n8n-nodes-base.webhook", "@n8n/n8n-nodes-langchain.agent", "n8n-nodes-base.httpRequest"],
        cost_profile_usd=40.0,
        target_price_usd=1800.0,
        complexity_level="HIGH",
        risk_level="MEDIUM",
        compatible_n8n_templates=["AGY-CRM-InboundReply-IntentClassifier-v1.0"],
        demo_blueprint_type="ai_chat",
        expected_outcomes=["Resolve 60%+ routine questions instantly", "24/7 brand representation"]
    ),
    SolutionCapability(
        capability_id="CAP-006-INVOICE-AP-EXTRACTOR",
        name="Automated Invoice & Document Ingestion Pipeline",
        category="Invoice/AP Processing",
        description="OCR and LLM-driven structured data extraction from PDF invoices into accounting tables with validation checks.",
        requirements=["Document inbox / file drop", "Structured schema definition", "Discrepancy review queue"],
        dependencies=["n8n-nodes-base.readBinaryFile", "n8n-nodes-base.httpRequest", "n8n-nodes-base.code"],
        cost_profile_usd=35.0,
        target_price_usd=1600.0,
        complexity_level="HIGH",
        risk_level="MEDIUM",
        compatible_n8n_templates=["AGY-AUDIT-DomainEnrichment-DiagnosticVector-v1.0"],
        demo_blueprint_type="intake_portal",
        expected_outcomes=["Cut AP processing time by 75%", "Prevent double-entry errors"]
    ),
]


class SolutionCapabilityCatalog:
    """
    Query interface for the Solution Capability Catalog.
    """

    def __init__(self, capabilities: Optional[List[SolutionCapability]] = None):
        self._capabilities = capabilities or CAPABILITY_REGISTRY

    def list_capabilities(self) -> List[SolutionCapability]:
        return list(self._capabilities)

    def get_capability(self, capability_id: str) -> Optional[SolutionCapability]:
        for cap in self._capabilities:
            if cap.capability_id == capability_id:
                return cap
        return None

    def find_by_category(self, category: str) -> List[SolutionCapability]:
        cat_lower = category.lower()
        return [c for c in self._capabilities if cat_lower in c.category.lower()]

    def find_by_n8n_template(self, template_name: str) -> Optional[SolutionCapability]:
        for cap in self._capabilities:
            if template_name in cap.compatible_n8n_templates:
                return cap
        return None


capability_catalog = SolutionCapabilityCatalog()
