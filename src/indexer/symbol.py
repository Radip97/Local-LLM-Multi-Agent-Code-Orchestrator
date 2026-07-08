"""
src/indexer/symbol.py
Indexes classes, functions, and variables using AST (no LLM).
"""

import ast
import os
import json
from typing import Dict, List, Any
from src.core.config import EXCLUDED_DIRS

class SymbolIndexer:
    def __init__(self, target_dir: str):
        self.target_dir = target_dir
        self.index_file = os.path.join(target_dir, "symbol_index.json")

    def build_index(self) -> Dict[str, Any]:
        index: Dict[str, Any] = {}
        
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, self.target_dir).replace("\\", "/")
                    symbols = self._parse_symbols(filepath)
                    index[rel_path] = symbols

        with open(self.index_file, "w") as f:
            json.dump(index, f, indent=2)

        return index

    def _parse_symbols(self, filepath: str) -> Dict[str, List[str]]:
        symbols = {"classes": [], "functions": []}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=filepath)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    symbols["classes"].append(node.name)
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    symbols["functions"].append(node.name)
        except Exception:
            pass
        return symbols
