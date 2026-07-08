"""
tools/file_tools.py
───────────────────
File-system tools available to agents.

All WRITE operations go to the STAGING directory (.staging/<path>) rather than
the live project. The orchestrator flushes staging → project on QA approval and
clears it on rejection, so agents never patch their own buggy outputs.

READ operations check staging first, then the live target directory.
"""
from __future__ import annotations

import os
from typing import Optional

from core.tool_registry import ToolResult, tool


# ── Read ───────────────────────────────────────────────────────────────────────

@tool(name="read_file", description="Read the full contents of a file from the project. Checks staging first, then the live project.")
def read_file(path: str, staging_dir: str = "", target_dir: str = "") -> ToolResult:
    """
    path: Relative path to the file within the project (e.g. 'src/main.py')
    """
    for base in filter(None, [staging_dir, target_dir]):
        full = os.path.join(base, path)
        if os.path.isfile(full):
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    return ToolResult(success=True, output=f.read())
            except OSError as exc:
                return ToolResult(success=False, output=None, error=str(exc))

    return ToolResult(success=False, output=None, error=f"File not found: {path}")


@tool(name="list_files", description="List all files in the project directory tree, excluding hidden/build folders.")
def list_files(directory: str = ".", target_dir: str = "") -> ToolResult:
    """
    directory: Sub-directory to list, relative to the project root. Use '.' for the root.
    """
    base = os.path.join(target_dir, directory) if target_dir else directory
    if not os.path.isdir(base):
        return ToolResult(success=False, output=None, error=f"Directory not found: {directory}")

    SKIP_DIRS = {".git", "__pycache__", ".staging", "node_modules", ".venv", "venv",
                 "dist", "build", ".idea", ".vscode"}
    SKIP_EXTS = {".pyc", ".pyo", ".pyd"}

    lines: list[str] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rel_root = os.path.relpath(root, target_dir or base)
        depth = rel_root.count(os.sep) if rel_root != "." else 0
        indent = "  " * depth
        folder_name = os.path.basename(root) if rel_root != "." else "."
        lines.append(f"{indent}{folder_name}/")
        for fname in sorted(files):
            if os.path.splitext(fname)[1] not in SKIP_EXTS:
                lines.append(f"{indent}  {fname}")

    return ToolResult(success=True, output="\n".join(lines))


# ── Write (to staging) ─────────────────────────────────────────────────────────

@tool(name="write_file", description="Write complete content to a file. The file is written to the staging area and only committed to the project after QA approval.")
def write_file(path: str, content: str, staging_dir: str = "") -> ToolResult:
    """
    path: Relative path for the file (e.g. 'templates/index.html')
    content: The complete file content to write — must be the FULL file, not a snippet
    """
    if not staging_dir:
        return ToolResult(success=False, output=None,
                          error="No staging directory configured. Orchestrator must inject 'staging_dir'.")

    # Safety: reject path-traversal
    norm = os.path.normpath(path)
    if os.path.isabs(norm) or norm.startswith(".."):
        return ToolResult(success=False, output=None, error=f"Unsafe path rejected: {path}")

    full = os.path.join(staging_dir, norm)
    os.makedirs(os.path.dirname(full) or staging_dir, exist_ok=True)

    try:
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        size = len(content.encode())
        return ToolResult(success=True, output=f"Wrote {size:,} bytes → staging/{norm}")
    except OSError as exc:
        return ToolResult(success=False, output=None, error=str(exc))


@tool(name="patch_file", description="Apply a targeted search-and-replace edit to an existing file. Safer than rewriting the whole file for small changes.")
def patch_file(path: str, search: str, replace: str,
               staging_dir: str = "", target_dir: str = "") -> ToolResult:
    """
    path: Relative path to the file to patch
    search: The exact existing text to find (must match character-for-character)
    replace: The replacement text
    """
    # Load current content (staging preferred)
    content: Optional[str] = None
    for base in filter(None, [staging_dir, target_dir]):
        full = os.path.join(base, path)
        if os.path.isfile(full):
            with open(full, encoding="utf-8", errors="replace") as f:
                content = f.read()
            break

    if content is None:
        return ToolResult(success=False, output=None, error=f"File not found for patching: {path}")

    if search not in content:
        # Try normalising line endings
        search_n = search.replace("\r\n", "\n")
        content_n = content.replace("\r\n", "\n")
        if search_n not in content_n:
            return ToolResult(success=False, output=None,
                              error=f"Search text not found in {path}. "
                                    "Tip: use read_file first to get the exact text.")
        content = content_n.replace(search_n, replace, 1)
    else:
        content = content.replace(search, replace, 1)

    # Write patched version to staging
    if not staging_dir:
        return ToolResult(success=False, output=None, error="No staging_dir configured.")

    norm = os.path.normpath(path)
    full_staging = os.path.join(staging_dir, norm)
    os.makedirs(os.path.dirname(full_staging) or staging_dir, exist_ok=True)
    with open(full_staging, "w", encoding="utf-8") as f:
        f.write(content)

    return ToolResult(success=True, output=f"Patched {path} successfully (staging).")
