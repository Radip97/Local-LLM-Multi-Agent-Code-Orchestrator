"""
src/indexer/dependency.py
Builds a dependency graph using AST parsing (no LLM).
"""

import ast
import os
import json
from typing import Dict, List, Set
from src.core.config import EXCLUDED_DIRS

class DependencyBuilder:
    def __init__(self, target_dir: str):
        self.target_dir = target_dir
        self.graph_file = os.path.join(target_dir, "dependency_graph.json")

    def build_graph(self) -> Dict[str, List[str]]:
        graph: Dict[str, List[str]] = {}
        
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, self.target_dir).replace("\\", "/")
                    imports = self._parse_imports(filepath)
                    graph[rel_path] = imports

        with open(self.graph_file, "w") as f:
            json.dump(graph, f, indent=2)

        return graph

    def _parse_imports(self, filepath: str) -> List[str]:
        imports = set()
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=filepath)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module)
        except Exception:
            pass
        return list(imports)
