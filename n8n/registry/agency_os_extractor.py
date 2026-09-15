"""
Agency OS — Proven Internal Workflow Extraction Loop.

Extracts proven internal Agency OS business workflows into standardized,
sanitized, and documented commercial n8n product candidates.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from n8n.registry.source_ingester import (
    N8nSourceIngester, source_ingester, LicenseStatus, SecurityStatus
)
from n8n.registry.validator import GovernanceViolation, validate_template_directory


class AgencyOsWorkflowExtractor:
    """
    Automates extraction of core Agency OS production services into commercial n8n templates.
    """

    PROVEN_AGENCY_SERVICES = {
        "domain_enrichment_diagnostic_vector": {
            "source_path": "app/audit/audit_service.py",
            "workflow_name": "AGY-AUDIT-DomainEnrichment-DiagnosticVector-v1.0",
            "category": "lead enrichment",
            "use_case": "Automated 6-vector prospect website diagnostic check, technology stack detection, performance scoring, and pain-point extraction for high-conversion B2B client intelligence.",
            "dependencies": [
                "n8n-nodes-base.webhook",
                "n8n-nodes-base.httpRequest",
                "n8n-nodes-base.code",
                "n8n-nodes-base.if",
                "n8n-nodes-base.respondToWebhook"
            ],
            "inputs": ["Prospect business name", "Website domain URL", "Target market/country"],
            "outputs": ["Overall health score (0-100)", "Diagnostic vector breakdown", "Key commercial deficits identified"]
        },
        "commercial_floor_scoring": {
            "source_path": "app/scoring/commercial_scoring.py",
            "workflow_name": "AGY-SCORE-LeadQualification-CommercialFloor-v1.0",
            "category": "lead qualification",
            "use_case": "Commercial feasibility scoring enforcing strict $500 project value floor, ICP alignment metrics, commercial priority tagging (HIGH/MEDIUM/LOW), and automated lead routing.",
            "dependencies": [
                "n8n-nodes-base.webhook",
                "n8n-nodes-base.code",
                "n8n-nodes-base.switch",
                "n8n-nodes-base.respondToWebhook"
            ],
            "inputs": ["Audit findings JSON", "Prospect revenue estimate / headcount", "Industry niche code"],
            "outputs": ["Commercial priority tag (HIGH/MED/LOW)", "Feasibility score (0-100)", "Commercial floor pass/fail boolean"]
        },
        "inbound_intent_classifier": {
            "source_path": "app/crm/reply_classifier.py",
            "workflow_name": "AGY-CRM-InboundReply-IntentClassifier-v1.0",
            "category": "reply classification",
            "use_case": "Inbound email reply sentiment and intent categorization (POSITIVE, OBJECTION, QUESTION, NOT_INTERESTED, UNSUBSCRIBE), auto-cancels scheduled follow-ups, and triggers CEO requirements alert.",
            "dependencies": [
                "n8n-nodes-base.webhook",
                "n8n-nodes-base.code",
                "n8n-nodes-base.if",
                "n8n-nodes-base.switch",
                "n8n-nodes-base.respondToWebhook"
            ],
            "inputs": ["Raw inbound email text", "Sender email address", "Original outreach campaign ID"],
            "outputs": ["Classification category", "Confidence score", "Actionable routing trigger"]
        },
        "cold_outreach_safety_guard": {
            "source_path": "app/outreach/generator.py",
            "workflow_name": "AGY-OUTREACH-PersonalizedDrafter-SafetyGuard-v1.0",
            "category": "personalized outreach",
            "use_case": "Evidence-grounded cold outreach synthesizer linking audit findings to concrete business value, equipped with CAN-SPAM compliance validation, unsubscribe headers, and approval gating.",
            "dependencies": [
                "n8n-nodes-base.webhook",
                "n8n-nodes-base.code",
                "n8n-nodes-base.if",
                "n8n-nodes-base.respondToWebhook"
            ],
            "inputs": ["Canonical prospect record", "Verified audit facts", "Matched commercial solution"],
            "outputs": ["Three concise email variants (60-140 words)", "Pre-send validation pass/fail", "Opt-out footer compliance check"]
        },
        "smart_cadence_auto_cancel": {
            "source_path": "app/outreach/followups.py",
            "workflow_name": "AGY-FOLLOWUP-SmartCadence-AutoCancelOnReply-v1.0",
            "category": "sales follow-up",
            "use_case": "Intelligent multi-stage follow-up sequencer honoring business days and recipient timezone, with automatic real-time cancellation upon inbound reply or unsubscribe.",
            "dependencies": [
                "n8n-nodes-base.webhook",
                "n8n-nodes-base.code",
                "n8n-nodes-base.if",
                "n8n-nodes-base.respondToWebhook"
            ],
            "inputs": ["Active campaign ID", "Recipient contact info", "Followup stage index"],
            "outputs": ["Scheduled timestamp (local timezone)", "Cancellation trigger listener active"]
        }
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent.parent
        self.ingester = N8nSourceIngester(self.base_dir)

    def extract_internal_workflow(
        self,
        service_key: str,
        workflow_json: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extracts, sanitizes, documents, and packages an Agency OS internal service as a commercial n8n template.
        """
        if service_key not in self.PROVEN_AGENCY_SERVICES:
            raise GovernanceViolation(f"Unknown internal service key: {service_key}")

        spec = self.PROVEN_AGENCY_SERVICES[service_key]
        return self.ingester.process_candidate(
            source_repo="https://github.com/Sufiyan367/agency-os",
            source_path=spec["source_path"],
            source_license="PROPRIETARY_AGENCY_OS",
            workflow_name=spec["workflow_name"],
            category=spec["category"],
            use_case=spec["use_case"],
            raw_workflow_json=workflow_json,
            dependencies=spec["dependencies"],
            inputs=spec["inputs"],
            outputs=spec["outputs"]
        )


workflow_extractor = AgencyOsWorkflowExtractor()
