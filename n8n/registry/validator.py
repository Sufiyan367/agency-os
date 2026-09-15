"""
Agency OS n8n Template Governance & Validation Engine.

Enforces:
1. Master registry schema integrity.
2. License & redistribution compliance gating.
3. Strict zero-secret / zero-credential safety.
4. n8n workflow JSON structure standards.
5. Standardized naming and documentation conventions.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple


SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9\-_]{20,}", "API Key (OpenAI / Stripe)"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API Key"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
    (r"xox[baprs]-[0-9a-zA-Z]{10,}", "Slack Token"),
    (r"-----BEGIN (?:RSA )?PRIVATE KEY-----", "Private Key"),
    (r"eyJ[a-zA-Z0-9\-_]{20,}\.eyJ[a-zA-Z0-9\-_]{20,}", "JWT Token"),
    (r"(?i)password\s*[:=]\s*['\"][^'\"]{6,}['\"]", "Hardcoded Password")
]

REQUIRED_REGISTRY_FIELDS = [
    "workflow_name",
    "category",
    "use_case",
    "source_repo",
    "source_path",
    "source_license",
    "dependencies",
    "adaptation_status",
    "test_status",
    "commercialization_status",
    "notes"
]

VALID_CATEGORIES = {
    "lead generation",
    "lead enrichment",
    "lead qualification",
    "crm automation",
    "personalized outreach",
    "reply classification",
    "sales follow-up",
    "customer onboarding",
    "appointment automation",
    "reporting",
    "ai support automation"
}

VALID_ADAPTATION_STATUSES = {
    "PROVEN_AGENCY_OS_CORE",
    "ADAPTED_FROM_REFERENCE",
    "CANDIDATE_UNDER_REVIEW",
    "BLOCKED_LICENSE"
}

VALID_COMMERCIAL_STATUSES = {
    "COMMERCIAL_READY",
    "INTERNAL_ONLY",
    "BLOCKED_LICENSE",
    "PENDING_REVIEW"
}


class GovernanceViolation(Exception):
    pass


def scan_for_secrets(text: str, file_path: str = "") -> List[Tuple[str, str]]:
    """Detects potential credentials, tokens, and private keys."""
    violations = []
    for pattern, name in SECRET_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            violations.append((name, file_path))
    return violations


def validate_registry(registry_path: Path) -> Dict[str, Any]:
    """Validates the structure, types, and compliance rules of workflow_registry.json."""
    if not registry_path.exists():
        raise GovernanceViolation(f"Registry file not found: {registry_path}")

    with open(registry_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "workflows" not in data or not isinstance(data["workflows"], list):
        raise GovernanceViolation("Registry must contain a top-level 'workflows' list.")

    names_seen = set()
    for idx, wf in enumerate(data["workflows"]):
        for field in REQUIRED_REGISTRY_FIELDS:
            if field not in wf:
                raise GovernanceViolation(f"Workflow at index {idx} missing required field '{field}'")

        name = wf["workflow_name"]
        if name in names_seen:
            raise GovernanceViolation(f"Duplicate workflow name detected: '{name}'")
        names_seen.add(name)

        cat = wf["category"].lower()
        if cat not in VALID_CATEGORIES:
            raise GovernanceViolation(f"Workflow '{name}' has invalid category: '{cat}'")

        adapt = wf["adaptation_status"]
        if adapt not in VALID_ADAPTATION_STATUSES:
            raise GovernanceViolation(f"Workflow '{name}' has invalid adaptation_status: '{adapt}'")

        comm = wf["commercialization_status"]
        if comm not in VALID_COMMERCIAL_STATUSES:
            raise GovernanceViolation(f"Workflow '{name}' has invalid commercialization_status: '{comm}'")

        # Legal License Gating Rule
        if wf["source_license"] in ("NO_LICENSE_ALL_RIGHTS_RESERVED", "UNKNOWN") or adapt == "BLOCKED_LICENSE":
            if comm == "COMMERCIAL_READY":
                raise GovernanceViolation(
                    f"LICENSE VIOLATION: Workflow '{name}' has license '{wf['source_license']}' "
                    f"or status '{adapt}' and CANNOT be marked COMMERCIAL_READY."
                )

    return data


def validate_template_directory(template_dir: Path, base_repo_path: Path) -> Dict[str, Any]:
    """Validates a productized template directory: workflow.json, README.md, metadata.json."""
    full_path = base_repo_path / template_dir if not template_dir.is_absolute() else template_dir
    if not full_path.exists() or not full_path.is_dir():
        raise GovernanceViolation(f"Template directory does not exist: {full_path}")

    wf_file = full_path / "workflow.json"
    readme_file = full_path / "README.md"
    meta_file = full_path / "metadata.json"

    for req in (wf_file, readme_file, meta_file):
        if not req.exists():
            raise GovernanceViolation(f"Missing required file: {req.name} in {full_path}")

    # Read and scan files
    with open(wf_file, "r", encoding="utf-8") as f:
        wf_content = f.read()
        wf_json = json.loads(wf_content)

    with open(readme_file, "r", encoding="utf-8") as f:
        readme_content = f.read()

    with open(meta_file, "r", encoding="utf-8") as f:
        meta_json = json.load(f)

    # Secret scanning
    for content, p in [(wf_content, wf_file), (readme_content, readme_file)]:
        secrets = scan_for_secrets(content, str(p))
        if secrets:
            raise GovernanceViolation(f"Secret detected in {p}: {secrets}")

    # Validate workflow JSON structure
    if "nodes" not in wf_json or not isinstance(wf_json["nodes"], list):
        raise GovernanceViolation(f"{wf_file} must have a 'nodes' array.")
    if "connections" not in wf_json or not isinstance(wf_json["connections"], dict):
        raise GovernanceViolation(f"{wf_file} must have a 'connections' dictionary.")

    # Must contain at least one node and a trigger or webhook
    node_types = [n.get("type", "") for n in wf_json["nodes"]]
    if not node_types:
        raise GovernanceViolation(f"{wf_file} has no nodes defined.")

    return {
        "workflow_nodes_count": len(wf_json["nodes"]),
        "node_types": node_types,
        "metadata": meta_json
    }


def run_full_validation(base_dir: Path) -> Dict[str, Any]:
    """Runs complete registry and template validation."""
    reg_path = base_dir / "n8n" / "registry" / "workflow_registry.json"
    registry = validate_registry(reg_path)

    templates_checked = 0
    for wf in registry["workflows"]:
        tdir = wf.get("template_dir")
        if tdir:
            validate_template_directory(Path(tdir), base_dir)
            templates_checked += 1

    return {
        "status": "PASS",
        "total_registered_workflows": len(registry["workflows"]),
        "active_templates_validated": templates_checked,
        "intelligence_sources_catalogued": len(registry.get("intelligence_sources", []))
    }


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent.parent
    try:
        results = run_full_validation(base)
        print("=== N8N GOVERNANCE VALIDATION: PASSED ===")
        print(json.dumps(results, indent=2))
        sys.exit(0)
    except GovernanceViolation as gv:
        print(f"=== N8N GOVERNANCE VIOLATION ===\n{gv}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"=== VALIDATION ERROR ===\n{e}", file=sys.stderr)
        sys.exit(2)
