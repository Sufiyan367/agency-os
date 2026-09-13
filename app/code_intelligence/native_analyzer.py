"""
Native Repository Analyzer — Primary Deterministic Code Intelligence Provider.
Uses Python AST, regular expressions, and filesystem static analysis to inspect
code dependencies, route definitions, symbol locations, and regression risk
without requiring any external LLM or cloud API dependencies.
"""
import os
import ast
import re
import logging
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

from app.code_intelligence.base import (
    BaseCodeIntelligenceProvider, CodebaseContext, SymbolReference,
    CallGraphNode, BlastRadiusReport
)

logger = logging.getLogger("agency.code_intelligence.native")


class NativeRepositoryAnalyzer(BaseCodeIntelligenceProvider):
    """
    Deterministic static code analyzer for Agency OS repository.
    Inspects Python ASTs, FastAPI routing patterns, and configuration references.
    """

    def __init__(self, root_dir: Optional[str] = None):
        if root_dir:
            self.root_dir = Path(root_dir)
        else:
            # Default to repository root
            self.root_dir = Path(__file__).resolve().parent.parent.parent

    @property
    def provider_name(self) -> str:
        return "NativeRepositoryAnalyzer"

    async def is_available(self) -> bool:
        return self.root_dir.exists() and (self.root_dir / "app").exists()

    async def analyze_incident_context(
        self,
        error_signature: str,
        affected_component: Optional[str] = None,
        query: Optional[str] = None
    ) -> CodebaseContext:
        """
        Locate files, routes, and symbols correlating with an error signature or affected component.
        """
        search_terms = []
        if query:
            search_terms.append(query.lower())
        if affected_component:
            search_terms.append(affected_component.lower())
        if error_signature:
            # Extract key identifiers (camelCase, snake_case, URLs, or exception names)
            tokens = re.findall(r'[a-zA-Z0-9_\-\.]+', error_signature)
            for t in tokens:
                if len(t) > 3 and t.lower() not in {"error", "failed", "http", "none", "true", "false"}:
                    search_terms.append(t.lower())

        matched_files: Set[str] = set()
        relevant_symbols: List[SymbolReference] = []
        related_routes: List[str] = []
        config_deps: Set[str] = set()

        app_dir = self.root_dir / "app"
        if not app_dir.exists():
            return CodebaseContext(
                query=error_signature,
                provider_name=self.provider_name,
                summary="App directory not found for native analysis"
            )

        # Walk through app directory
        for py_file in app_dir.rglob("*.py"):
            rel_path = str(py_file.relative_to(self.root_dir)).replace("\\", "/")
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            content_lower = content.lower()
            file_matched = False

            # Check if any search term hits this file
            for term in search_terms:
                if term in content_lower or term in rel_path.lower():
                    matched_files.add(rel_path)
                    file_matched = True
                    break

            if file_matched:
                # AST parse for symbols & routes
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        # Detect functions / async functions
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            doc = ast.get_docstring(node)
                            # Check decorators for FastAPI routes
                            for dec in node.decorator_list:
                                dec_str = ast.unparse(dec) if hasattr(ast, 'unparse') else ""
                                if "router." in dec_str or "app." in dec_str:
                                    related_routes.append(f"{dec_str} in {rel_path}:{node.lineno}")

                            # If function matches term, add to symbols
                            for term in search_terms:
                                if term in node.name.lower():
                                    relevant_symbols.append(SymbolReference(
                                        name=node.name,
                                        kind="function",
                                        file_path=rel_path,
                                        line_number=node.lineno,
                                        docstring=doc[:120] if doc else None
                                    ))
                                    break

                        elif isinstance(node, ast.ClassDef):
                            for term in search_terms:
                                if term in node.name.lower():
                                    relevant_symbols.append(SymbolReference(
                                        name=node.name,
                                        kind="class",
                                        file_path=rel_path,
                                        line_number=node.lineno,
                                        docstring=ast.get_docstring(node)[:120] if ast.get_docstring(node) else None
                                    ))
                                    break

                        # Detect settings / config references
                        elif isinstance(node, ast.Attribute):
                            attr_name = getattr(node, "attr", "")
                            val_id = getattr(node.value, "id", "") if isinstance(node.value, ast.Name) else ""
                            if val_id == "settings" and attr_name:
                                config_deps.add(f"settings.{attr_name}")

                except SyntaxError:
                    pass

        # Prioritize files explicitly matching affected_component or query
        def file_priority(f: str) -> int:
            score = 0
            if affected_component and (affected_component.lower() in f.lower() or Path(affected_component).stem.lower() in f.lower()):
                score += 10
            if query and query.lower() in f.lower():
                score += 5
            return score

        sorted_files = sorted(list(matched_files), key=lambda f: (-file_priority(f), f))

        summary = (
            f"Native AST analysis identified {len(matched_files)} files, "
            f"{len(relevant_symbols)} symbols, and {len(related_routes)} routes "
            f"associated with signature: {error_signature[:60]}"
        )

        return CodebaseContext(
            query=error_signature,
            matched_files=sorted_files[:25],
            relevant_symbols=relevant_symbols[:15],
            related_routes=sorted(list(set(related_routes)))[:10],
            configuration_dependencies=sorted(list(config_deps))[:10],
            provider_name=self.provider_name,
            confidence=0.92 if matched_files else 0.50,
            summary=summary
        )

    async def get_blast_radius(
        self,
        candidate_files: List[str]
    ) -> BlastRadiusReport:
        """
        Calculates direct and indirect downstream impacts for proposed changes.
        """
        normalized_candidates = {f.replace("\\", "/").strip() for f in candidate_files}
        directly_affected: Set[str] = set()
        affected_routes: Set[str] = set()
        affected_services: Set[str] = set()

        app_dir = self.root_dir / "app"
        if not app_dir.exists():
            return BlastRadiusReport(
                modified_files=candidate_files,
                risk_level="LOW",
                reasoning="Repository app directory not accessible"
            )

        # Build reverse import graph
        for py_file in app_dir.rglob("*.py"):
            rel_path = str(py_file.relative_to(self.root_dir)).replace("\\", "/")
            if rel_path in normalized_candidates:
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # Check if py_file imports any candidate
            for cand in normalized_candidates:
                # Convert path to module notation: app/database/models.py -> app.database.models
                mod_name = cand.replace(".py", "").replace("/", ".")
                base_name = Path(cand).stem

                if mod_name in content or f"import {base_name}" in content or f"from {mod_name}" in content:
                    directly_affected.add(rel_path)
                    if "router" in content or "@router." in content:
                        affected_routes.add(rel_path)
                    if "service" in rel_path:
                        affected_services.add(rel_path)

        # Determine risk level
        total_impact = len(directly_affected)
        contains_critical = any(
            "database" in f or "auth" in f or "payment" in f or "models.py" in f
            for f in normalized_candidates
        )

        if contains_critical or total_impact > 12:
            risk_level = "CRITICAL" if contains_critical and total_impact > 8 else "HIGH"
            regression_score = 0.85
            reasoning = f"Core subsystem modified ({', '.join(normalized_candidates)}) impacting {total_impact} downstream files."
        elif total_impact > 4:
            risk_level = "MEDIUM"
            regression_score = 0.50
            reasoning = f"Moderate blast radius impacting {total_impact} dependent files."
        else:
            risk_level = "LOW"
            regression_score = 0.20
            reasoning = f"Isolated change impacting {total_impact} dependent files."

        return BlastRadiusReport(
            modified_files=list(normalized_candidates),
            directly_affected_files=sorted(list(directly_affected))[:15],
            indirectly_affected_routes=sorted(list(affected_routes))[:10],
            affected_services=sorted(list(affected_services))[:10],
            risk_level=risk_level,
            regression_risk_score=regression_score,
            reasoning=reasoning
        )

    async def get_call_hierarchy(
        self,
        symbol_name: str,
        file_path: Optional[str] = None
    ) -> Optional[CallGraphNode]:
        """
        Scans AST to locate callers of a given symbol across the codebase.
        """
        app_dir = self.root_dir / "app"
        callers: Set[str] = set()
        callees: Set[str] = set()
        found_file = file_path or ""

        target_call_pattern = re.compile(r'\b' + re.escape(symbol_name) + r'\s*\(')

        for py_file in app_dir.rglob("*.py"):
            rel_path = str(py_file.relative_to(self.root_dir)).replace("\\", "/")
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if target_call_pattern.search(content):
                callers.add(rel_path)

            if not found_file and f"def {symbol_name}" in content:
                found_file = rel_path
                # Parse callees inside this function
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol_name:
                            for subnode in ast.walk(node):
                                if isinstance(subnode, ast.Call):
                                    if isinstance(subnode.func, ast.Name):
                                        callees.add(subnode.func.id)
                                    elif isinstance(subnode.func, ast.Attribute):
                                        callees.add(subnode.func.attr)
                except Exception:
                    pass

        return CallGraphNode(
            symbol=symbol_name,
            file_path=found_file or "unknown",
            callers=sorted(list(callers))[:10],
            callees=sorted(list(callees))[:10]
        )
