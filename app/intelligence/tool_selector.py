"""
Agency OS — Demo Factory Intelligence & Tool Selector.
Evaluates requirement specifications and allocates tools (Stitch, Gemini, Antigravity, Firebase)
with bounded repair constraints and sandbox verification policies.
"""

from typing import Dict, Any, List, Optional
import uuid

from app.builder.models import CanonicalSpec


class ToolType:
    STITCH = "STITCH_DESIGN_PROVIDER"
    GEMINI = "GOOGLE_AI_STUDIO_PROVIDER"
    ANTIGRAVITY = "ANTIGRAVITY_CODING_PROVIDER"
    FIREBASE = "FIREBASE_PROVIDER"


class DemoPlan:
    """
    Requirement-grounded execution plan for Demo Factory generation.
    """
    def __init__(
        self,
        plan_id: str,
        project_id: str,
        customer_slug: str,
        tool_allocations: Dict[str, List[str]],
        tool_rationales: Dict[str, str],
        qa_expectations: List[str],
        sandbox_strategy: str = "ISOLATED_LOCAL_SANDBOX",
        bounded_repair_limit: int = 3,
        ceo_gate_escalation_rule: str = "Escalate to CEO_REQUIRED if overall status == FAIL after 3 attempts"
    ):
        self.plan_id = plan_id
        self.project_id = project_id
        self.customer_slug = customer_slug
        self.tool_allocations = tool_allocations
        self.tool_rationales = tool_rationales
        self.qa_expectations = qa_expectations
        self.sandbox_strategy = sandbox_strategy
        self.bounded_repair_limit = bounded_repair_limit
        self.ceo_gate_escalation_rule = ceo_gate_escalation_rule

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "customer_slug": self.customer_slug,
            "tool_allocations": self.tool_allocations,
            "tool_rationales": self.tool_rationales,
            "qa_expectations": self.qa_expectations,
            "sandbox_strategy": self.sandbox_strategy,
            "bounded_repair_limit": self.bounded_repair_limit,
            "ceo_gate_escalation_rule": self.ceo_gate_escalation_rule
        }


class DemoToolSelector:
    """
    Intelligently maps project requirements to optimal Demo Factory tools.
    """

    @classmethod
    def generate_demo_plan(
        cls,
        spec: CanonicalSpec
    ) -> DemoPlan:
        """
        Synthesizes a concrete Demo Plan from CanonicalSpec.
        """
        tool_allocations: Dict[str, List[str]] = {
            ToolType.STITCH: [],
            ToolType.GEMINI: [],
            ToolType.ANTIGRAVITY: [],
            ToolType.FIREBASE: []
        }
        tool_rationales: Dict[str, str] = {}

        # 1. Evaluate screens for Stitch Design
        screens = spec.required_pages or []
        for screen in screens:
            route = screen.get("route", "/")
            tool_allocations[ToolType.STITCH].append(route)
        tool_rationales[ToolType.STITCH] = "Stitch generates responsive screen layout hierarchy and design tokens."

        # 2. Evaluate AI Features for Google AI Studio (Gemini)
        ai_features = spec.required_features or []
        has_ai = False
        for feat in ai_features:
            feat_id = feat.get("feature_id", "")
            tool_allocations[ToolType.GEMINI].append(feat_id)
            has_ai = True
        if not has_ai:
            # Default intake AI logic
            tool_allocations[ToolType.GEMINI].append("intake_assistant")
        tool_rationales[ToolType.GEMINI] = "Google Gemini generates structured reasoning, prompt templates, and intake logic."

        # 3. Antigravity Coding Engine for full-stack code synthesis
        tool_allocations[ToolType.ANTIGRAVITY].extend([
            "fastapi_backend_routes",
            "html_vanilla_css_templates",
            "client_side_stepper_logic"
        ])
        tool_rationales[ToolType.ANTIGRAVITY] = "Antigravity Multi-Language Coding Provider compiles robust routes and zero-dependency UI."

        # 4. Check if Firebase is required (auth, real-time sync)
        integrations = [i.lower() for i in (spec.integrations or [])]
        if any("firebase" in i or "auth" in i for i in integrations):
            tool_allocations[ToolType.FIREBASE].append("authentication_and_storage")
            tool_rationales[ToolType.FIREBASE] = "Firebase provisions authentication and real-time state storage."

        plan_id = f"plan_{uuid.uuid4().hex[:8]}"

        qa_expectations = [
            "20 QA gates evaluated",
            "Zero placeholder leakage in client-facing components",
            "All routes return HTTP 200",
            "Sub-second load paint on mobile viewports",
            "Deterministic fallback on AI endpoint timeout"
        ]

        return DemoPlan(
            plan_id=plan_id,
            project_id=spec.project_id,
            customer_slug=spec.customer_slug,
            tool_allocations=tool_allocations,
            tool_rationales=tool_rationales,
            qa_expectations=qa_expectations,
            sandbox_strategy="ISOLATED_LOCAL_SANDBOX",
            bounded_repair_limit=3,
            ceo_gate_escalation_rule="Escalate to CEO_REQUIRED if overall status == FAIL after 3 attempts"
        )


demo_tool_selector = DemoToolSelector()
