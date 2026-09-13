"""
Base Provider Interfaces for Autonomous Demo & Build Pipeline.
Defines abstract contracts for Design, AI Prototyping, Coding/Build, and Infrastructure.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from app.database.models import ProjectSpecification, CustomerProject, ProjectBuild
from app.builder.models import (
    DesignResult, AIPrototypeResult, BuildResult, RepairResult, DeploymentResult
)


class BaseDesignProvider(ABC):
    """Abstract provider for UI/UX visual design system and screen wireframes."""

    @abstractmethod
    async def generate_design(
        self,
        spec: ProjectSpecification,
        customer_project: CustomerProject
    ) -> DesignResult:
        """Generates design system tokens, responsive layouts, and screen definitions."""
        pass


class BaseAIProvider(ABC):
    """Abstract provider for AI feature prototyping, system instructions, and interactive mocks."""

    @abstractmethod
    async def generate_prototype(
        self,
        spec: ProjectSpecification,
        customer_project: CustomerProject
    ) -> AIPrototypeResult:
        """Configures AI models, system instructions, prompt templates, and conversational hooks."""
        pass


class BaseCodingProvider(ABC):
    """Abstract provider for multi-language code generation, assembly, and automated repair."""

    @abstractmethod
    async def build_project(
        self,
        spec: ProjectSpecification,
        design: DesignResult,
        ai_proto: AIPrototypeResult,
        customer_project: CustomerProject
    ) -> BuildResult:
        """Assembles project codebase, generates clean production-grade code artifacts, and compiles manifests."""
        pass

    @abstractmethod
    async def repair_build(
        self,
        spec: ProjectSpecification,
        build: ProjectBuild,
        failing_gate: str,
        failure_classification: str,
        critical_violations: List[str],
        attempt_number: int
    ) -> RepairResult:
        """Applies targeted patch to resolve QA failures without breaking existing passing gates."""
        pass


class BaseInfrastructureProvider(ABC):
    """Abstract provider for isolated sandbox deployment, preview URLs, and hosting."""

    @abstractmethod
    async def provision_and_deploy(
        self,
        build: ProjectBuild,
        customer_project: CustomerProject
    ) -> DeploymentResult:
        """Deploys build artifacts to isolated sandbox environment and returns verified live demo URL."""
        pass
