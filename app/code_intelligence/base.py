"""
Code Intelligence & Codebase Context Layer — Base Interface.
Defines standardized interfaces and schemas for codebase structure analysis,
call-graph inspection, blast radius estimation, and historical fix retrieval.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class SymbolReference(BaseModel):
    name: str
    kind: str  # function, class, method, route, variable
    file_path: str
    line_number: int
    docstring: Optional[str] = None


class CallGraphNode(BaseModel):
    symbol: str
    file_path: str
    callers: List[str] = Field(default_factory=list)
    callees: List[str] = Field(default_factory=list)


class BlastRadiusReport(BaseModel):
    modified_files: List[str]
    directly_affected_files: List[str] = Field(default_factory=list)
    indirectly_affected_routes: List[str] = Field(default_factory=list)
    affected_services: List[str] = Field(default_factory=list)
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    regression_risk_score: float = 0.0  # 0.0 to 1.0
    reasoning: str = ""


class CodebaseContext(BaseModel):
    query: str
    matched_files: List[str] = Field(default_factory=list)
    relevant_symbols: List[SymbolReference] = Field(default_factory=list)
    related_routes: List[str] = Field(default_factory=list)
    configuration_dependencies: List[str] = Field(default_factory=list)
    provider_name: str = "NativeRepositoryAnalyzer"
    confidence: float = 0.85
    summary: str = ""


class HistoricalFix(BaseModel):
    signature: str
    description: str
    affected_component: str
    fix_applied: str
    verified: bool = True
    occurrence_count: int = 1


class BaseCodeIntelligenceProvider(ABC):
    """
    Abstract contract for codebase context extraction and blast radius analysis.
    Implementations MUST be read-only and never mutate files or authorize changes directly.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the code intelligence provider."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider backend/runtime is operational."""
        pass

    @abstractmethod
    async def analyze_incident_context(
        self,
        error_signature: str,
        affected_component: Optional[str] = None,
        query: Optional[str] = None
    ) -> CodebaseContext:
        """Extract structured codebase context relevant to an incident or error signature."""
        pass

    @abstractmethod
    async def get_blast_radius(
        self,
        candidate_files: List[str]
    ) -> BlastRadiusReport:
        """Evaluate the potential blast radius and regression risk of modifying candidate files."""
        pass

    @abstractmethod
    async def get_call_hierarchy(
        self,
        symbol_name: str,
        file_path: Optional[str] = None
    ) -> Optional[CallGraphNode]:
        """Locate callers and callees for a specified symbol."""
        pass
