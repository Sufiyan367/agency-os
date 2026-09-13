"""
Code Intelligence Layer for Agency OS.
Provides structured codebase context, caller/callee analysis, blast radius calculation,
and provider benchmarking for autonomous diagnostics and self-healing operations.
"""
from app.code_intelligence.base import (
    BaseCodeIntelligenceProvider, CodebaseContext, SymbolReference,
    CallGraphNode, BlastRadiusReport, HistoricalFix
)
from app.code_intelligence.native_analyzer import NativeRepositoryAnalyzer
from app.code_intelligence.graft_provider import GraftProvider
from app.code_intelligence.codebase_memory_provider import CodebaseMemoryProvider
from app.code_intelligence.benchmarks import code_intelligence_benchmarker, ProviderBenchmarkResult

__all__ = [
    "BaseCodeIntelligenceProvider",
    "CodebaseContext",
    "SymbolReference",
    "CallGraphNode",
    "BlastRadiusReport",
    "HistoricalFix",
    "NativeRepositoryAnalyzer",
    "GraftProvider",
    "CodebaseMemoryProvider",
    "code_intelligence_benchmarker",
    "ProviderBenchmarkResult",
]
