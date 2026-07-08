"""
src/context/retriever.py
Returns only relevant files, symbols, and imports based on the task.
"""

import os
import json
from typing import Dict, List, Any
from src.core.config import MAX_TOKENS_PER_REQUEST

class ContextRetriever:
    def __init__(self, target_dir: str):
        self.target_dir = target_dir

    def retrieve(self, task: str) -> str:
        """
        Retrieves context based on task.
        In a full implementation, this would use TF-IDF or vector embeddings
        to match `task` against the symbol_index.json and dependency_graph.json.
        """
        context_parts = []
        
        # Load indexes
        symbol_file = os.path.join(self.target_dir, "symbol_index.json")
        if os.path.exists(symbol_file):
            with open(symbol_file, 'r') as f:
                symbols = json.load(f)
                context_parts.append("### Workspace Symbols")
                context_parts.append(json.dumps(symbols, indent=2)[:2000]) # truncated for budget

        # Simple greedy retrieval for demonstration: just grab main files
        manifest_file = os.path.join(self.target_dir, "project_manifest.json")
        if os.path.exists(manifest_file):
            with open(manifest_file, 'r') as f:
                manifest = json.load(f)
                for entry in manifest.get("entrypoints", []):
                    entry_path = os.path.join(self.target_dir, entry)
                    if os.path.exists(entry_path):
                        with open(entry_path, 'r', encoding='utf-8') as ef:
                            context_parts.append(f"### File: {entry}")
                            context_parts.append(ef.read())

        return "\n\n".join(context_parts)
