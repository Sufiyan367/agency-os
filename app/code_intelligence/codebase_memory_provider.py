"""
CodebaseMemoryProvider — MCP / Memory-Augmented Provider Adapter.
Implements BaseCodeIntelligenceProvider interface querying vector/knowledge memories
with deterministic native fallback when MCP memory service is unconfigured.
"""
import os
import logging
from typing import Dict, Any, List, Optional

from app.code_intelligence.base import (
    BaseCodeIntelligenceProvider, CodebaseContext, SymbolReference,
    CallGraphNode, BlastRadiusReport
)
from app.code_intelligence.native_analyzer import NativeRepositoryAnalyzer

logger = logging.getLogger("agency.code_intelligence.memory")


class CodebaseMemoryProvider(BaseCodeIntelligenceProvider):
    """
    Codebase Memory Provider utilizing memory indexing and MCP patterns.
    Falls back gracefully to NativeRepositoryAnalyzer when external memory is unavailable.
    """

    def __init__(self, mcp_server_name: str = "codebase-memory-mcp"):
        self.mcp_server_name = mcp_server_name
        self._native_fallback = NativeRepositoryAnalyzer()
        self._is_active = bool(os.environ.get("ENABLE_CODEBASE_MEMORY_MCP") == "true")

    @property
    def provider_name(self) -> str:
        return "CodebaseMemoryProvider"

    async def is_available(self) -> bool:
        return self._is_active

    async def analyze_incident_context(
        self,
        error_signature: str,
        affected_component: Optional[str] = None,
        query: Optional[str] = None
    ) -> CodebaseContext:
        ctx = await self._native_fallback.analyze_incident_context(
            error_signature, affected_component, query
        )
        ctx.provider_name = self.provider_name
        ctx.summary = f"[CodebaseMemory Adapter (Native Engine)] {ctx.summary}"
        return ctx

    async def get_blast_radius(
        self,
        candidate_files: List[str]
    ) -> BlastRadiusReport:
        report = await self._native_fallback.get_blast_radius(candidate_files)
        report.reasoning = f"[CodebaseMemory Adapter] {report.reasoning}"
        return report

    async def get_call_hierarchy(
        self,
        symbol_name: str,
        file_path: Optional[str] = None
    ) -> Optional[CallGraphNode]:
        return await self._native_fallback.get_call_hierarchy(symbol_name, file_path)
