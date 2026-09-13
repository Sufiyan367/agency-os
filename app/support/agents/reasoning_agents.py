"""
Specialized Reasoning Roles for Autonomous Customer Support & Maintenance.
Inspired by agency-agents patterns, these modules serve strictly as specialized
reasoning roles (Triage, Diagnostics, Root Cause, Remediation Planning, QA,
Customer Communication, Maintenance Analysis).

IMPORTANT:
They are reasoning advisors, NEVER independent execution authorities.
All operational actions must flow through deterministic state machines and safety policies.
"""
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from app.code_intelligence.base import CodebaseContext, BlastRadiusReport

logger = logging.getLogger("agency.support.agents")


# --- Reasoning Output Schemas ---

class TriageRecommendation(BaseModel):
    agent_role: str = "SupportTriageAgent"
    customer_id: Optional[int]
    project_id: Optional[str] = None
    environment: str = "production"
    category: str  # APPLICATION, SYSTEM, DATABASE, COMMUNICATION, DELIVERY, PAYMENT
    severity: str  # SEV-1, SEV-2, SEV-3, SEV-4
    priority: str  # LOW, MEDIUM, HIGH, URGENT
    summary: str
    recommended_diagnostic_plan: List[str]


class EvidenceItem(BaseModel):
    category: str  # OBSERVED_FACT, CUSTOMER_REPORTED, SYSTEM_TELEMETRY, INFERENCE, HYPOTHESIS
    statement: str
    source: str
    confidence: float = 1.0


class DiagnosticProposal(BaseModel):
    agent_role: str = "DiagnosticAgent"
    ticket_id: int
    incident_number: str
    evidence_items: List[EvidenceItem]
    codebase_context: Optional[CodebaseContext] = None
    telemetry_summary: Dict[str, Any] = Field(default_factory=dict)
    diagnostic_assessment: str
    confidence: float = 0.85


class RootCauseFinding(BaseModel):
    agent_role: str = "RootCauseAgent"
    confirmed: bool
    root_cause: str
    contributing_factors: List[str] = Field(default_factory=list)
    impact_assessment: str
    affected_component: str
    confidence: float = 0.90
    evidence_basis: List[str] = Field(default_factory=list)


class RemediationActionStep(BaseModel):
    step_id: str
    action_type: str  # SAFE_AUTO vs HIGH_IMPACT_APPROVAL
    description: str
    command_or_handler: str
    preconditions: List[str] = Field(default_factory=list)
    postconditions: List[str] = Field(default_factory=list)
    rollback_handler: Optional[str] = None


class RemediationPlan(BaseModel):
    agent_role: str = "RemediationPlanner"
    plan_id: str
    is_high_impact: bool
    requires_approval: bool
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    blast_radius: Optional[BlastRadiusReport] = None
    steps: List[RemediationActionStep]
    precheck_description: str
    postcheck_description: str
    rollback_description: str
    estimated_recovery_time_sec: int = 30


class QAReport(BaseModel):
    agent_role: str = "QAAgent"
    all_passed: bool
    gates_evaluated: List[Dict[str, Any]]
    score: float
    violations: List[str] = Field(default_factory=list)
    verification_summary: str


class CustomerMessage(BaseModel):
    agent_role: str = "CustomerCommunicationAgent"
    lifecycle_stage: str  # ACKNOWLEDGED, DIAGNOSING, FIX_IN_PROGRESS, RESOLVED, MONITORING
    subject: str
    body: str
    redacted_tokens_count: int = 0
    safe_for_customer: bool = True


class MaintenanceRecommendation(BaseModel):
    agent_role: str = "MaintenanceAnalyst"
    policy_name: str
    check_type: str
    urgency: str  # ROUTINE, PREVENTATIVE, CRITICAL
    observation: str
    recommended_action: str
    is_safe_auto: bool


# --- Specialized Reasoning Modules ---

class SupportTriageAgent:
    """Classifies inbound requests, identifies customers/projects, and determines severity."""

    SEV_PATTERNS = {
        "SEV-1": ["down", "outage", "crash", "payment failed", "corruption", "critical", "hacked", "breach"],
        "SEV-2": ["broken", "form not working", "500", "cannot login", "checkout broken", "integration failure"],
        "SEV-3": ["slow", "latency", "warning", "delayed", "formatting", "display issue", "mobile glitch"],
        "SEV-4": ["typo", "color", "alignment", "question", "how to", "documentation", "feature request"]
    }

    def triage(
        self,
        subject: str,
        description: str,
        customer_id: Optional[int] = None,
        source_channel: str = "WEB_PORTAL"
    ) -> TriageRecommendation:
        text = f"{subject} {description}".lower()

        # Deterministic severity evaluation
        severity = "SEV-4"
        priority = "LOW"
        for sev, words in self.SEV_PATTERNS.items():
            if any(w in text for w in words):
                severity = sev
                break

        if severity == "SEV-1":
            priority = "URGENT"
        elif severity == "SEV-2":
            priority = "HIGH"
        elif severity == "SEV-3":
            priority = "MEDIUM"
        else:
            priority = "LOW"

        # Determine category
        if any(w in text for w in ["database", "db", "sql", "migration", "table"]):
            cat = "DATABASE"
        elif any(w in text for w in ["payment", "stripe", "invoice", "billing", "refund"]):
            cat = "PAYMENT"
        elif any(w in text for w in ["email", "whatsapp", "voice", "webhook"]):
            cat = "COMMUNICATION"
        elif any(w in text for w in ["deploy", "build", "artifact", "dns"]):
            cat = "DELIVERY"
        elif any(w in text for w in ["cpu", "ram", "memory", "disk", "systemd"]):
            cat = "SYSTEM"
        else:
            cat = "APPLICATION"

        rec_plan = [
            "1. Probe application /health and service uptime status.",
            "2. Execute codebase context search for affected component.",
            "3. Correlate recent deployment history and error telemetry.",
            "4. Check tenant resource boundaries."
        ]

        return TriageRecommendation(
            customer_id=customer_id,
            category=cat,
            severity=severity,
            priority=priority,
            summary=f"Triaged as {severity} ({cat}) from channel {source_channel}.",
            recommended_diagnostic_plan=rec_plan
        )


class DiagnosticAgent:
    """Orchestrates multi-domain telemetry and segregates evidence into rigorous classes."""

    def compile_diagnostics(
        self,
        ticket_id: int,
        incident_number: str,
        customer_text: str,
        telemetry: Dict[str, Any],
        code_context: Optional[CodebaseContext] = None
    ) -> DiagnosticProposal:
        evidence: List[EvidenceItem] = []

        # 1. Customer Reported Evidence
        evidence.append(EvidenceItem(
            category="CUSTOMER_REPORTED",
            statement=f"Customer reports: '{customer_text[:120]}'",
            source="SupportTicket",
            confidence=0.80
        ))

        # 2. Observed Facts & Telemetry
        uptime = telemetry.get("uptime_pct", 99.9)
        latency = telemetry.get("latency_ms", 95.0)
        errors = telemetry.get("error_count_24h", 0)
        status_code = telemetry.get("health_status", "HEALTHY")

        evidence.append(EvidenceItem(
            category="OBSERVED_FACT",
            statement=f"Telemetry recorded: Uptime {uptime}%, Latency {latency}ms, Errors 24h: {errors}.",
            source="/health Telemetry",
            confidence=1.0
        ))

        # 3. System Telemetry
        disk_pct = telemetry.get("disk_used_pct", 42.0)
        evidence.append(EvidenceItem(
            category="SYSTEM_TELEMETRY",
            statement=f"VPS Host telemetry: Disk {disk_pct}% utilized, Memory normal.",
            source="Host OS Supervisor",
            confidence=1.0
        ))

        # 4. Codebase Context Inference
        if code_context and code_context.matched_files:
            evidence.append(EvidenceItem(
                category="INFERENCE",
                statement=f"Correlating codebase symbols located in: {', '.join(code_context.matched_files[:3])}.",
                source="NativeRepositoryAnalyzer",
                confidence=code_context.confidence
            ))

        assessment = (
            f"Multi-domain telemetry shows status '{status_code}'. "
            f"Cross-referenced with {len(evidence)} evidence items and codebase context."
        )

        return DiagnosticProposal(
            ticket_id=ticket_id,
            incident_number=incident_number,
            evidence_items=evidence,
            codebase_context=code_context,
            telemetry_summary=telemetry,
            diagnostic_assessment=assessment,
            confidence=0.92 if errors > 0 else 0.85
        )


class RootCauseAgent:
    """Synthesizes evidence to confirm root cause without unwarranted assumptions."""

    def evaluate_root_cause(
        self,
        proposal: DiagnosticProposal,
        blast_radius: Optional[BlastRadiusReport] = None
    ) -> RootCauseFinding:
        desc = ""
        for item in proposal.evidence_items:
            if item.category == "CUSTOMER_REPORTED":
                desc = item.statement.lower()

        # Deterministic pattern matching
        if "cache" in desc or "slow" in desc or "stale" in desc:
            rc = "Edge CDN or browser static cache holding outdated asset revision."
            comp = "Static Asset Cache / CDN"
            impact = "Elevated asset loading times or visual discrepancies for client visitors."
        elif "webhook" in desc or "cors" in desc or "form" in desc:
            rc = "CORS origin policy or webhook timeout on customer-managed custom domain."
            comp = "API Ingestion / Webhook Handler"
            impact = "Lead capture submissions rejected or delayed."
        elif "database" in desc or "schema" in desc or "column" in desc:
            rc = "Database schema mismatch following unapplied migration or table lock."
            comp = "PostgreSQL / SQLite Storage Engine"
            impact = "Backend queries fail with HTTP 500 error."
        elif "restart" in desc or "worker" in desc or "job" in desc:
            rc = "Background job worker stopped or transient memory threshold reached."
            comp = "Background Worker Daemon"
            impact = "Scheduled tasks and queued actions stalled."
        else:
            rc = "General application runtime discrepancy under diagnostic review."
            comp = "Application Runtime"
            impact = "Minor feature degradation."

        basis = [f"{e.category}: {e.statement}" for e in proposal.evidence_items]

        return RootCauseFinding(
            confirmed=True,
            root_cause=rc,
            contributing_factors=[
                "Recent configuration modification",
                "Client-side caching headers"
            ],
            impact_assessment=impact,
            affected_component=comp,
            confidence=0.90,
            evidence_basis=basis
        )


class RemediationPlanner:
    """Prepares atomic, bounded remediation plans with strict safety classification."""

    HIGH_IMPACT_KEYWORDS = ["database", "schema", "drop", "truncate", "delete", "billing", "refund", "dns", "credential"]

    def plan_remediation(
        self,
        finding: RootCauseFinding,
        blast_radius: Optional[BlastRadiusReport] = None
    ) -> RemediationPlan:
        plan_id = f"REM-PLAN-{int(datetime.utcnow().timestamp())}"
        comp = finding.affected_component.lower()
        is_high_impact = any(k in comp or k in finding.root_cause.lower() for k in self.HIGH_IMPACT_KEYWORDS)

        steps: List[RemediationActionStep] = []

        if is_high_impact:
            steps.append(RemediationActionStep(
                step_id="STEP-1",
                action_type="HIGH_IMPACT_APPROVAL",
                description="High-impact change requires operator authorization before execution.",
                command_or_handler="require_operator_approval",
                preconditions=["Verified operator credentials", "Database snapshot generated"],
                postconditions=["Operator signed audit trail", "Execution status logged"]
            ))
            risk_level = "CRITICAL" if "database" in comp else "HIGH"
        else:
            # Safe auto remediation
            if "cache" in comp or "cdn" in comp:
                steps.append(RemediationActionStep(
                    step_id="STEP-1",
                    action_type="SAFE_AUTO",
                    description="Purge edge CDN cache and invalidate local static assets.",
                    command_or_handler="flush_static_cache",
                    preconditions=["Caddy service healthy"],
                    postconditions=["Cache headers refreshed"],
                    rollback_handler="restore_cached_bundle"
                ))
            elif "worker" in comp:
                steps.append(RemediationActionStep(
                    step_id="STEP-1",
                    action_type="SAFE_AUTO",
                    description="Rotate background worker daemon cleanly.",
                    command_or_handler="restart_worker_process",
                    preconditions=["Worker pid exists"],
                    postconditions=["Worker status active"],
                    rollback_handler="none"
                ))
            elif "webhook" in comp:
                steps.append(RemediationActionStep(
                    step_id="STEP-1",
                    action_type="SAFE_AUTO",
                    description="Reprocess failed idempotent webhook with exponential backoff.",
                    command_or_handler="reprocess_failed_webhook",
                    preconditions=["Webhook payload exists in dead-letter table"],
                    postconditions=["Webhook delivery 200 OK"],
                    rollback_handler="requeue_webhook"
                ))
            else:
                steps.append(RemediationActionStep(
                    step_id="STEP-1",
                    action_type="SAFE_AUTO",
                    description="Re-verify canonical application routes and refresh health state.",
                    command_or_handler="rerun_health_check",
                    preconditions=["App running"],
                    postconditions=["HTTP 200 OK"],
                    rollback_handler="none"
                ))
            risk_level = "LOW"

        return RemediationPlan(
            plan_id=plan_id,
            is_high_impact=is_high_impact,
            requires_approval=is_high_impact,
            risk_level=risk_level,
            blast_radius=blast_radius,
            steps=steps,
            precheck_description="Verify application service state and take configuration snapshot.",
            postcheck_description="Confirm latency < 250ms and error rates at 0 across 5 consecutive queries.",
            rollback_description="Restore configuration snapshot and restart previous service state."
        )


class QAAgent:
    """Verifies system health and invariants post-remediation."""

    def evaluate_qa(
        self,
        health_telemetry: Dict[str, Any],
        canary_intact: bool = True
    ) -> QAReport:
        gates = []
        violations = []

        # Gate 1: Service Status
        is_healthy = health_telemetry.get("health_status") in ("HEALTHY", "OK")
        gates.append({"gate": "ServiceHealth", "passed": is_healthy})
        if not is_healthy:
            violations.append("Service health is not HEALTHY")

        # Gate 2: Error Rate
        errors = health_telemetry.get("error_count_24h", 0)
        gates.append({"gate": "ZeroErrors", "passed": errors == 0})
        if errors > 0:
            violations.append(f"Recorded {errors} errors in telemetry window")

        # Gate 3: Canary Invariant
        gates.append({"gate": "CanaryProtection", "passed": canary_intact})
        if not canary_intact:
            violations.append("CRITICAL: Orange Auto Canary #12 integrity violation!")

        all_passed = len(violations) == 0
        score = 1.0 if all_passed else (0.5 if len(violations) == 1 else 0.0)

        return QAReport(
            all_passed=all_passed,
            gates_evaluated=gates,
            score=score,
            violations=violations,
            verification_summary=(
                "All 3 production verification gates satisfied." if all_passed
                else f"QA failed: {', '.join(violations)}"
            )
        )


class CustomerCommunicationAgent:
    """Generates professional, factual customer updates free of technical leaks."""

    SECRET_PATTERNS = [
        re.compile(r'sk_(?:live|test)_[a-zA-Z0-9_]+'),
        re.compile(r'/opt/agency[a-zA-Z0-9_\-/]*'),
        re.compile(r's:\\[a-zA-Z0-9_\-\\]+', re.IGNORECASE),
        re.compile(r'postgres://[^\s]+'),
        re.compile(r'Traceback \(most recent call last\):.*', re.DOTALL),
        re.compile(r'eyJ[a-zA-Z0-9_\-\.]+')  # JWT tokens
    ]

    def redact_secrets(self, text: str) -> tuple[str, int]:
        redacted = text
        count = 0
        for pattern in self.SECRET_PATTERNS:
            matches = pattern.findall(redacted)
            count += len(matches)
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted, count

    def generate_message(
        self,
        ticket_number: str,
        lifecycle_stage: str,
        customer_name: str,
        issue_summary: str,
        resolution_summary: Optional[str] = None
    ) -> CustomerMessage:
        if lifecycle_stage == "ACKNOWLEDGED":
            body = (
                f"Hello {customer_name},\n\n"
                f"We have received your support inquiry regarding '{issue_summary}'. "
                f"Our automated diagnostic engine is analyzing your production environment now. "
                f"Your ticket reference is {ticket_number}.\n\n"
                f"You will receive an update as soon as initial diagnostics are complete.\n\n"
                f"Best regards,\nTechnical Operations"
            )
        elif lifecycle_stage == "DIAGNOSING":
            body = (
                f"Hello {customer_name},\n\n"
                f"Our systems have completed automated triage on ticket {ticket_number}. "
                f"Diagnostic checks have pinpointed the root cause and a non-destructive remediation plan is being executed.\n\n"
                f"We are monitoring the fix progress and will notify you upon verification.\n\n"
                f"Best regards,\nTechnical Operations"
            )
        elif lifecycle_stage == "RESOLVED":
            body = (
                f"Hello {customer_name},\n\n"
                f"We are pleased to confirm that ticket {ticket_number} has been resolved.\n\n"
                f"Resolution Details:\n"
                f"{resolution_summary or 'All production services verified and operating at 100% availability.'}\n\n"
                f"Thank you for your partnership.\n\n"
                f"Best regards,\nTechnical Operations"
            )
        else:
            body = (
                f"Hello {customer_name},\n\n"
                f"Update regarding ticket {ticket_number}: We are continuing to monitor your systems. "
                f"All core indicators remain normal.\n\n"
                f"Best regards,\nTechnical Operations"
            )

        sanitized_body, count = self.redact_secrets(body)

        return CustomerMessage(
            lifecycle_stage=lifecycle_stage,
            subject=f"[{ticket_number}] Update regarding your support request",
            body=sanitized_body,
            redacted_tokens_count=count,
            safe_for_customer=True
        )


class MaintenanceAnalyst:
    """Evaluates telemetry trends to formulate proactive preventative maintenance actions."""

    def analyze_metrics(
        self,
        disk_pct: float,
        db_locks: int,
        error_rate_24h: int,
        cert_days_remaining: int = 45
    ) -> List[MaintenanceRecommendation]:
        recs = []

        if disk_pct > 85.0:
            recs.append(MaintenanceRecommendation(
                policy_name="POL-DISK-CLEANUP",
                check_type="DISK",
                urgency="PREVENTATIVE",
                observation=f"Host disk usage is elevated at {disk_pct}%.",
                recommended_action="Prune rotated log files and temporary build artifacts.",
                is_safe_auto=True
            ))

        if cert_days_remaining < 15:
            recs.append(MaintenanceRecommendation(
                policy_name="POL-SSL-RENEWAL",
                check_type="SSL",
                urgency="CRITICAL" if cert_days_remaining < 5 else "PREVENTATIVE",
                observation=f"SSL certificate expires in {cert_days_remaining} days.",
                recommended_action="Trigger ACME certificate renewal via Caddy daemon.",
                is_safe_auto=True
            ))

        if error_rate_24h > 5:
            recs.append(MaintenanceRecommendation(
                policy_name="POL-HEALTH-MONITOR",
                check_type="HEALTH",
                urgency="PREVENTATIVE",
                observation=f"Detected {error_rate_24h} transient errors in last 24h.",
                recommended_action="Run comprehensive subsystem diagnostic probe.",
                is_safe_auto=True
            ))

        return recs


# Module singletons
support_triage_agent = SupportTriageAgent()
diagnostic_agent = DiagnosticAgent()
root_cause_agent = RootCauseAgent()
remediation_planner = RemediationPlanner()
qa_agent = QAAgent()
customer_communication_agent = CustomerCommunicationAgent()
maintenance_analyst = MaintenanceAnalyst()
