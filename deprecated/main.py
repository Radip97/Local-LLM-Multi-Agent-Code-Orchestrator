"""
main.py  —  Core Orchestrator
══════════════════════════════
The isolated, importable workflow engine. Can be used directly or via cli.py.

Architecture
────────────
• Staging area (.staging/)  — developer writes here; QA reads here.
  On approval  → files are flushed to the live project.
  On rejection → staging is wiped; developer retries from a clean state.

• Planning loop  — Planner drafts a plan, QA reviews it; rejected plans are
  fed back to the Planner with structured feedback (up to MAX_PLAN_ITERATIONS).

• Dev/QA loop    — For each sub-task: Developer implements → QA reviews.
  Rejections inject structured issue JSON back into the Developer's next prompt.
  After MAX_CODE_ITERATIONS failed attempts, the step is failed and the
  orchestrator attempts to continue with remaining steps.

• Checkpoint/Resume — state is saved to LongTermMemory after each approved step
  so a workflow interrupted mid-run can be resumed with `--resume`.
"""
from __future__ import annotations

# ── Python 3.10 alpha compatibility (must be first) ────────────────────────────
import dataclasses as _dc
import types as _types

if not hasattr(_types, "UnionType"):
    _types.UnionType = type("UnionType", (), {})

_orig_dc = _dc.dataclass
def _patched_dc(*args, **kwargs):
    kwargs.pop("slots", None)
    kwargs.pop("kw_only", None)
    return _orig_dc(*args, **kwargs)
_dc.dataclass = _patched_dc
# ──────────────────────────────────────────────────────────────────────────────

import os
import re
import shutil
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

import config

# Import all tools (side-effect: registers them in the global ToolRegistry)
import tools  # noqa: F401

from agents.developer import DeveloperAgent
from agents.planner import PlannerAgent
from agents.qa import QAIssue, QAAgent, QAResult
from core.memory import LongTermMemory, ShortTermMemory
from tools.code_tools import check_syntax

console = Console()


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class Orchestrator:
    """
    Main workflow engine. Importable and reusable — CLI wraps this class.

    Parameters
    ──────────
    target_dir   Project directory where code is written.
    files        Optional list of relative file paths to load as context
                 (overrides automatic directory scan).
    verbose      If True, prints each JSON tool call/result to stderr.
    """

    STAGING_DIR_NAME = ".staging"

    def __init__(
        self,
        target_dir: str,
        files: list[str] | None = None,
        verbose: bool = False,
    ) -> None:
        self.target_dir  = os.path.abspath(target_dir)
        self.files       = files
        self.verbose     = verbose
        self.staging_dir = os.path.join(self.target_dir, self.STAGING_DIR_NAME)

        if not os.path.isdir(self.target_dir):
            os.makedirs(self.target_dir)
            console.print(f"[yellow]Created target directory: {self.target_dir}[/yellow]")

        # Shared memory
        self.stm = ShortTermMemory()
        self.ltm = LongTermMemory(self.target_dir)

        # Executor context injected into every tool call
        self._exec_ctx: dict = {
            "staging_dir": self.staging_dir,
            "target_dir":  self.target_dir,
        }

        # Agents (share the same memory and executor context)
        self.planner  = PlannerAgent(stm=self.stm, ltm=self.ltm,
                                     executor_context=self._exec_ctx, verbose=verbose)
        self.developer = DeveloperAgent(stm=self.stm, ltm=self.ltm,
                                        executor_context=self._exec_ctx, verbose=verbose)
        self.qa       = QAAgent(stm=self.stm, ltm=self.ltm,
                                executor_context=self._exec_ctx, verbose=verbose)

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────────

    def run(self, user_request: str, resume: bool = False) -> bool:
        """
        Execute the full planning → development → QA workflow.
        Returns True if completed successfully.
        """
        console.print(Panel(
            f"[bold blue]Local Agent Orchestrator[/bold blue]\n"
            f"[bold]Target:[/bold] {self.target_dir}\n"
            f"[bold]Task:[/bold]   {user_request}",
            title="Starting Workflow",
        ))

        # Verify LLM connection
        with console.status("[cyan]Connecting to LLM server...[/cyan]"):
            try:
                model = self.planner.get_model()
                console.print(f"[green]✓ Connected — model: [bold]{model}[/bold][/green]")
            except SystemExit:
                return False

        # Detect reference images
        reference_images = self._get_reference_images()
        if reference_images:
            console.print(
                f"[cyan]Found {len(reference_images)} reference image(s): "
                f"{[os.path.basename(p) for p in reference_images]}[/cyan]"
            )

        # Direct query routing (no planning/coding needed)
        if self._is_direct_query(user_request):
            return self._handle_direct_query(user_request)

        # ── Resume or fresh start ─────────────────────────────────────────────
        if resume:
            checkpoint = self.ltm.load_checkpoint()
            if checkpoint:
                approved_plan = checkpoint["plan"]
                sub_tasks     = checkpoint["sub_tasks"]
                start_idx     = checkpoint["step_idx"]
                if start_idx >= len(sub_tasks):
                    self.ltm.clear_checkpoint()
                    console.print("[green]Checkpoint already completed; cleared stale checkpoint.[/green]")
                    return True
                console.print(Panel(
                    f"[bold green]Resuming from step {start_idx + 1}/{len(sub_tasks)}[/bold green]\n"
                    f"[bold]Next step:[/bold] {sub_tasks[start_idx]}",
                    title="Checkpoint Restored", border_style="green",
                ))
                return self._run_dev_loop(
                    user_request, approved_plan, sub_tasks,
                    start_idx, reference_images,
                )

        # ── Planning phase ────────────────────────────────────────────────────
        approved_plan, sub_tasks = self._run_planning_loop(
            user_request, reference_images
        )
        if not approved_plan:
            return False

        # ── Development phase ─────────────────────────────────────────────────
        return self._run_dev_loop(
            user_request, approved_plan, sub_tasks, 0, reference_images
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Planning loop
    # ──────────────────────────────────────────────────────────────────────────

    def _run_planning_loop(
        self,
        user_request: str,
        reference_images: list[str],
    ) -> tuple[str | None, list[str]]:
        """Returns (approved_plan_text, sub_tasks_list) or (None, []) on failure."""
        console.print("\n[bold yellow]=== PHASE 1: PLANNING ===[/bold yellow]")

        spec = self._get_project_spec()
        codebase_ctx = (
            f"### Project Spec:\n{spec}"
            if spec else "(Fresh project — no spec yet)"
        )

        feedback_history: list[str] = []

        for iteration in range(1, config.MAX_PLAN_ITERATIONS + 1):
            console.print(f"\n[bold]Planning iteration {iteration}/{config.MAX_PLAN_ITERATIONS}[/bold]")

            with console.status("[cyan]Planner is drafting the implementation plan...[/cyan]"):
                feedback = "\n\n".join(feedback_history) if feedback_history else ""
                plan_text = self.planner.plan(
                    user_request, codebase_ctx,
                    image_paths=reference_images,
                    feedback_history=feedback,
                )

            console.print(Panel(Markdown(plan_text), title=f"Proposed Plan (iter {iteration})"))
            plan_issues = self._validate_plan_shape(plan_text)
            if plan_issues:
                feedback_history.append(
                    f"Iteration {iteration} rejected locally: invalid plan format.\n"
                    + "\n".join(f"  Issue: {issue}" for issue in plan_issues)
                )
                console.print(Panel(
                    "\n".join(plan_issues),
                    title=f"Local Plan Validation (iter {iteration})",
                    border_style="red",
                ))
                continue

            with console.status("[cyan]QA is reviewing the plan...[/cyan]"):
                qa_result = self.qa.review_plan(user_request, plan_text, codebase_ctx)

            border = "green" if qa_result.approved else "red"
            status_label = "✓ APPROVED" if qa_result.approved else "✗ REJECTED"
            console.print(Panel(
                f"[bold]{status_label}[/bold]\n{qa_result.summary}",
                title=f"QA Plan Review (iter {iteration})", border_style=border,
            ))

            if qa_result.approved:
                sub_tasks = PlannerAgent.extract_sub_tasks(plan_text)
                console.print(
                    f"[bold green]✓ Plan approved! {len(sub_tasks)} steps extracted.[/bold green]"
                )
                return plan_text, sub_tasks

            # Build rejection feedback for next iteration
            feedback_history.append(
                f"Iteration {iteration} rejected: {qa_result.summary}\n"
                + "\n".join(
                    f"  Issue: {iss.issue}" for iss in qa_result.issues
                )
            )
            console.print(f"[yellow]Plan rejected → feeding back to planner.[/yellow]")

        console.print("[red]All plan iterations rejected. Aborting.[/red]")
        return None, []

    def _validate_plan_shape(self, plan_text: str) -> list[str]:
        issues: list[str] = []
        sub_tasks = PlannerAgent.extract_sub_tasks(plan_text)
        if not sub_tasks:
            issues.append(
                "Plan must include a '## Sub-tasks Checklist' with numbered '- [ ]' or '1. [ ]' style items."
            )
        elif len(sub_tasks) < 2:
            issues.append("Plan must split coding work into at least two incremental sub-tasks.")

        if "## Proposed Changes" not in plan_text:
            issues.append("Plan must include a '## Proposed Changes' section with exact file paths.")

        mentioned_files = self._extract_file_mentions(plan_text)
        if not mentioned_files:
            issues.append("Plan must mention at least one concrete file path.")

        return issues

    # ──────────────────────────────────────────────────────────────────────────
    # Development / QA loop
    # ──────────────────────────────────────────────────────────────────────────

    def _run_dev_loop(
        self,
        user_request: str,
        approved_plan: str,
        sub_tasks: list[str],
        start_idx: int,
        reference_images: list[str],
    ) -> bool:
        console.print("\n[bold yellow]=== PHASE 2: DEVELOPMENT ===[/bold yellow]")
        console.print(
            f"[dim]Running {len(sub_tasks) - start_idx} step(s) "
            f"(starting from step {start_idx + 1})[/dim]"
        )

        for step_idx, step in enumerate(sub_tasks[start_idx:], start=start_idx + 1):
            console.rule(f"[bold cyan]Step {step_idx}/{len(sub_tasks)}: {step[:70]}[/bold cyan]")

            step_succeeded = self._run_step(
                user_request, approved_plan, step,
                step_idx, reference_images,
            )

            if step_succeeded:
                self.stm.set("last_completed_step", step_idx)
                self.ltm.save_checkpoint(step_idx, sub_tasks, approved_plan)
            else:
                console.print(
                    f"[red]Step {step_idx} failed after all retries. "
                    "Aborting workflow.[/red]"
                )
                self._clear_staging()
                return False

        self.ltm.clear_checkpoint()
        console.print("\n[bold green]✓ Workflow complete![/bold green]")
        return True

    def _run_step(
        self,
        user_request: str,
        approved_plan: str,
        step: str,
        step_idx: int,
        reference_images: list[str],
    ) -> bool:
        """
        Single step: Developer → QA → commit or retry.
        Returns True if the step was approved and committed.
        """
        qa_feedback   = ""
        staged_files: list[str] = []

        for attempt in range(1, config.MAX_CODE_ITERATIONS + 1):
            console.print(
                f"  [dim]Attempt {attempt}/{config.MAX_CODE_ITERATIONS}[/dim]"
            )

            # ── Clear staging ─────────────────────────────────────────────────
            self._clear_staging()
            live_snapshot = self._snapshot_live_files()

            # ── Codebase context for this step ────────────────────────────────
            codebase_ctx = self.get_codebase_context(step)
            step_plan = self._extract_step_plan(approved_plan, step)
            allowed_files = self._extract_file_mentions(step)

            # ── Developer implements step ─────────────────────────────────────
            with console.status(f"[cyan]Developer implementing step {step_idx}...[/cyan]"):
                dev_summary = self.developer.write_code(
                    user_request=user_request,
                    approved_plan=step_plan,
                    step_instruction=step,
                    codebase_context=codebase_ctx,
                    qa_feedback=qa_feedback,
                    image_paths=reference_images,
                )

            console.print(Panel(dev_summary or "(no summary)", title="Developer Output"))

            live_errors = self._validate_live_project_unchanged(live_snapshot)
            if live_errors:
                qa_feedback = self._format_system_rejection(
                    summary="Developer modified live project files instead of staging.",
                    issues=live_errors,
                )
                console.print(Panel(qa_feedback, title="Staging Contract Violation", border_style="red"))
                self._clear_staging()
                continue

            # ── Discover staged files ─────────────────────────────────────────
            staged_files = self._list_staged_files()
            if not staged_files:
                console.print(
                    "[yellow]⚠️  Developer did not write any files to staging. "
                    "QA cannot review nothing.[/yellow]"
                )
                qa_feedback = (
                    "You did not write any files. You MUST use the write_file tool "
                    "to write code files to staging before calling final_answer."
                )
                self._clear_staging()
                continue

            console.print(
                f"  [dim]Staged: {staged_files}[/dim]"
            )

            validation_errors = self._validate_staged_files(staged_files)
            validation_errors.extend(self._validate_step_scope(staged_files, allowed_files))
            if validation_errors:
                qa_feedback = self._format_system_rejection(
                    summary="Orchestrator-side staged file validation failed.",
                    issues=validation_errors,
                )
                console.print(Panel(qa_feedback, title="Staged File Validation", border_style="red"))
                self._clear_staging()
                continue

            # ── QA reviews staged files ───────────────────────────────────────
            with console.status("[cyan]QA reviewing staged files...[/cyan]"):
                qa_result = self.qa.review_code(
                    user_request=user_request,
                    approved_plan=step_plan,
                    step_instruction=step,
                    staged_files=staged_files,
                )

            qa_result = self._normalize_qa_result(qa_result)

            border = "green" if qa_result.approved else "red"
            icon   = "✓ APPROVED" if qa_result.approved else "✗ REJECTED"
            console.print(Panel(
                f"[bold]{icon}[/bold]\n{qa_result.summary}",
                title=f"QA Code Review (attempt {attempt})", border_style=border,
            ))

            if qa_result.approved:
                self._flush_staging()
                console.print(f"[bold green]✓ Step {step_idx} committed to project.[/bold green]")
                self._update_project_spec(step_idx, step, staged_files)
                return True

            # ── Rejected — build structured feedback ──────────────────────────
            qa_feedback = qa_result.feedback_for_developer()
            if qa_result.issues:
                for issue in qa_result.issues:
                    console.print(
                        f"    [red]✗[/red] {issue.file}: {issue.issue}"
                    )
            self._clear_staging()

        console.print(
            f"[red]Step {step_idx} failed after {config.MAX_CODE_ITERATIONS} attempts.[/red]"
        )
        self._clear_staging()
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # Staging area management
    # ──────────────────────────────────────────────────────────────────────────

    def _clear_staging(self) -> None:
        if os.path.isdir(self.staging_dir):
            shutil.rmtree(self.staging_dir)
        os.makedirs(self.staging_dir)

    def _flush_staging(self) -> None:
        """Copy all staged files to the live project directory."""
        for root, _, files in os.walk(self.staging_dir):
            for fname in files:
                src = os.path.join(root, fname)
                rel = os.path.normpath(os.path.relpath(src, self.staging_dir))
                if os.path.isabs(rel) or rel.startswith(".."):
                    raise RuntimeError(f"Unsafe staged path rejected during flush: {rel}")
                dst = os.path.join(self.target_dir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                console.print(f"    [green]✓[/green] {rel}")
        self._clear_staging()

    def _list_staged_files(self) -> list[str]:
        """Return relative paths of all files currently in staging."""
        files: list[str] = []
        if not os.path.isdir(self.staging_dir):
            return files
        for root, _, fnames in os.walk(self.staging_dir):
            for fname in fnames:
                full = os.path.join(root, fname)
                rel  = os.path.relpath(full, self.staging_dir)
                files.append(rel.replace("\\", "/"))
        return sorted(files)

    def _validate_staged_files(self, staged_files: list[str]) -> list[QAIssue]:
        """Perform deterministic checks before any LLM QA review."""
        issues: list[QAIssue] = []
        seen: set[str] = set()

        for rel in staged_files:
            norm = os.path.normpath(rel)
            if os.path.isabs(norm) or norm.startswith(".."):
                issues.append(QAIssue(
                    file=rel,
                    issue="Unsafe staged file path.",
                    fix="Write only relative paths inside the project.",
                ))
                continue

            if norm in seen:
                issues.append(QAIssue(
                    file=rel,
                    issue="Duplicate staged file path.",
                    fix="Write each staged file once.",
                ))
            seen.add(norm)

            full = os.path.join(self.staging_dir, norm)
            if not os.path.isfile(full):
                issues.append(QAIssue(
                    file=rel,
                    issue="Staged path is missing or is not a file.",
                    fix="Use write_file or patch_file to create a staged file.",
                ))
                continue

            result = check_syntax(
                path=norm,
                staging_dir=self.staging_dir,
                target_dir=self.target_dir,
            )
            if not result.success:
                issues.append(QAIssue(
                    file=rel,
                    issue=result.error or "Syntax validation failed.",
                    fix="Correct the file and run check_syntax before final_answer.",
                ))

        return issues

    def _extract_file_mentions(self, text: str) -> set[str]:
        ext_pat = r"[\w./\\-]+\.(?:py|js|ts|tsx|jsx|css|html|json|yaml|yml|sh|txt|md)"
        mentions = re.findall(ext_pat, text, re.IGNORECASE)
        return {
            os.path.normpath(p.replace("\\", "/").strip("`'\"")).replace("\\", "/").lstrip("./")
            for p in mentions
        }

    def _validate_step_scope(
        self,
        staged_files: list[str],
        allowed_files: set[str],
    ) -> list[QAIssue]:
        if not allowed_files:
            return []

        issues: list[QAIssue] = []
        for rel in staged_files:
            norm = os.path.normpath(rel).replace("\\", "/").lstrip("./")
            if norm not in allowed_files:
                allowed = ", ".join(sorted(allowed_files))
                issues.append(QAIssue(
                    file=rel,
                    issue=f"File is outside the current step scope. Allowed file(s): {allowed}",
                    fix="Only stage files explicitly named in the current checklist step.",
                ))
        return issues

    def _extract_step_plan(self, approved_plan: str, step: str) -> str:
        """Limit model context to the active checklist step and matching file sections."""
        allowed_files = self._extract_file_mentions(step)
        if not allowed_files:
            return (
                "## Current Step Only\n"
                f"{step}\n\n"
                "Implement only this checklist item. Do not start future steps."
            )

        sections: list[str] = []
        for allowed in sorted(allowed_files):
            escaped = re.escape(allowed)
            basename = re.escape(os.path.basename(allowed))
            pattern = (
                rf"(###\s+\[[^\]]+\]\s+`?(?:[^`\n]*[/\\])?(?:{escaped}|{basename})`?"
                rf"[\s\S]*?)(?=\n###\s+\[|\n##\s+|\Z)"
            )
            match = re.search(pattern, approved_plan, re.IGNORECASE)
            if match:
                sections.append(match.group(1).strip())

        detail = "\n\n".join(sections) if sections else "(No matching file detail in plan.)"
        allowed = ", ".join(sorted(allowed_files))
        return (
            "## Current Step Only\n"
            f"{step}\n\n"
            f"Allowed staged file(s): {allowed}\n\n"
            "## Step-Relevant Plan Detail\n"
            f"{detail}\n\n"
            "Do not create, modify, or stage files outside the allowed list."
        )

    def _normalize_qa_result(self, qa_result: object) -> QAResult:
        """Reject non-deterministic or malformed QA responses."""
        if not isinstance(qa_result, QAResult):
            return QAResult(
                decision="REJECTED",
                summary="QA returned a malformed result object.",
                issues=[QAIssue(
                    file="(qa)",
                    issue="QA must return a QAResult parsed from valid JSON.",
                    fix='Return JSON like {"decision":"APPROVED","summary":"...","issues":[]}.',
                )],
            )

        decision = qa_result.decision.upper()
        if decision not in {"APPROVED", "REJECTED"}:
            return QAResult(
                decision="REJECTED",
                summary="QA returned an invalid decision.",
                issues=[QAIssue(
                    file="(qa)",
                    issue=f"Invalid decision: {qa_result.decision}",
                    fix='Use only "APPROVED" or "REJECTED".',
                )],
            )

        if decision == "REJECTED" and not qa_result.issues:
            return QAResult(
                decision="REJECTED",
                summary=qa_result.summary or "QA rejected without actionable issues.",
                issues=[QAIssue(
                    file="(qa)",
                    issue="Rejected QA results must include at least one issue.",
                    fix="Return a concrete issue with file, issue, broken_code, and fix fields.",
                )],
            )

        qa_result.decision = decision
        return qa_result

    def _format_system_rejection(self, summary: str, issues: list[QAIssue]) -> str:
        return QAResult(
            decision="REJECTED",
            summary=summary,
            issues=issues,
        ).feedback_for_developer()

    def _snapshot_live_files(self) -> dict[str, tuple[int, int]]:
        snapshot: dict[str, tuple[int, int]] = {}
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in config.IGNORE_DIRS
                       and d != self.STAGING_DIR_NAME]
            for fname in files:
                if fname in {".agent_memory.json"}:
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, self.target_dir).replace("\\", "/")
                try:
                    stat = os.stat(full)
                except OSError:
                    continue
                snapshot[rel] = (stat.st_mtime_ns, stat.st_size)
        return snapshot

    def _validate_live_project_unchanged(
        self,
        before: dict[str, tuple[int, int]],
    ) -> list[QAIssue]:
        after = self._snapshot_live_files()
        issues: list[QAIssue] = []

        before_keys = set(before)
        after_keys = set(after)
        for rel in sorted(after_keys - before_keys):
            issues.append(QAIssue(
                file=rel,
                issue="Developer created a live project file before QA approval.",
                fix="Write this file through the staged write_file tool instead.",
            ))
        for rel in sorted(before_keys - after_keys):
            issues.append(QAIssue(
                file=rel,
                issue="Developer deleted a live project file before QA approval.",
                fix="Do not modify live project files directly during development attempts.",
            ))
        for rel in sorted(before_keys & after_keys):
            if before[rel] != after[rel]:
                issues.append(QAIssue(
                    file=rel,
                    issue="Developer modified a live project file before QA approval.",
                    fix="Write modifications to staging and let the orchestrator promote them.",
                ))

        return issues

    # ──────────────────────────────────────────────────────────────────────────
    # Context building
    # ──────────────────────────────────────────────────────────────────────────

    def get_codebase_context(self, user_request: str = "") -> str:
        """
        Build a context string from project files for injection into agent prompts.
        Supports explicit file list or smart RAG-lite selection.
        """
        context_parts: list[str] = []

        # Explicit file list mode
        if self.files:
            for rel in self.files:
                full = os.path.join(self.target_dir, rel)
                if not os.path.isfile(full):
                    console.print(f"[yellow]Warning: explicit file '{rel}' not found.[/yellow]")
                    continue
                try:
                    with open(full, encoding="utf-8", errors="ignore") as f:
                        context_parts.append(f"--- File: {rel} ---\n{f.read()}\n---")
                except OSError:
                    pass
            return "\n\n".join(context_parts) or "(No valid explicit files loaded)"

        # Walk directory
        candidates: list[str] = []
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in config.IGNORE_DIRS
                       and d != self.STAGING_DIR_NAME]
            for fname in files:
                _, ext = os.path.splitext(fname)
                if ext.lower() in config.IGNORE_EXTENSIONS:
                    continue
                full = os.path.join(root, fname)
                rel  = os.path.relpath(full, self.target_dir).replace("\\", "/")
                candidates.append(rel)

        if not candidates:
            return "(Empty project — no files present yet)"

        selected = self._rag_select(candidates, user_request)

        for rel in selected:
            full = os.path.join(self.target_dir, rel)
            try:
                with open(full, encoding="utf-8", errors="ignore") as f:
                    context_parts.append(f"--- File: {rel} ---\n{f.read()}\n---")
            except OSError:
                pass

        return "\n\n".join(context_parts)

    def _rag_select(self, candidates: list[str], query: str) -> list[str]:
        """Smart file selection — matches backtick-quoted paths, bare filenames, and keywords."""
        # Raise threshold: if small project, just load everything
        if len(candidates) <= 8 or not query:
            return candidates

        # ── Strategy 1: path/filename mentions (strips backtick/asterisk/quote formatting)
        # Remove markdown formatting: `path/to/file.js` → path/to/file.js
        clean_query = re.sub(r'[`*\'"\[\]]', '', query)
        ext_pat = r"[\w./\\-]+\.(?:py|js|ts|tsx|jsx|css|html|json|yaml|yml|sh|txt|md)"
        raw_mentions = re.findall(ext_pat, clean_query, re.IGNORECASE)
        mentioned = [p.replace("\\", "/").lstrip("./") for p in raw_mentions]

        matched: list[str] = []
        for c in candidates:
            c_norm = c.replace("\\", "/")
            c_base = os.path.basename(c_norm)  # e.g. "main.js"
            for m in mentioned:
                m_base = os.path.basename(m)
                # Match: full path suffix OR bare filename match
                if c_norm.endswith(m) or m.endswith(c_norm) or c_base == m_base:
                    if c not in matched:
                        matched.append(c)
                    break

        if matched:
            # Always include project_spec.md for interface context
            for c in candidates:
                if os.path.basename(c) == "project_spec.md" and c not in matched:
                    matched.insert(0, c)
            console.print(f"[dim]RAG-Lite: {len(matched)} file(s) matched by filename.[/dim]")
            return matched

        # ── Strategy 2: keyword overlap against file path tokens
        words = {w for w in re.findall(r"\w+", clean_query.lower()) if len(w) > 2}
        kw = [c for c in candidates if words & set(re.findall(r"\w+", c.lower()))]
        if kw:
            console.print(f"[dim]RAG-Lite: {len(kw)} file(s) matched by keyword.[/dim]")
            return kw

        # Fallback: first 6 files
        console.print(f"[dim]RAG-Lite: using first 6 files as fallback.[/dim]")
        return candidates[:6]

    # ──────────────────────────────────────────────────────────────────────────
    # Project spec (living documentation)
    # ──────────────────────────────────────────────────────────────────────────

    def _get_project_spec(self) -> str:
        path = os.path.join(self.target_dir, "project_spec.md")
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return f.read()
            except OSError:
                pass
        return ""

    def _update_project_spec(
        self, step_idx: int, step: str, staged_files: list[str]
    ) -> None:
        """Ask the developer model to update the living project spec after each step."""
        spec_path = os.path.join(self.target_dir, "project_spec.md")
        current   = self._get_project_spec()
        files_txt = "\n".join(f"  - {f}" for f in staged_files)

        system = (
            "You are a Technical Spec Writer. Maintain a concise `project_spec.md` "
            "listing every file, its purpose, and the public interfaces (classes, "
            "function signatures). Be brief — no full implementations.\n"
            "Output ONLY the updated Markdown content (no code fences)."
        )
        user = (
            f"### Current Spec:\n{current or '(none yet)'}\n\n"
            f"### Step {step_idx} Completed:\n{step}\n\n"
            f"### Files Written in This Step:\n{files_txt}\n\n"
            "Output the updated project_spec.md content."
        )

        try:
            updated = self.developer.call_llm(system, user)
            os.makedirs(os.path.dirname(spec_path) or self.target_dir, exist_ok=True)
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write(updated)
            console.print("[dim]✓ project_spec.md updated[/dim]")
        except Exception as exc:
            console.print(f"[yellow]⚠️  Could not update project_spec.md: {exc}[/yellow]")

    # ──────────────────────────────────────────────────────────────────────────
    # Direct query routing
    # ──────────────────────────────────────────────────────────────────────────

    def _is_direct_query(self, prompt: str) -> bool:
        p = prompt.strip().lower()
        starters = ("explain", "what", "why", "how does", "how do", "where",
                    "who", "which", "tell me", "describe", "document",
                    "show me", "read", "analyze", "list")
        return p.startswith(starters)

    def _handle_direct_query(self, user_request: str) -> bool:
        console.print("\n[bold green]=== DIRECT QUERY ===[/bold green]")
        ctx = self.get_codebase_context(user_request)
        system = ("You are a helpful programming assistant. "
                  "Answer the user's question based on the codebase context.")
        user_prompt = f"### Codebase:\n{ctx}\n\n### Question:\n{user_request}"
        with console.status("[cyan]Querying model...[/cyan]"):
            answer = self.planner.call_llm(system, user_prompt)
        console.print(Panel(Markdown(answer), title="Answer", border_style="green"))
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # Reference images
    # ──────────────────────────────────────────────────────────────────────────

    def _get_reference_images(self) -> list[str]:
        exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        imgs: list[str] = []
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in config.IGNORE_DIRS
                       and d != self.STAGING_DIR_NAME]
            for fname in files:
                if os.path.splitext(fname)[1].lower() in exts:
                    imgs.append(os.path.join(root, fname))
        return imgs
