"""
Automated Demo QA Engine — Phase 19.
Deterministic validation of generated demo artifacts against rigorous quality gates.
"""
import os
import json
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.delivery.demo_factory import DemoGenerationResult, DemoArtifactMetadata
from app.delivery.requirements_engine import RequirementsPacket
from app.core.logging import logger


class QACheckItem(BaseModel):
    name: str
    passed: bool
    details: str


class DemoQAResult(BaseModel):
    demo_id: str
    overall_passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    checks: List[QACheckItem]
    qa_signature: str
    error_summary: Optional[str] = None


class DemoQAEngine:
    """
    Deterministic automated quality assurance engine validating the generated demo package.
    """

    @classmethod
    def validate_demo(
        cls,
        demo_result: DemoGenerationResult,
        packet: RequirementsPacket
    ) -> DemoQAResult:
        checks: List[QACheckItem] = []
        meta = demo_result.metadata
        html = demo_result.html_content

        # 1. FILE_EXISTENCE Gate
        html_exists = os.path.exists(meta.html_file_path) and os.path.getsize(meta.html_file_path) > 0
        html_filename = os.path.basename(meta.html_file_path)
        checks.append(QACheckItem(
            name="FILE_EXISTENCE_HTML",
            passed=html_exists,
            details=f"HTML artifact file '{html_filename}' exists ({os.path.getsize(meta.html_file_path) if html_exists else 0} bytes)"
        ))

        json_exists = os.path.exists(meta.json_spec_path) and os.path.getsize(meta.json_spec_path) > 0
        spec_filename = os.path.basename(meta.json_spec_path)
        checks.append(QACheckItem(
            name="FILE_EXISTENCE_SPEC",
            passed=json_exists,
            details=f"Spec artifact file '{spec_filename}' exists"
        ))

        # 2. IDENTITY_INTEGRITY Gate
        name_in_html = meta.business_name in html
        domain_in_html = meta.domain in html
        identity_ok = name_in_html and domain_in_html
        checks.append(QACheckItem(
            name="IDENTITY_INTEGRITY",
            passed=identity_ok,
            details=f"Business name '{meta.business_name}' and domain '{meta.domain}' present in demo."
        ))

        # 3. COMMERCIAL_ALIGNMENT Gate
        price_in_html = f"{meta.price_usd:,.2f}" in html or f"{meta.price_usd:.2f}" in html or f"{int(meta.price_usd)}" in html
        price_above_floor = meta.price_usd >= 500.0
        service_in_html = meta.service_title in html
        commercial_ok = price_in_html and price_above_floor and service_in_html
        checks.append(QACheckItem(
            name="COMMERCIAL_ALIGNMENT",
            passed=commercial_ok,
            details=f"Service '{meta.service_title}' and Price ${meta.price_usd:,.2f} (>= $500 floor) present in demo."
        ))

        # 4. ZERO_PLACEHOLDERS Gate (also enforces no internal data leakage)
        placeholder_patterns = [
            r"\{\{", r"\}\}", r"TODO", r"lorem ipsum", r"undefined", r"\[Business Name\]",
            r"[a-zA-Z]:\\(?:Users|opt|AGENCY)[^<>\s]*", r"/opt/agency/[^<>\s]*",
            r"\b(OUTREACH_READY|PENDING_APPROVAL|QUALIFIED_REPLY)\b"
        ]
        found_placeholders = []
        for pat in placeholder_patterns:
            if re.search(pat, html, re.I):
                found_placeholders.append(pat)
        no_placeholders = len(found_placeholders) == 0
        checks.append(QACheckItem(
            name="ZERO_PLACEHOLDERS",
            passed=no_placeholders,
            details="No unpopulated placeholders or internal leaks detected." if no_placeholders else f"Found placeholders/leaks: {found_placeholders}"
        ))

        # 5. STRUCTURAL_HTML Gate
        has_doctype = "<!DOCTYPE html>" in html or "<!doctype html>" in html
        has_html_tags = "<html" in html and "</html>" in html
        has_body_tags = "<body" in html and "</body>" in html
        structure_ok = has_doctype and has_html_tags and has_body_tags
        checks.append(QACheckItem(
            name="STRUCTURAL_VALIDITY",
            passed=structure_ok,
            details="Valid HTML5 document structure with DOCTYPE, html, and body tags."
        ))

        # 6. REQUIREMENTS_COVERAGE Gate
        all_reqs_in_html = all(r.id in html for r in packet.requirements)
        checks.append(QACheckItem(
            name="REQUIREMENTS_COVERAGE",
            passed=all_reqs_in_html,
            details=f"All {len(packet.requirements)} requirement item IDs are explicitly rendered in table."
        ))

        # 7. DETERMINISM Gate
        checksum_valid = len(meta.build_checksum) == 64
        checks.append(QACheckItem(
            name="DETERMINISTIC_CHECKSUM",
            passed=checksum_valid,
            details=f"Valid SHA-256 build checksum: {meta.build_checksum[:16]}..."
        ))

        passed_count = sum(1 for c in checks if c.passed)
        failed_count = len(checks) - passed_count
        overall = failed_count == 0

        errors = None
        if not overall:
            errors = "; ".join(c.details for c in checks if not c.passed)

        logger.info(f"[DemoQA] QA Result for {meta.demo_id}: {'PASS' if overall else 'FAIL'} ({passed_count}/{len(checks)} passed).")

        return DemoQAResult(
            demo_id=demo_result.demo_id,
            overall_passed=overall,
            total_checks=len(checks),
            passed_checks=passed_count,
            failed_checks=failed_count,
            checks=checks,
            qa_signature=f"QA-PASS-{meta.build_checksum[:12]}" if overall else "QA-FAIL",
            error_summary=errors
        )

    @classmethod
    def verify_zero_internal_leakage(cls, html: str) -> Dict[str, Any]:
        """
        Independent verification asserting zero operational data leakage:
        - No server filesystem paths
        - No internal database pipeline stages
        - No internal database primary keys
        - No live credentials or API tokens
        """
        leak_patterns = [
            (r"[a-zA-Z]:\\(?:Users|opt|AGENCY)[^<>\s]*", "Absolute server path (Windows)"),
            (r"/opt/agency/[^<>\s]*", "Absolute server path (Linux)"),
            (r"\b(OUTREACH_READY|PENDING_APPROVAL|QUALIFIED_REPLY|IN_DELIVERY|ADVANCE_PAID)\b", "Internal pipeline stage"),
            (r"business_id:\s*\d+", "Internal database foreign key"),
            (r"sk-live-[a-zA-Z0-9]+", "API secret key")
        ]
        leaks = []
        for pat, desc in leak_patterns:
            matches = re.findall(pat, html)
            if matches:
                leaks.append(f"{desc}: {matches[:3]}")
        return {
            "passed": len(leaks) == 0,
            "leak_count": len(leaks),
            "leaks": leaks
        }


demo_qa_engine = DemoQAEngine()
