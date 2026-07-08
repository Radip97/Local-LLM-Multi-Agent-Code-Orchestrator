"""
core/memory.py
──────────────
Short-term (session) and Long-term (file-backed) memory for the orchestrator.

ShortTermMemory  — Python dict, lives for one orchestrator.run() call.
LongTermMemory   — JSON file at <target_dir>/.agent_memory.json, persists runs.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional


# ── Short-term memory ──────────────────────────────────────────────────────────

class ShortTermMemory:
    """Ephemeral key-value store for the current run."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._tool_log: list[dict] = []

    # KV store
    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def snapshot(self) -> dict:
        return deepcopy(self._store)

    # Tool execution log
    def log_tool(
        self,
        agent: str,
        tool: str,
        args: dict,
        success: bool,
        output_preview: str,
    ) -> None:
        self._tool_log.append({
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "agent": agent,
            "tool": tool,
            "args": {k: str(v)[:80] for k, v in args.items()},
            "success": success,
            "preview": output_preview[:160],
        })

    def tool_summary(self, last_n: int = 5) -> str:
        recent = self._tool_log[-last_n:]
        if not recent:
            return "(no tool calls yet)"
        lines = []
        for e in recent:
            icon = "✓" if e["success"] else "✗"
            lines.append(f"  {icon} [{e['agent']}] {e['tool']}({e['args']}) → {e['preview']}")
        return "\n".join(lines)

    def clear_tool_log(self) -> None:
        self._tool_log.clear()


# ── Long-term memory ───────────────────────────────────────────────────────────

class LongTermMemory:
    """
    JSON-file-backed store that persists across runs.
    Stored at <target_dir>/.agent_memory.json.
    """

    FILENAME = ".agent_memory.json"

    def __init__(self, target_dir: str) -> None:
        self._path = os.path.join(target_dir, self.FILENAME)
        self._data: dict[str, Any] = self._load()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if os.path.exists(self._path):
            try:
                with open(self._path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            import sys
            print(f"[LongTermMemory] Warning — could not save: {exc}", file=sys.stderr)

    # ── Generic KV ────────────────────────────────────────────────────────────

    def remember(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def recall(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    # ── Checkpoint (workflow resume) ───────────────────────────────────────────

    def save_checkpoint(self, step_idx: int, sub_tasks: list[str], plan: str) -> None:
        self._data["checkpoint"] = {
            "step_idx": step_idx,
            "sub_tasks": sub_tasks,
            "plan": plan,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save()

    def load_checkpoint(self) -> Optional[dict]:
        return self._data.get("checkpoint")

    def clear_checkpoint(self) -> None:
        self._data.pop("checkpoint", None)
        self._save()

    # ── Error pattern tracking ─────────────────────────────────────────────────

    def add_error_pattern(self, agent: str, error: str, context: str) -> None:
        patterns = self._data.get("error_patterns", [])
        patterns.append({
            "agent": agent,
            "error": error[:300],
            "context": context[:200],
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        })
        self._data["error_patterns"] = patterns[-30:]  # keep last 30
        self._save()

    def get_error_patterns(self, last_n: int = 5) -> list[dict]:
        return self._data.get("error_patterns", [])[-last_n:]

    def error_pattern_summary(self) -> str:
        patterns = self.get_error_patterns()
        if not patterns:
            return ""
        lines = [f"  [{p['agent']}] {p['error']}" for p in patterns]
        return "\n## Past Errors to Avoid:\n" + "\n".join(lines)

    # ── Project file registry ──────────────────────────────────────────────────

    def update_file_registry(self, files: dict[str, str]) -> None:
        """files: {relative_path: one-line description}"""
        registry = self._data.get("file_registry", {})
        registry.update(files)
        self._data["file_registry"] = registry
        self._save()

    def get_file_registry(self) -> dict[str, str]:
        return self._data.get("file_registry", {})
