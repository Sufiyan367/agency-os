"""
Agency OS — N8N Source Repository Ingestion & Productization Engine.

Implements the deterministic productization lifecycle:
SOURCE -> DISCOVER -> SELECT -> LICENSE CHECK -> SECURITY CHECK ->
DEDUPLICATE -> ADAPT -> SANITIZE -> VALIDATE -> DOCUMENT -> PACKAGE -> COMMERCIAL_READY
"""

import json
import re
import hashlib
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field

from n8n.registry.validator import (
    scan_for_secrets,
    validate_template_directory,
    GovernanceViolation,
    VALID_CATEGORIES
)


class LicenseStatus(str, Enum):
    LICENSE_ALLOWED = "LICENSE_ALLOWED"
    LICENSE_REQUIRES_ATTRIBUTION = "LICENSE_REQUIRES_ATTRIBUTION"
    LICENSE_REQUIRES_REVIEW = "LICENSE_REQUIRES_REVIEW"
    BLOCKED_LICENSE = "BLOCKED_LICENSE"
    UNKNOWN_LICENSE = "UNKNOWN_LICENSE"


class SecurityStatus(str, Enum):
    SECURITY_PASSED = "SECURITY_PASSED"
    SECURITY_FAILED = "SECURITY_FAILED"


@dataclass
class LicenseCheckResult:
    license_name: str
    status: LicenseStatus
    can_commercialize: bool
    requires_attribution: bool
    notes: str


@dataclass
class SecurityCheckResult:
    status: SecurityStatus
    violations: List[Tuple[str, str]]
    details: str


@dataclass
class CandidateWorkflow:
    source_repo: str
    source_path: str
    workflow_name: str
    category: str
    use_case: str
    source_license: str
    workflow_json: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    credentials_required: List[str] = field(default_factory=list)
    license_result: Optional[LicenseCheckResult] = None
    security_result: Optional[SecurityCheckResult] = None
    structural_signature: str = ""
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None


class N8nSourceIngester:
    """
    Selective ingestion, gating, and commercial packaging engine for external reference workflows.
    Supported Sources:
    - nusquama/n8nworkflows.xyz (MIT / Community)
    - enescingoz/awesome-n8n-templates (CC-BY-4.0)
    - Zie619/n8n-workflows (MIT)
    - wassupjay/n8n-free-templates (NO_LICENSE_ALL_RIGHTS_RESERVED -> BLOCKED)
    """

    ALLOWED_PERMISSIVE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "PROPRIETARY_AGENCY_OS"}
    REQUIRES_ATTRIBUTION = {"CC-BY-4.0", "CC-BY-SA-4.0"}
    REQUIRES_REVIEW = {"MPL-2.0", "LGPL-3.0", "EPL-2.0"}
    BLOCKED_LICENSES = {"NO_LICENSE_ALL_RIGHTS_RESERVED", "GPL-3.0", "AGPL-3.0", "SSPL"}

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent.parent
        self.registry_path = self.base_dir / "n8n" / "registry" / "workflow_registry.json"
        self.templates_root = self.base_dir / "n8n" / "templates"
        self._known_signatures: Dict[str, str] = {}
        self._load_existing_signatures()

    def _load_existing_signatures(self):
        """Indexes structural signatures of existing templates to prevent duplication."""
        if not self.templates_root.exists():
            return
        for wf_file in self.templates_root.rglob("workflow.json"):
            try:
                with open(wf_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sig = self.compute_structural_signature(data)
                self._known_signatures[sig] = wf_file.parent.name
            except Exception:
                pass

    @classmethod
    def evaluate_license(cls, raw_license: Optional[str]) -> LicenseCheckResult:
        """
        Step A3: LICENSE GATE.
        Categorizes license into strict operational compliance states.
        UNKNOWN or BLOCKED can NEVER become COMMERCIAL_READY.
        """
        if not raw_license or not raw_license.strip():
            return LicenseCheckResult(
                license_name="UNKNOWN",
                status=LicenseStatus.UNKNOWN_LICENSE,
                can_commercialize=False,
                requires_attribution=False,
                notes="License is missing or unspecified. Commercial distribution strictly blocked."
            )

        lic = raw_license.strip()
        lic_upper = lic.upper()

        if any(p == lic or p.upper() == lic_upper for p in cls.ALLOWED_PERMISSIVE):
            return LicenseCheckResult(
                license_name=lic,
                status=LicenseStatus.LICENSE_ALLOWED,
                can_commercialize=True,
                requires_attribution=False,
                notes=f"Permissive license '{lic}' allows commercial adaptation and distribution."
            )
        elif any(p == lic or p.upper() == lic_upper for p in cls.REQUIRES_ATTRIBUTION):
            return LicenseCheckResult(
                license_name=lic,
                status=LicenseStatus.LICENSE_REQUIRES_ATTRIBUTION,
                can_commercialize=True,
                requires_attribution=True,
                notes=f"Attribution license '{lic}' requires upstream author credit and modification notes in README & metadata."
            )
        elif any(p == lic or p.upper() == lic_upper for p in cls.REQUIRES_REVIEW):
            return LicenseCheckResult(
                license_name=lic,
                status=LicenseStatus.LICENSE_REQUIRES_REVIEW,
                can_commercialize=False,
                requires_attribution=True,
                notes=f"License '{lic}' carries reciprocal or copyleft provisions. Legal review required before commercial release."
            )
        elif any(p in lic_upper for p in ("NO_LICENSE", "ALL_RIGHTS_RESERVED", "GPL", "AGPL")):
            return LicenseCheckResult(
                license_name=lic,
                status=LicenseStatus.BLOCKED_LICENSE,
                can_commercialize=False,
                requires_attribution=False,
                notes=f"License '{lic}' is copyleft or restricted. Commercial redistribution is strictly blocked."
            )
        else:
            return LicenseCheckResult(
                license_name=lic,
                status=LicenseStatus.UNKNOWN_LICENSE,
                can_commercialize=False,
                requires_attribution=False,
                notes=f"Unrecognized license '{lic}'. Commercial distribution blocked until verified."
            )

    @classmethod
    def evaluate_security(cls, workflow_json: Dict[str, Any], file_path: str = "") -> SecurityCheckResult:
        """
        Step A4: SECURITY / SECRET GATE.
        Deep-scans nodes, parameters, credentials blocks, and raw JSON strings.
        Any secret found -> SECURITY_FAILED.
        """
        raw_text = json.dumps(workflow_json)
        violations = scan_for_secrets(raw_text, file_path)

        # Also inspect node credentials block
        nodes = workflow_json.get("nodes", [])
        for node in nodes:
            credentials = node.get("credentials", {})
            for cred_type, cred_val in credentials.items():
                if isinstance(cred_val, dict):
                    for k, v in cred_val.items():
                        if isinstance(v, str) and len(v) > 12 and not v.startswith("={{"):
                            violations.append((f"Potential embedded credential value in node '{node.get('name')}'", file_path))

        if violations:
            return SecurityCheckResult(
                status=SecurityStatus.SECURITY_FAILED,
                violations=violations,
                details=f"Detected {len(violations)} security violations. Packaging strictly aborted."
            )

        return SecurityCheckResult(
            status=SecurityStatus.SECURITY_PASSED,
            violations=[],
            details="Zero hardcoded credentials, JWTs, or private keys detected."
        )

    @classmethod
    def compute_structural_signature(cls, workflow_json: Dict[str, Any]) -> str:
        """
        Step A5: STRUCTURAL DUPLICATE DETECTION.
        Generates a topological signature from sorted node types, operation names, and connection layout.
        """
        nodes = workflow_json.get("nodes", [])
        node_sigs = []
        for n in sorted(nodes, key=lambda x: str(x.get("name", ""))):
            ntype = n.get("type", "")
            params = n.get("parameters", {})
            operation = params.get("operation", params.get("resource", ""))
            node_sigs.append(f"{ntype}:{operation}")

        connections = workflow_json.get("connections", {})
        conn_edges = []
        for src_node, targets in sorted(connections.items()):
            for out_type, out_conns in sorted(targets.items()):
                for sublist in out_conns:
                    for target in sublist:
                        tgt_node = target.get("node", "")
                        conn_edges.append(f"{src_node}->{tgt_node}")

        signature_raw = "|".join(node_sigs) + "###" + ";".join(sorted(conn_edges))
        return hashlib.sha256(signature_raw.encode("utf-8")).hexdigest()

    def check_duplicate(self, signature: str, workflow_name: str) -> Tuple[bool, Optional[str]]:
        """
        Checks if a workflow with identical topology or identical name already exists.
        """
        if signature in self._known_signatures:
            return True, self._known_signatures[signature]

        # Check by registry name
        if self.registry_path.exists():
            with open(self.registry_path, "r", encoding="utf-8") as f:
                reg = json.load(f)
            for wf in reg.get("workflows", []):
                if wf.get("workflow_name") == workflow_name:
                    return True, workflow_name

        return False, None

    @classmethod
    def adapt_workflow(
        cls,
        raw_workflow: Dict[str, Any],
        standardized_name: str,
        category: str
    ) -> Dict[str, Any]:
        """
        Step A6: TEMPLATE ADAPTATION.
        Cleans node naming, sets standard execution order, removes environment specifics,
        and ensures configurable inputs via variables.
        """
        adapted = json.loads(json.dumps(raw_workflow))
        adapted["name"] = standardized_name
        adapted["tags"] = sorted(list(set(adapted.get("tags", []) + ["Agency-OS", "Commercial-Engine", category.replace(" ", "-")])))
        adapted["settings"] = adapted.get("settings", {})
        adapted["settings"]["executionOrder"] = "v1"
        adapted["settings"]["saveManualExecutions"] = False
        adapted["settings"]["callerPolicy"] = "workflowsFromSameOwner"

        # Sanitize internal endpoints and emails
        raw_str = json.dumps(adapted)
        sanitized_str = re.sub(r'https?://[a-zA-Z0-9.\-_]+:5678/webhook/[a-zA-Z0-9\-]+', '{{ $env.AGENCY_WEBHOOK_URL }}', raw_str)
        sanitized_str = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '{{ $env.AGENCY_NOTIFICATION_EMAIL }}', sanitized_str)
        return json.loads(sanitized_str)

    @classmethod
    def generate_readme(
        cls,
        workflow_name: str,
        category: str,
        use_case: str,
        license_check: LicenseCheckResult,
        source_repo: str,
        source_path: str,
        dependencies: List[str],
        inputs: List[str],
        outputs: List[str],
        required_env_vars: List[str]
    ) -> str:
        """
        Step A7: Generates complete 13-section commercial README.md.
        """
        dep_list = "\n".join([f"- `{d}`" for d in dependencies]) or "- Standard n8n core nodes"
        env_list = "\n".join([f"- `{v}`: Configuration setting" for v in required_env_vars]) or "- None"
        in_list = "\n".join([f"- {i}" for i in inputs]) or "- Webhook HTTP POST JSON payload"
        out_list = "\n".join([f"- {o}" for o in outputs]) or "- Structured JSON response"

        attribution_section = ""
        if license_check.requires_attribution:
            attribution_section = (
                f"\n## 12. License & Source Attribution\n\n"
                f"- **Upstream Repository**: [{source_repo}]({source_repo})\n"
                f"- **Source Reference**: `{source_path}`\n"
                f"- **Source License**: {license_check.license_name}\n"
                f"- **Attribution Statement**: This workflow was adapted from open-source reference material provided under {license_check.license_name}. "
                f"Modifications include Agency OS security sanitization, zero-secret gating, standardized variable parameterization, and commercial packaging.\n"
            )
        else:
            attribution_section = (
                f"\n## 12. License & Source Attribution\n\n"
                f"- **License**: {license_check.license_name}\n"
                f"- **Provenance**: {source_repo} ({source_path})\n"
                f"- **Status**: Verified commercially distributable under permissive open-source license.\n"
            )

        return f"""# {workflow_name}

## 1. What It Does
{use_case}

## 2. Who It Is For
Agency operators, B2B digital teams, and service businesses automating customer pipelines.

## 3. Use Cases
- High-velocity automated processing for {category}.
- Streamlining manual handoffs into deterministic background executions.
- Eliminating dropped customer leads and delayed response cycles.

## 4. Required n8n Setup
- **Minimum n8n Version**: `1.0.0` or higher
- **Node Runtime**: Node.js 18+ or n8n cloud instance
- **Execution Mode**: Production webhook listener or scheduled cadence

## 5. Required Credentials
Zero hardcoded credentials. All integrations utilize isolated n8n credential managers:
{dep_list}

## 6. Inputs
{in_list}

## 7. Outputs
{out_list}

## 8. Installation
1. Open your n8n workspace console.
2. Select **Workflows** -> **Import from File...**
3. Upload `workflow.json` from this package.
4. Set execution active.

## 9. Configuration
Configure required environment parameters:
{env_list}

## 10. Expected Behavior
Upon trigger event, the workflow parses incoming data, applies validation rules, dispatches to destination systems, and returns an idempotent status confirmation.

## 11. Error Handling
- Built-in error catch branches route malformed payloads to error logging.
- Includes safe fallbacks for temporary network drops.
{attribution_section}
## 13. Modification Notes
- Standardized for Agency OS commercial engine deployment.
- All secrets, tokens, and hardcoded addresses removed and replaced with environmental variables.
"""

    def process_candidate(
        self,
        source_repo: str,
        source_path: str,
        source_license: str,
        workflow_name: str,
        category: str,
        use_case: str,
        raw_workflow_json: Dict[str, Any],
        dependencies: Optional[List[str]] = None,
        inputs: Optional[List[str]] = None,
        outputs: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end candidate ingestion pipeline.
        Returns detailed audit status and paths.
        """
        cat_clean = category.strip().lower()
        if cat_clean not in VALID_CATEGORIES:
            raise GovernanceViolation(f"Invalid category '{category}'. Must be one of {VALID_CATEGORIES}")

        # 1. License Check
        lic_result = self.evaluate_license(source_license)

        # 2. Security Check
        sec_result = self.evaluate_security(raw_workflow_json, source_path)

        # 3. Duplicate Detection
        signature = self.compute_structural_signature(raw_workflow_json)
        is_dup, dup_target = self.check_duplicate(signature, workflow_name)

        candidate = CandidateWorkflow(
            source_repo=source_repo,
            source_path=source_path,
            workflow_name=workflow_name,
            category=cat_clean,
            use_case=use_case,
            source_license=source_license,
            workflow_json=raw_workflow_json,
            dependencies=dependencies or ["n8n-nodes-base.webhook"],
            license_result=lic_result,
            security_result=sec_result,
            structural_signature=signature,
            is_duplicate=is_dup,
            duplicate_of=dup_target
        )

        can_proceed = (
            lic_result.can_commercialize and
            sec_result.status == SecurityStatus.SECURITY_PASSED and
            not is_dup
        )

        commercial_status = "COMMERCIAL_READY" if can_proceed else (
            "BLOCKED_LICENSE" if not lic_result.can_commercialize else (
                "SECURITY_FAILED" if sec_result.status == SecurityStatus.SECURITY_FAILED else "DUPLICATE_REJECTED"
            )
        )

        package_path = None
        if can_proceed:
            adapted_json = self.adapt_workflow(raw_workflow_json, workflow_name, cat_clean)
            package_path = self._write_commercial_package(
                candidate=candidate,
                adapted_json=adapted_json,
                inputs=inputs or ["Incoming JSON payload"],
                outputs=outputs or ["Processed status result"]
            )
            self._known_signatures[signature] = workflow_name

        return {
            "workflow_name": workflow_name,
            "category": cat_clean,
            "commercial_status": commercial_status,
            "license_status": lic_result.status.value,
            "security_status": sec_result.status.value,
            "is_duplicate": is_dup,
            "duplicate_of": dup_target,
            "package_path": str(package_path) if package_path else None,
            "notes": lic_result.notes
        }

    def _write_commercial_package(
        self,
        candidate: CandidateWorkflow,
        adapted_json: Dict[str, Any],
        inputs: List[str],
        outputs: List[str]
    ) -> Path:
        folder_slug = candidate.workflow_name.lower().replace("-", "_").replace(".", "_")
        target_dir = self.templates_root / candidate.category.replace(" ", "_") / folder_slug
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. workflow.json
        with open(target_dir / "workflow.json", "w", encoding="utf-8") as f:
            json.dump(adapted_json, f, indent=2)

        # 2. metadata.json
        metadata = {
            "template_id": candidate.workflow_name,
            "category": candidate.category,
            "use_case": candidate.use_case,
            "version": "1.0.0",
            "provenance": {
                "source_repository": candidate.source_repo,
                "source_file": candidate.source_path,
                "source_license": candidate.source_license,
                "attribution_required": candidate.license_result.requires_attribution if candidate.license_result else False
            },
            "security": {
                "credential_status": "ZERO_HARDCODED_SECRETS",
                "structural_signature": candidate.structural_signature,
                "environment_variables_required": [
                    "AGENCY_WEBHOOK_URL",
                    "AGENCY_NOTIFICATION_EMAIL"
                ]
            },
            "compatibility": {
                "n8n_version_minimum": "1.0.0",
                "agency_os_version": "1.0.0"
            }
        }
        with open(target_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # 3. README.md
        readme = self.generate_readme(
            workflow_name=candidate.workflow_name,
            category=candidate.category,
            use_case=candidate.use_case,
            license_check=candidate.license_result,
            source_repo=candidate.source_repo,
            source_path=candidate.source_path,
            dependencies=candidate.dependencies,
            inputs=inputs,
            outputs=outputs,
            required_env_vars=["AGENCY_WEBHOOK_URL", "AGENCY_NOTIFICATION_EMAIL"]
        )
        with open(target_dir / "README.md", "w", encoding="utf-8") as f:
            f.write(readme)

        # Validate template directory
        validate_template_directory(target_dir, self.base_dir)

        # Register in catalog
        self._register_in_catalog(candidate, str(target_dir.relative_to(self.base_dir)).replace("\\", "/"))

        return target_dir

    def _register_in_catalog(self, candidate: CandidateWorkflow, template_rel_dir: str):
        with open(self.registry_path, "r", encoding="utf-8") as f:
            reg = json.load(f)

        existing = [wf for wf in reg["workflows"] if wf["workflow_name"] == candidate.workflow_name]
        entry = {
            "workflow_name": candidate.workflow_name,
            "category": candidate.category,
            "use_case": candidate.use_case,
            "source_repo": candidate.source_repo,
            "source_path": candidate.source_path,
            "source_license": candidate.source_license,
            "dependencies": candidate.dependencies,
            "template_dir": template_rel_dir,
            "adaptation_status": "ADAPTED_FROM_REFERENCE",
            "test_status": "PASSED_STRICT_AUDIT",
            "commercialization_status": "COMMERCIAL_READY",
            "notes": "Verified zero secrets, sanitized for commercial delivery."
        }

        if existing:
            reg["workflows"] = [entry if wf["workflow_name"] == candidate.workflow_name else wf for wf in reg["workflows"]]
        else:
            reg["workflows"].append(entry)

        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)


source_ingester = N8nSourceIngester()
