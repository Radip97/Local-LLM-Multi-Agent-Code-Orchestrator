"""
tools/code_tools.py
────────────────────
Code analysis and validation tools: syntax checking and code search.
"""
from __future__ import annotations

import ast
import os
import re
from typing import Optional

from core.tool_registry import ToolResult, tool


@tool(name="check_syntax", description="Check a file for syntax errors. Supports Python (.py) and basic checks for JS/HTML/CSS.")
def check_syntax(path: str, staging_dir: str = "", target_dir: str = "") -> ToolResult:
    """
    path: Relative file path to check (the extension determines which checker is used)
    """
    content: Optional[str] = None
    for base in filter(None, [staging_dir, target_dir]):
        full = os.path.join(base, path)
        if os.path.isfile(full):
            with open(full, encoding="utf-8", errors="replace") as f:
                content = f.read()
            break

    if content is None:
        return ToolResult(success=False, output=None, error=f"File not found: {path}")

    ext = os.path.splitext(path)[1].lower()

    if ext == ".py":
        try:
            ast.parse(content, filename=path)
            return ToolResult(success=True, output=f"✓ {path}: Python syntax OK")
        except SyntaxError as exc:
            return ToolResult(success=False, output=None,
                              error=f"SyntaxError in {path} line {exc.lineno}: {exc.msg}\n"
                                    f"  → {(exc.text or '').strip()}")

    elif ext in (".html", ".htm"):
        issues = []
        lower = content.lower()
        if "<html" not in lower and "<!doctype" not in lower:
            issues.append("Missing <!DOCTYPE> or <html> element")
        opens = len(re.findall(r"<[a-z][a-z0-9]*[^>]*>", content, re.I))
        if opens == 0:
            issues.append("No HTML tags found")
        if issues:
            return ToolResult(success=False, output=None, error="; ".join(issues))
        return ToolResult(success=True, output=f"✓ {path}: HTML structure OK")

    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        issues = []
        opens  = content.count("{")
        closes = content.count("}")
        if abs(opens - closes) > 3:
            issues.append(f"Unbalanced braces: {{={opens} }}={closes}")
        backticks = content.count("`")
        if backticks % 2 != 0:
            issues.append(f"Odd backtick count ({backticks}) — possible unclosed template literal")
        if issues:
            return ToolResult(success=False, output=None, error="; ".join(issues))
        return ToolResult(success=True, output=f"✓ {path}: JS checks passed")

    elif ext == ".css":
        opens  = content.count("{")
        closes = content.count("}")
        if opens != closes:
            return ToolResult(success=False, output=None,
                              error=f"Unbalanced braces in CSS: {{={opens} }}={closes}")
        return ToolResult(success=True, output=f"✓ {path}: CSS braces balanced")

    return ToolResult(success=True, output=f"✓ {path}: No checker for {ext}, skipping")


@tool(name="search_code", description="Grep for a text pattern across all project files. Returns file:line matches.")
def search_code(pattern: str, directory: str = ".", target_dir: str = "") -> ToolResult:
    """
    pattern: Text or regex pattern to search for (case-insensitive)
    directory: Sub-directory to search within (relative to project root, default '.')
    """
    base = os.path.join(target_dir, directory) if target_dir else directory
    if not os.path.isdir(base):
        return ToolResult(success=False, output=None, error=f"Directory not found: {base}")

    SKIP_DIRS = {".git", "__pycache__", ".staging", "node_modules", ".venv"}
    SKIP_EXTS = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".webp",
                 ".ico", ".woff", ".woff2", ".ttf", ".eot", ".zip", ".tar", ".gz"}

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return ToolResult(success=False, output=None, error=f"Invalid regex: {exc}")

    results: list[str] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if os.path.splitext(fname)[1] in SKIP_EXTS:
                continue
            fpath = os.path.join(root, fname)
            rel   = os.path.relpath(fpath, target_dir or base)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append(f"{rel}:{lineno}:  {line.rstrip()}")
                            if len(results) >= 60:
                                break
            except OSError:
                continue
            if len(results) >= 60:
                break

    if not results:
        return ToolResult(success=True, output=f"No matches for: {pattern}")

    if len(results) >= 60:
        results.append("... (output truncated at 60 matches)")

    return ToolResult(success=True, output="\n".join(results))
