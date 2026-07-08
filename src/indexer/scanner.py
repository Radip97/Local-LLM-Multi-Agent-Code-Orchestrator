"""
src/indexer/scanner.py
Detects project language, framework, package manager, and entrypoints.
"""

import os
import json
from typing import Dict, Any, List
from src.core.config import EXCLUDED_DIRS

class ProjectScanner:
    def __init__(self, target_dir: str):
        self.target_dir = target_dir
        self.manifest_file = os.path.join(target_dir, "project_manifest.json")

    def scan(self) -> Dict[str, Any]:
        manifest = {
            "language": "unknown",
            "framework": "unknown",
            "package_manager": "unknown",
            "entrypoints": [],
            "config_files": [],
            "build_commands": [],
            "test_commands": []
        }
        
        if os.path.exists(self.manifest_file):
            try:
                with open(self.manifest_file, "r") as f:
                    existing = json.load(f)
                    manifest.update(existing)
            except:
                pass

        files = self._get_all_files()
        
        # Detect package manager & language
        if "package.json" in files:
            manifest["language"] = "javascript/typescript"
            manifest["package_manager"] = "npm/yarn/pnpm"
            manifest["config_files"].append("package.json")
            if "tsconfig.json" in files:
                manifest["language"] = "typescript"
                manifest["config_files"].append("tsconfig.json")
        elif "requirements.txt" in files or "pyproject.toml" in files:
            manifest["language"] = "python"
            manifest["package_manager"] = "pip/poetry"
            if "requirements.txt" in files:
                manifest["config_files"].append("requirements.txt")
            if "pyproject.toml" in files:
                manifest["config_files"].append("pyproject.toml")
        elif "go.mod" in files:
            manifest["language"] = "go"
            manifest["package_manager"] = "go modules"
            manifest["config_files"].append("go.mod")
            manifest["build_commands"].append("go build")

        # Detect entrypoints
        entrypoints = [f for f in files if f in ["main.py", "app.py", "index.js", "main.go", "src/index.ts"]]
        manifest["entrypoints"] = entrypoints

        with open(self.manifest_file, "w") as f:
            json.dump(manifest, f, indent=2)

        return manifest

    def _get_all_files(self) -> List[str]:
        all_files = []
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), self.target_dir)
                all_files.append(rel_path.replace("\\", "/"))
        return all_files
