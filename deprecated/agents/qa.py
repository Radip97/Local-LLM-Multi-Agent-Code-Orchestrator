"""
agents/qa.py
────────────
QAAgent — reviews staged code and outputs a structured JSON decision.

Uses read_file + check_syntax tools to inspect staged files, then calls
final_answer with a JSON-structured approval or rejection object that the
orchestrator parses for structured feedback to feed back to the developer.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

import config
from agents.base import BaseAgent
from core.memory import LongTermMemory, ShortTermMemory


# ── System prompt ──────────────────────────────────────────────────────────────

QA_SYSTEM_PROMPT = """\
You are a strict Quality Assurance engineer reviewing code changes.

YOUR WORKFLOW:
1. Use `read_file` to read each staged file being reviewed.
2. Use `check_syntax` to verify syntax on Python, JS, HTML, and CSS files.
3. Trace the execution flow mentally — check for runtime errors, missing logic, broken imports.
4. Call `final_answer` with a JSON decision object (see format below).

OUTPUT FORMAT — your `final_answer` result MUST be valid JSON:

If approved:
{"decision": "APPROVED", "summary": "Brief approval note", "issues": []}

If rejected:
{
  "decision": "REJECTED",
  "summary": "One-line summary of the primary problem",
  "issues": [
    {
      "file": "relative/path/to/file",
      "issue": "Exact description of the bug or missing feature",
      "broken_code": "The exact problematic snippet (or null)",
      "fix": "The exact corrected code or precise instruction"
    }
  ]
}

REVIEW RULES:
1. Reject ONLY for functional bugs, missing requirements, or syntax errors.
2. Do NOT reject for style preferences, variable naming, or cosmetic choices.
3. If the developer implemented MORE than required — APPROVE as long as it works.
4. When rejecting: `fix` MUST be copy-pasteable corrected code — NOT a vague description.
5. If code is syntactically correct and logically implements the step → APPROVE.
6. Be decisive: never partially reject without listing all specific issues.
"""


# ── Result data classes ────────────────────────────────────────────────────────

@dataclass
class QAIssue:
    file: str
    issue: str
    broken_code: Optional[str] = None
    fix: Optional[str] = None

    def as_feedback_text(self) -> str:
        lines = [f"  File: {self.file}", f"  Issue: {self.issue}"]
        if self.broken_code:
            lines.append(f"  Broken:\n    {self.broken_code}")
        if self.fix:
            lines.append(f"  Fix:\n    {self.fix}")
        return "\n".join(lines)


@dataclass
class QAResult:
    decision: str          # "APPROVED" or "REJECTED"
    summary: str
    issues: list[QAIssue] = field(default_factory=list)

    @property
    def approved(self) -> bool:
        return self.decision.upper() == "APPROVED"

    def feedback_for_developer(self) -> str:
        """Structured feedback string to inject into the developer's next prompt."""
        if self.approved:
            return ""
        lines = [f"QA REJECTION: {self.summary}", ""]
        for i, issue in enumerate(self.issues, 1):
            lines.append(f"Issue {i}:\n{issue.as_feedback_text()}")
            lines.append("")
        return "\n".join(lines)


# ── Agent class ────────────────────────────────────────────────────────────────

class QAAgent(BaseAgent):
    ROLE  = "QA"
    TOOLS = ["read_file", "check_syntax"]

    def __init__(
        self,
        model_name: Optional[str] = None,
        stm: Optional[ShortTermMemory] = None,
        ltm: Optional[LongTermMemory] = None,
        executor_context: Optional[dict] = None,
        verbose: bool = False,
    ) -> None:
        super().__init__(
            model_name=model_name or config.QA_MODEL,
            stm=stm, ltm=ltm,
            executor_context=executor_context,
            verbose=verbose,
        )

    # ── Plan review (no tools needed) ─────────────────────────────────────────

    def review_plan(
        self,
        user_request: str,
        proposed_plan: str,
        codebase_context: str,
    ) -> QAResult:
        prompt = f"""\
### User Request:
{user_request}

### Existing Project State:
{codebase_context}

### Proposed Plan:
{proposed_plan}

Verify: Does the plan cover all requirements? Are file paths correct? Are steps granular enough?
Output ONLY valid JSON: {{"decision": "...", "summary": "...", "issues": [...]}}
"""
        raw = self.call_llm(QA_SYSTEM_PROMPT, prompt, temperature=config.MODEL_TEMPERATURE)
        return self._parse(raw)

    # ── Code review (uses tools to read staged files) ─────────────────────────

    def review_code(
        self,
        user_request: str,
        approved_plan: str,
        step_instruction: str,
        staged_files: list[str],
    ) -> QAResult:
        """
        Reviews the files written to staging for the current step.
        staged_files: list of relative paths that were written to staging.
        """
        plan_summary = approved_plan
        if len(approved_plan) > 1200:
            m = re.search(r"(## Proposed Changes[\s\S]*)", approved_plan)
            plan_summary = m.group(1) if m else approved_plan[:1200] + "...(truncated)"

        files_list = "\n".join(f"  - {f}" for f in staged_files) if staged_files \
                     else "  (check staging directory for new or modified files)"

        user_message = f"""\
### Task:
{user_request}

### Step Being Reviewed:
{step_instruction}

### Approved Plan Summary:
{plan_summary}

### Files to Review (in staging):
{files_list}

Read each file with `read_file`, check syntax with `check_syntax`, then call `final_answer`
with a valid JSON decision: {{"decision": "...", "summary": "...", "issues": [...]}}
"""
        raw = self.run_with_tools(QA_SYSTEM_PROMPT, user_message)
        result = self._parse(raw)

        # Store rejection patterns in LTM
        if not result.approved and result.issues and self.ltm:
            for issue in result.issues:
                self.ltm.add_error_pattern(
                    agent="Developer",
                    error=issue.issue,
                    context=f"step={step_instruction[:80]}, file={issue.file}",
                )

        return result

    # ── Parser ─────────────────────────────────────────────────────────────────

    def _parse(self, text: str) -> QAResult:
        """Extract structured QAResult from the agent's text output."""
        raw = text.strip()

        # Try direct JSON parse of whole response
        data = self._try_json(raw)
        if data is None:
            # Look inside ``` blocks
            m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw, re.DOTALL)
            if m:
                data = self._try_json(m.group(1))
        if data is None:
            # Outermost balanced braces
            depth, start = 0, None
            for i, ch in enumerate(raw):
                if ch == "{":
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == "}" and depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        data = self._try_json(raw[start: i + 1])
                        if data:
                            break

        if data and isinstance(data, dict) and "decision" in data:
            decision = str(data.get("decision", "REJECTED")).upper()
            summary  = str(data.get("summary", ""))
            issues   = [
                QAIssue(
                    file=str(item.get("file", "unknown")),
                    issue=str(item.get("issue", "")),
                    broken_code=item.get("broken_code"),
                    fix=item.get("fix"),
                )
                for item in data.get("issues", [])
                if isinstance(item, dict)
            ]
            return QAResult(decision=decision, summary=summary, issues=issues)

        # Fallback: look for DECISION: APPROVED / REJECTED
        if re.search(r"DECISION:\s*APPROVED", raw, re.IGNORECASE):
            return QAResult(decision="APPROVED", summary="Approved (text fallback parser)")
        if re.fullmatch(r"\s*APPROVED\s*", raw, re.IGNORECASE):
            return QAResult(decision="APPROVED", summary="Approved (bare decision fallback parser)")
        if re.fullmatch(r"\s*REJECTED\s*", raw, re.IGNORECASE):
            return QAResult(
                decision="REJECTED",
                summary="Rejected without structured issues.",
                issues=[QAIssue(
                    file="(qa)",
                    issue="QA returned bare REJECTED without actionable issue details.",
                    fix="Return JSON with decision, summary, and issues.",
                )],
            )

        return QAResult(
            decision="REJECTED",
            summary="QA returned unparseable output — treating as rejection for safety.",
            issues=[QAIssue(
                file="(unknown)",
                issue=f"QA raw output could not be parsed as JSON: {raw[:400]}",
                fix="Ensure QA outputs only valid JSON in final_answer.",
            )],
        )

    @staticmethod
    def _try_json(s: str):
        try:
            s = re.sub(r"^```(?:json)?\s*", "", s.strip())
            s = re.sub(r"\s*```$", "", s.strip())
            return json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return None
