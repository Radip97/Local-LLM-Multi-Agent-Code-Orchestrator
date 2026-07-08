"""
Compatibility wrapper for older imports.

The staging-based workflow in main.py is the single authoritative orchestrator.
Import Orchestrator from this module only if older code still references
`orchestrator.Orchestrator`.
"""
from main import Orchestrator

__all__ = ["Orchestrator"]
