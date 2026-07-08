"""
agents/planner.py
─────────────────
PlannerAgent — decomposes a user request into an ordered sub-task checklist.

Uses list_files + read_file tools to inspect the project before planning,
then outputs a Markdown plan with a numbered Sub-tasks Checklist.
"""
from __future__ import annotations

import re
from typing import Optional

import config
from agents.base import BaseAgent
from core.memory import LongTermMemory, ShortTermMemory


# ── System prompt ──────────────────────────────────────────────────────────────

PLANNER_SYSTEM_PROMPT = """\
You are an expert software architect and technical planner.

YOUR JOB:
1. Use the `list_files` tool to understand the current project structure.
2. Use the `read_file` tool to read any relevant existing files.
3. Once you have enough context, call `final_answer` with a Markdown plan.

PLAN FORMAT (inside the final_answer result):
```
# Implementation Plan: <Title>

## Goal
<One paragraph describing what the plan achieves>

## Sub-tasks Checklist
1. [ ] <Step 1 description — must be a skeleton: empty classes, stubs, NO logic>
2. [ ] <Step 2 description — first working feature>
3. [ ] <Step 3 — next feature, depends on step 2>
...

## Proposed Changes
### [NEW/MODIFY/DELETE] `relative/path/to/file`
- Exact structural or behavioural changes here
- (Optional) Function signatures or pseudo-code outlines

## Edge Cases & Testing
- What to verify after each step
```

PLANNING RULES:
• Break work into 4–7 granular, progressive steps.
• Step 1 MUST be a skeleton (file structure with empty stubs) — NO complex logic yet.
• Each step must be tiny and focused (one concern per step).
• Never write a step that says "implement the whole feature" — be incremental.
• List exact file paths for every change.
"""


# ── Agent class ────────────────────────────────────────────────────────────────

class PlannerAgent(BaseAgent):
    ROLE  = "Planner"
    TOOLS = ["list_files", "read_file"]

    def __init__(
        self,
        model_name: Optional[str] = None,
        stm: Optional[ShortTermMemory] = None,
        ltm: Optional[LongTermMemory] = None,
        executor_context: Optional[dict] = None,
        verbose: bool = False,
    ) -> None:
        super().__init__(
            model_name=model_name or config.PLANNER_MODEL,
            stm=stm, ltm=ltm,
            executor_context=executor_context,
            verbose=verbose,
        )

    def plan(
        self,
        user_request: str,
        codebase_context: str,
        image_paths: Optional[list[str]] = None,
        feedback_history: str = "",
    ) -> str:
        """
        Generate an implementation plan.
        Returns the Markdown plan text.
        """
        image_paths = image_paths or []
        image_note = (
            f"\n\n### Visual Reference:\nYou have {len(image_paths)} reference image(s). "
            "Match their aesthetic and colour palette in your plan.\n"
            if image_paths else ""
        )

        history_note = (
            f"\n\n### Previous Plan Feedback (incorporate this):\n{feedback_history}\n"
            if feedback_history else ""
        )

        error_ctx = self._error_context()

        user_message = f"""\
### User Request:
{user_request}{image_note}{history_note}

### Current Project State:
{codebase_context}{error_ctx}

Inspect the project with tools as needed, then call `final_answer` with the full Markdown plan.
"""
        # Planner uses tool loop (list_files, read_file) then final_answer
        plan_text = self.run_with_tools(PLANNER_SYSTEM_PROMPT, user_message)

        # Save to LTM for resume capability
        if self.ltm:
            self.ltm.remember("last_plan_text", plan_text)

        return plan_text

    @staticmethod
    def extract_sub_tasks(plan: str) -> list[str]:
        """
        Pull out the numbered checklist items from the plan text.
        Returns a list of task description strings.
        """
        items = re.findall(r"^\s*\d+\.\s*\[\s*\]\s*(.+)$", plan, re.MULTILINE)
        return [t.strip() for t in items if t.strip()]
