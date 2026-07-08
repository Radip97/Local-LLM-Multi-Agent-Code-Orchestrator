"""
src/analyzer/root_cause.py
Root Cause Analyzer: Given parsed errors, determine primary vs secondary errors.
"""

from typing import Dict, Any

class RootCauseAnalyzer:
    def analyze(self, parsed_error: Dict[str, Any], dependency_graph: Dict[str, Any]) -> str:
        """
        Determines the root cause.
        Never asks LLM to fix downstream errors; strips out cascading failures.
        """
        error_type = parsed_error.get("error_type", "unknown")
        raw = parsed_error.get("raw_output", "")
        
        # Simplistic heuristic for root cause
        # A real implementation would trace the stack trace against the dependency graph
        root_cause_summary = f"Root cause identified as {error_type} error. Details:\n{raw}"
        
        return root_cause_summary
