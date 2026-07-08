"""
agents/developer.py
────────────────────
DeveloperAgent — implements code changes via JSON tool-calling.

Writes ALL output to the STAGING area (.staging/) via the write_file tool.
Files are only promoted to the live project when QA approves.
"""
from __future__ import annotations

from typing import Optional

import config
from agents.base import BaseAgent
from core.memory import LongTermMemory, ShortTermMemory


# ── System prompt ──────────────────────────────────────────────────────────────

DEVELOPER_SYSTEM_PROMPT = """\
You are a senior software developer implementing specific, scoped code changes.

YOUR WORKFLOW:
1. Use `read_file` to read any files you need to understand before writing.
2. Use `list_files` if you need to explore the directory structure.
3. Use `search_code` to find existing patterns, imports, or functions.
4. Use `write_file` to write complete, working file content to staging.
   - For new files: write the full content from scratch.
   - For modified files: read first, then write the entire updated version.
5. Use `patch_file` for targeted edits (when you need to change a small portion of a large file).
6. Use `check_syntax` to validate Python/JS/HTML files after writing.
7. Once ALL files are written and validated, call `final_answer` with a brief summary.

CRITICAL RULES:
• ONLY implement the CURRENT STEP — do NOT add features from other steps.
• `write_file` requires the COMPLETE file content — never write a partial snippet.
• Always read existing files before modifying them.
• Validate Python files with `check_syntax` after writing.
• Never output code in your `final_answer` — only tool calls contain code.
• Your `final_answer` result must list which files you wrote and what changed.
"""


# ── Agent class ────────────────────────────────────────────────────────────────

class DeveloperAgent(BaseAgent):
    ROLE  = "Developer"
    TOOLS = ["read_file", "write_file", "patch_file", "list_files",
             "search_code", "check_syntax"]

    def __init__(
        self,
        model_name: Optional[str] = None,
        stm: Optional[ShortTermMemory] = None,
        ltm: Optional[LongTermMemory] = None,
        executor_context: Optional[dict] = None,
        verbose: bool = False,
    ) -> None:
        super().__init__(
            model_name=model_name or config.DEVELOPER_MODEL,
            stm=stm, ltm=ltm,
            executor_context=executor_context,
            verbose=verbose,
        )

    def write_code(
        self,
        user_request: str,
        approved_plan: str,
        step_instruction: str,
        codebase_context: str,
        qa_feedback: str = "",
        image_paths: Optional[list[str]] = None,
    ) -> str:
        """
        Implement the current step via the JSON tool loop.
        Returns the final_answer summary text (not the code — that goes to staging).
        """
        image_paths = image_paths or []
        image_note = (
            f"\n\n### Visual Reference:\nYou have {len(image_paths)} reference image(s). "
            "Match their aesthetic in your implementation.\n"
            if image_paths else ""
        )

        qa_note = ""
        if qa_feedback:
            qa_note = (
                "\n\n### ⚠️  QA REJECTION — FIX ALL THESE ISSUES:\n"
                f"{qa_feedback}\n\n"
                "Every issue listed above MUST be resolved in this attempt. "
                "Do not skip any of them.\n"
            )

        tool_summary = self.stm.tool_summary(last_n=4)
        error_ctx    = self._error_context()

        # Truncate plan if too long to save context budget
        plan_summary = approved_plan
        if len(approved_plan) > 1800:
            import re
            m = re.search(r"(## Proposed Changes[\s\S]*)", approved_plan)
            plan_summary = m.group(1) if m else approved_plan[:1800] + "\n...(truncated)"

        user_message = f"""\
### Overall Task:
{user_request}{image_note}

### Approved Implementation Plan:
{plan_summary}

### Current Step to Implement:
{step_instruction}

### Existing Project State:
{codebase_context}{qa_note}{error_ctx}

### Recent Tool Activity:
{tool_summary}

Start by reading relevant existing files, then write your implementation via tool calls.
When all files are written and syntax-checked, call `final_answer` summarising what you wrote.
"""
        return self.run_with_tools(DEVELOPER_SYSTEM_PROMPT, user_message)
