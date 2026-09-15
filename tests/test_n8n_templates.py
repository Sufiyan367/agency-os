import json
from pathlib import Path
import pytest
from n8n.registry.validator import run_full_validation, scan_for_secrets, GovernanceViolation, validate_registry


@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parent.parent


def test_n8n_governance_validation(repo_root):
    """Verify that all n8n templates and the registry pass strict governance checks."""
    result = run_full_validation(repo_root)
    assert result["status"] == "PASS"
    assert result["total_registered_workflows"] >= 5
    assert result["active_templates_validated"] >= 5
    assert result["intelligence_sources_catalogued"] == 5


def test_no_hardcoded_secrets_in_templates(repo_root):
    """Strictly assert zero API keys, passwords, or tokens in all n8n template files."""
    templates_dir = repo_root / "n8n" / "templates"
    for file_path in templates_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix in (".json", ".md"):
            content = file_path.read_text(encoding="utf-8")
            secrets = scan_for_secrets(content, str(file_path))
            assert len(secrets) == 0, f"Secret detected in {file_path}: {secrets}"


def test_license_gate_enforcement(repo_root):
    """Ensure workflows with missing or restricted licenses are strictly blocked from commercialization."""
    reg_path = repo_root / "n8n" / "registry" / "workflow_registry.json"
    data = validate_registry(reg_path)
    
    for wf in data["workflows"]:
        if wf["source_license"] == "NO_LICENSE_ALL_RIGHTS_RESERVED" or wf["adaptation_status"] == "BLOCKED_LICENSE":
            assert wf["commercialization_status"] == "BLOCKED_LICENSE"
            assert wf["commercialization_status"] != "COMMERCIAL_READY"


def test_template_json_schema(repo_root):
    """Verify nodes, connections, and required trigger nodes exist in all active workflow.json files."""
    templates_dir = repo_root / "n8n" / "templates"
    for wf_file in templates_dir.rglob("workflow.json"):
        with open(wf_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "name" in data
        assert "nodes" in data and isinstance(data["nodes"], list) and len(data["nodes"]) > 0
        assert "connections" in data and isinstance(data["connections"], dict)
        
        # Verify webhook or trigger node exists
        node_types = [n.get("type") for n in data["nodes"]]
        assert any("webhook" in t or "trigger" in t.lower() for t in node_types), f"No trigger in {wf_file}"
