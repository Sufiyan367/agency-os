"""
Builder Data Models — Pydantic Schemas for Canonical Specifications and Providers.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class RequirementFact(BaseModel):
    category: str
    description: str
    source: str = "business_profile"

class CustomerRequestItem(BaseModel):
    request_text: str
    feature_type: str = "ui"
    priority: str = "high"

class AIInferenceItem(BaseModel):
    inferred_need: str
    recommended_solution: str
    confidence: float = 0.90

class CanonicalSpec(BaseModel):
    project_id: str
    customer_slug: str
    business_name: str
    domain: str
    industry: str
    version: int = 1
    architecture_style: str = "modular_monolith"
    primary_language: str = "typescript"
    framework: str = "react"
    backend_framework: str = "fastapi"
    styling_library: str = "tailwind"
    facts: List[RequirementFact] = Field(default_factory=list)
    customer_requests: List[CustomerRequestItem] = Field(default_factory=list)
    ai_inferences: List[AIInferenceItem] = Field(default_factory=list)
    required_screens: List[Dict[str, Any]] = Field(default_factory=list)
    ai_features: List[Dict[str, Any]] = Field(default_factory=list)
    checksum: str = ""

class ScreenDesign(BaseModel):
    screen_id: str
    title: str
    route: str
    description: str
    components: List[str] = Field(default_factory=list)

class DesignResult(BaseModel):
    provider: str
    status: str
    version: int = 1
    screens: List[ScreenDesign] = Field(default_factory=list)
    color_system: Dict[str, Any] = Field(default_factory=dict)
    typography: Dict[str, Any] = Field(default_factory=dict)
    responsive_variants: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AIPrototypeResult(BaseModel):
    provider: str
    status: str
    version: int = 1
    prototype_type: str
    prompt_templates: Dict[str, Any] = Field(default_factory=dict)
    system_instructions: str = ""
    safety_settings: Dict[str, Any] = Field(default_factory=dict)
    model_name: str = "gemini-2.5-flash"
    fallback_behavior: Dict[str, Any] = Field(default_factory=dict)
    interactive_hooks: Dict[str, Any] = Field(default_factory=dict)

class BuildArtifactItem(BaseModel):
    file_path: str
    file_type: str
    size_bytes: int
    sha256: str
    content: Optional[str] = None

class BuildResult(BaseModel):
    build_number: int
    status: str
    artifacts_manifest: Dict[str, Any] = Field(default_factory=dict)
    routes_manifest: List[str] = Field(default_factory=list)
    dependencies_manifest: Dict[str, Any] = Field(default_factory=dict)
    build_duration_ms: int = 0
    generated_files: List[BuildArtifactItem] = Field(default_factory=list)
    error: Optional[str] = None

class QAGateResult(BaseModel):
    gate_name: str
    passed: bool
    details: str
    critical: bool = True

class PipelineQAResult(BaseModel):
    build_id: int
    overall_status: str
    score: float
    gate_results: Dict[str, Any] = Field(default_factory=dict)
    critical_violations: List[str] = Field(default_factory=list)
    non_critical_warnings: List[str] = Field(default_factory=list)

class RepairResult(BaseModel):
    attempt_number: int
    failing_gate: str
    failure_classification: str
    diff_applied: str
    resolved: bool
    error: Optional[str] = None

class DeploymentResult(BaseModel):
    demo_id: str
    customer_slug: str
    deployment_url: str
    status: str
    artifacts_dir: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
