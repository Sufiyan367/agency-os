"""
Agency OS — Focused Tests for Workstream A: N8N Product Engine.
Verifies Source Ingestion, 5 License Compliance States, Secret Scanning,
Topological Deduplication, 13-Section Packaging, Extraction Loop,
and Controlled 8-Step Execution Verification.
"""
import os
import json
import pytest
from pathlib import Path

from n8n.registry.source_ingester import N8nSourceIngester, LicenseStatus, SecurityStatus
from n8n.registry.agency_os_extractor import AgencyOsWorkflowExtractor
from n8n.registry.execution_verifier import (
    N8nExecutionVerifier,
    ExecutionVerificationState,
    CommercializationStatus
)


@pytest.mark.asyncio
async def test_license_compliance_gate():
    """Test verification of all 5 license compliance states."""
    ingester = N8nSourceIngester()

    # 1. ALLOWED
    res_mit = ingester.evaluate_license("MIT")
    assert res_mit.status == LicenseStatus.LICENSE_ALLOWED
    assert res_mit.can_commercialize is True

    res_apache = ingester.evaluate_license("Apache-2.0")
    assert res_apache.status == LicenseStatus.LICENSE_ALLOWED
    assert res_apache.can_commercialize is True

    # 2. REQUIRES_ATTRIBUTION
    res_cc = ingester.evaluate_license("CC-BY-4.0")
    assert res_cc.status == LicenseStatus.LICENSE_REQUIRES_ATTRIBUTION
    assert res_cc.requires_attribution is True

    # 3. REQUIRES_REVIEW
    res_mpl = ingester.evaluate_license("MPL-2.0")
    assert res_mpl.status == LicenseStatus.LICENSE_REQUIRES_REVIEW
    assert res_mpl.can_commercialize is False

    # 4. BLOCKED_LICENSE
    res_gpl = ingester.evaluate_license("GPL-3.0")
    assert res_gpl.status == LicenseStatus.BLOCKED_LICENSE
    assert res_gpl.can_commercialize is False

    res_no_lic = ingester.evaluate_license("NO_LICENSE_ALL_RIGHTS_RESERVED")
    assert res_no_lic.status == LicenseStatus.BLOCKED_LICENSE

    # 5. UNKNOWN_LICENSE
    res_unknown = ingester.evaluate_license("")
    assert res_unknown.status == LicenseStatus.UNKNOWN_LICENSE

    res_custom = ingester.evaluate_license("SomeMadeUpCustomLicense")
    assert res_custom.status == LicenseStatus.UNKNOWN_LICENSE


@pytest.mark.asyncio
async def test_security_and_secret_scanner():
    """Test that embedded API keys and secrets are identified and failed by security evaluation."""
    ingester = N8nSourceIngester()

    # Clean workflow
    clean_workflow = {
        "name": "Clean Webhook",
        "nodes": [
            {
                "name": "HTTP Request",
                "type": "n8n-nodes-base.httpRequest",
                "parameters": {
                    "url": "https://api.example.com",
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": "={{ $env.MY_API_KEY }}"}
                        ]
                    }
                }
            }
        ],
        "connections": {}
    }
    sec_clean = ingester.evaluate_security(clean_workflow)
    assert sec_clean.status == SecurityStatus.SECURITY_PASSED

    # Workflow with exposed secret
    workflow_with_secret = {
        "name": "Leaky Webhook",
        "nodes": [
            {
                "name": "HTTP Request",
                "type": "n8n-nodes-base.httpRequest",
                "parameters": {
                    "url": "https://api.example.com",
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": "Bearer sk-live-1234567890abcdef1234567890abcdef"}
                        ]
                    }
                }
            }
        ],
        "connections": {}
    }
    sec_leaky = ingester.evaluate_security(workflow_with_secret)
    assert sec_leaky.status == SecurityStatus.SECURITY_FAILED
    assert len(sec_leaky.violations) > 0


@pytest.mark.asyncio
async def test_structural_topological_deduplication():
    """Test that identical workflow topologies produce the exact same topological signature."""
    ingester = N8nSourceIngester()

    wf1 = {
        "nodes": [
            {"name": "NodeA", "type": "n8n-nodes-base.webhook", "parameters": {}},
            {"name": "NodeB", "type": "n8n-nodes-base.emailSend", "parameters": {}}
        ],
        "connections": {
            "NodeA": {"main": [[{"node": "NodeB", "type": "main", "index": 0}]]}
        }
    }

    wf2 = {
        "nodes": [
            {"name": "NodeB", "type": "n8n-nodes-base.emailSend", "parameters": {}},
            {"name": "NodeA", "type": "n8n-nodes-base.webhook", "parameters": {}}
        ],
        "connections": {
            "NodeA": {"main": [[{"node": "NodeB", "type": "main", "index": 0}]]}
        }
    }

    sig1 = ingester.compute_structural_signature(wf1)
    sig2 = ingester.compute_structural_signature(wf2)
    assert sig1 == sig2
    assert len(sig1) == 64  # SHA-256


@pytest.mark.asyncio
async def test_13_section_packaging_and_docs():
    """Test generation of the full 13-section commercial product package."""
    ingester = N8nSourceIngester()
    lic_check = ingester.evaluate_license("MIT")

    readme = ingester.generate_readme(
        workflow_name="Diagnostic Vector Intake",
        category="Lead Enrichment",
        use_case="Automated diagnostic pipeline for inbound prospect enrichment.",
        license_check=lic_check,
        source_repo="Agency OS Core Engine",
        source_path="app/audit/audit_service.py",
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.code"],
        inputs=["domain", "email"],
        outputs=["enrichment_data"],
        required_env_vars=["AGENCY_WEBHOOK_URL"]
    )

    expected_sections = [
        "## 1. What It Does",
        "## 2. Who It Is For",
        "## 3. Use Cases",
        "## 4. Required n8n Setup",
        "## 5. Required Credentials",
        "## 6. Inputs",
        "## 7. Outputs",
        "## 8. Installation",
        "## 9. Configuration",
        "## 10. Expected Behavior",
        "## 11. Error Handling",
        "## 12. License & Source Attribution",
        "## 13. Modification Notes"
    ]

    for sec in expected_sections:
        assert sec in readme, f"Missing required documentation section: {sec}"


@pytest.mark.asyncio
async def test_agency_os_extractor_core_workflows():
    """Test extracting Agency OS core operational services as commercial templates."""
    services = AgencyOsWorkflowExtractor.PROVEN_AGENCY_SERVICES
    assert len(services) >= 5

    assert "commercial_floor_scoring" in services
    assert "inbound_intent_classifier" in services
    assert "smart_cadence_auto_cancel" in services
    assert "domain_enrichment_diagnostic_vector" in services
    assert "cold_outreach_safety_guard" in services

    for key, spec in services.items():
        assert "workflow_name" in spec
        assert "category" in spec
        assert "use_case" in spec
        assert "dependencies" in spec
        assert len(spec["dependencies"]) > 0


@pytest.mark.asyncio
async def test_execution_verifier_8_step_pipeline():
    """Test 8-step controlled execution verification on commercial_floor_scoring template."""
    verifier = N8nExecutionVerifier()

    template_rel_path = "n8n/templates/lead_qualification/commercial_floor_scoring"
    test_payload = {
        "deal_value": 750.0,
        "traffic_score": 80.0,
        "industry": "Commercial Services"
    }
    expected_assertions = {
        "floor_passed": True,
        "commercial_priority": "HIGH_PRIORITY",
        "requires_human_review": False
    }

    report = verifier.verify_template_execution(
        template_rel_path=template_rel_path,
        test_payload=test_payload,
        expected_assertions=expected_assertions
    )

    assert report.overall_certified is True
    assert len(report.steps) == 8
    for step in report.steps:
        assert step.passed is True, f"Step {step.step_number} ({step.step_name}) failed: {step.details}"

    # Verify execution output
    assert report.output_sample["deal_value"] == 750.0
    assert report.output_sample["feasibility_score"] >= 80.0
    assert report.execution_state == ExecutionVerificationState.PRODUCTION_PROVEN
    assert report.commercialization_status == CommercializationStatus.COMMERCIAL_READY
    assert report.failure_path_tested is True


@pytest.mark.asyncio
async def test_execution_verifier_honest_states_and_audit():
    """Verify that catalog audit produces honest states without fake production claims."""
    verifier = N8nExecutionVerifier()
    audit = verifier.audit_all_catalog_workflows()

    assert "catalog_summary" in audit
    summary = audit["catalog_summary"]
    assert summary["total"] == 10
    assert summary["COMMERCIAL_READY"] >= 4
    assert summary["BLOCKED_LICENSE"] == 1
    assert summary["EXTERNAL_EXECUTION_BLOCKED"] >= 2

    workflows_by_name = {w["workflow_name"]: w for w in audit["workflows"]}

    # Blocked license workflow must not be marked production proven or commercial ready
    rag_wf = workflows_by_name["REF-RAG-MultiSourceResearch-v0.5"]
    assert rag_wf["commercialization_status"] == CommercializationStatus.BLOCKED_LICENSE
    assert rag_wf["execution_verification_state"] == ExecutionVerificationState.STATIC_VALIDATED

    # Workflow requiring external HubSpot token must be marked blocked
    hub_wf = workflows_by_name["REF-HUB-LinkedInEnrichment-HubSpot-v0.9"]
    assert hub_wf["commercialization_status"] == CommercializationStatus.REQUIRES_EXTERNAL_VERIFICATION
    assert hub_wf["execution_verification_state"] == ExecutionVerificationState.EXTERNAL_EXECUTION_BLOCKED

    # Core scoring workflow is proven in Agency OS core and commercial ready
    score_wf = workflows_by_name["AGY-SCORE-LeadQualification-CommercialFloor-v1.0"]
    assert score_wf["commercialization_status"] == CommercializationStatus.COMMERCIAL_READY
    assert score_wf["execution_verification_state"] == ExecutionVerificationState.PRODUCTION_PROVEN


@pytest.mark.asyncio
async def test_failure_path_verification():
    """Verify failure paths are deterministically tested and handled safely."""
    verifier = N8nExecutionVerifier()

    # 1. Commercial Floor Scoring failure path: deal below $500 floor
    floor_fail = verifier.verify_failure_path(
        {"nodes": [{"name": "commercial_floor_scoring"}]},
        {"COMMERCIAL_FLOOR_USD": 500.0}
    )
    assert floor_fail["tested"] is True
    assert floor_fail["passed"] is True
    assert "Sub-$500 floor correctly blocked" in floor_fail["details"]

    # 2. Inbound Intent failure path: unsubscribe / opt-out
    optout_fail = verifier.verify_failure_path(
        {"nodes": [{"name": "inbound_intent_classifier"}]},
        {}
    )
    assert optout_fail["tested"] is True
    assert optout_fail["passed"] is True
    assert "auto-cancelled" in optout_fail["details"]

