"""
cli.py  —  Official CLI Interface
═════════════════════════════════
The supported entry point for the staging-based workflow is:

    python cli.py run     --target ./my_project --task "build a FastAPI app"
    python cli.py debug   --target ./my_project --task "..."      (verbose)
    python cli.py resume  --target ./my_project
    python cli.py agents                                           (list agents)
    python cli.py tools                                            (list tools)
    python cli.py status  --target ./my_project                   (checkpoint)

The Orchestrator class in main.py is the single authoritative workflow engine.
This file is purely the user-facing shell.
"""
from __future__ import annotations

# ── Python 3.10 alpha compat (must run before any 3rd-party import) ──────────
import patch_env  # noqa: F401  (side-effect: patches UnionType, dataclass slots)

import argparse
import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

# ── Lazy imports (heavy; only pulled in when the subcommand needs them) ────────

def _get_orchestrator(target_dir: str, files=None, verbose: bool = False):
    """Import and construct the Orchestrator (deferred to avoid slow startup)."""
    from main import Orchestrator
    return Orchestrator(target_dir=target_dir, files=files, verbose=verbose)


# ══════════════════════════════════════════════════════════════════════════════
# Subcommand handlers
# ══════════════════════════════════════════════════════════════════════════════

def cmd_run(args: argparse.Namespace) -> int:
    """Run the full planning + development workflow."""
    target = os.path.abspath(args.target)
    task   = args.task

    if not task:
        console.print("[bold cyan]Local Agent Orchestrator[/bold cyan]")
        console.print("Enter the coding task you want the agents to implement.")
        try:
            task = input("\nTask > ").strip()
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled.[/yellow]")
            return 0
        if not task:
            console.print("[red]Task cannot be empty.[/red]")
            return 1

    files = None
    if getattr(args, "files", None):
        files = [f.strip() for f in args.files.split(",") if f.strip()]

    orchestrator = _get_orchestrator(target, files=files, verbose=False)
    try:
        success = orchestrator.run(task, resume=False)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        return 0

    return 0 if success else 1


def cmd_debug(args: argparse.Namespace) -> int:
    """Same as run but with verbose tool-call tracing on stderr."""
    target = os.path.abspath(args.target)
    task   = args.task

    if not task:
        try:
            task = input("Task > ").strip()
        except KeyboardInterrupt:
            return 0
        if not task:
            console.print("[red]Task cannot be empty.[/red]")
            return 1

    console.print(Panel(
        "[bold yellow]DEBUG MODE — every JSON tool call will be printed to stderr[/bold yellow]",
        border_style="yellow",
    ))

    orchestrator = _get_orchestrator(target, verbose=True)
    try:
        success = orchestrator.run(task, resume=False)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        return 0

    return 0 if success else 1


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume a previously interrupted workflow from its checkpoint."""
    target = os.path.abspath(args.target)
    orchestrator = _get_orchestrator(target)

    checkpoint = orchestrator.ltm.load_checkpoint()
    if not checkpoint:
        console.print(f"[yellow]No checkpoint found in {target}[/yellow]")
        return 1

    sub_tasks  = checkpoint.get("sub_tasks", [])
    step_idx   = checkpoint.get("step_idx", 0)
    saved_at   = checkpoint.get("ts", "unknown")

    console.print(Panel(
        f"[bold green]Checkpoint found[/bold green]\n"
        f"[bold]Saved:[/bold]     {saved_at}\n"
        f"[bold]Next step:[/bold] {step_idx + 1}/{len(sub_tasks)}\n"
        f"[bold]Step:[/bold]      {sub_tasks[step_idx] if step_idx < len(sub_tasks) else '(done)'}",
        title="Resuming Workflow", border_style="green",
    ))

    try:
        success = orchestrator.run(
            user_request=checkpoint.get("plan", "(no task in checkpoint)"),
            resume=True,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        return 0

    return 0 if success else 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show the workflow checkpoint and long-term memory for a project."""
    target = os.path.abspath(args.target)

    from core.memory import LongTermMemory
    ltm = LongTermMemory(target)

    # ── Checkpoint ────────────────────────────────────────────────────────────
    chk = ltm.load_checkpoint()
    if chk:
        sub_tasks = chk.get("sub_tasks", [])
        step_idx  = chk.get("step_idx", 0)
        t = Table(title="Workflow Checkpoint", box=box.ROUNDED, show_header=False)
        t.add_column("Key",   style="bold cyan",  no_wrap=True)
        t.add_column("Value", style="white")
        t.add_row("Target",    target)
        t.add_row("Saved at",  chk.get("ts", "—"))
        t.add_row("Progress",  f"Step {step_idx + 1} of {len(sub_tasks)}")
        t.add_row("Next step", sub_tasks[step_idx] if step_idx < len(sub_tasks) else "(complete)")
        console.print(t)
    else:
        console.print(f"[yellow]No active checkpoint in: {target}[/yellow]")

    # ── Error patterns ─────────────────────────────────────────────────────────
    patterns = ltm.get_error_patterns(last_n=5)
    if patterns:
        t2 = Table(title="Recent Error Patterns (LTM)", box=box.SIMPLE)
        t2.add_column("Agent",   style="cyan")
        t2.add_column("Error",   style="red")
        t2.add_column("Context", style="dim")
        for p in patterns:
            t2.add_row(p.get("agent", ""), p.get("error", "")[:60], p.get("context", "")[:50])
        console.print(t2)

    # ── File registry ──────────────────────────────────────────────────────────
    registry = ltm.get_file_registry()
    if registry:
        t3 = Table(title="File Registry (LTM)", box=box.SIMPLE)
        t3.add_column("File",        style="green")
        t3.add_column("Description", style="white")
        for path, desc in registry.items():
            t3.add_row(path, desc[:70])
        console.print(t3)

    return 0


def cmd_agents(args: argparse.Namespace) -> int:
    """List all available agents and their tool sets."""
    import config

    rows = [
        ("Planner",   config.PLANNER_MODEL,   "list_files, read_file",
         "Decomposes user requests into sub-task checklists"),
        ("Developer", config.DEVELOPER_MODEL,  "read_file, write_file, patch_file,\nlist_files, search_code, check_syntax",
         "Implements code changes to the staging area"),
        ("QA",        config.QA_MODEL,         "read_file, check_syntax",
         "Reviews staged files and returns structured JSON feedback"),
    ]

    t = Table(title="Available Agents", box=box.ROUNDED)
    t.add_column("Agent",       style="bold cyan",  no_wrap=True)
    t.add_column("Model",       style="yellow")
    t.add_column("Tools",       style="green")
    t.add_column("Description", style="white")
    for role, model, tools, desc in rows:
        t.add_row(role, model, tools, desc)
    console.print(t)

    import config as cfg
    console.print(
        f"\n[dim]LLM endpoint: {cfg.API_BASE_URL}  |  "
        f"Tool-calling: native-first (falls back to JSON-prompt)[/dim]"
    )
    return 0


def cmd_tools(args: argparse.Namespace) -> int:
    """List all registered tools with their descriptions and parameter schemas."""
    # Import tools package to trigger registration
    import tools  # noqa: F401
    from core.tool_registry import _REGISTRY

    if not _REGISTRY:
        console.print("[yellow]No tools registered.[/yellow]")
        return 0

    t = Table(title=f"Registered Tools ({len(_REGISTRY)})", box=box.ROUNDED)
    t.add_column("Tool",        style="bold green",  no_wrap=True)
    t.add_column("Description", style="white", max_width=52)
    t.add_column("Parameters",  style="cyan",  max_width=36)

    for name, defn in sorted(_REGISTRY.items()):
        props = defn.parameters.get("properties", {})
        req   = set(defn.parameters.get("required", []))
        param_lines = []
        for p_name, p_schema in props.items():
            mark = "" if p_name in req else "?"
            p_type = p_schema.get("type", "str")
            param_lines.append(f"{p_name}{mark}: {p_type}")
        t.add_row(name, defn.description, "\n".join(param_lines) or "(none)")

    console.print(t)
    console.print("\n[dim]? = optional parameter[/dim]")
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# Argument parser
# ══════════════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Local LLM Multi-Agent Code Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py run    --target ./my_app --task "build a FastAPI REST API"
  python cli.py run    --target ./my_app                          # prompts for task
  python cli.py debug  --target ./my_app --task "fix the CSS"    # verbose tracing
  python cli.py resume --target ./my_app                         # resume checkpoint
  python cli.py status --target ./my_app                         # show state
  python cli.py agents                                           # list agents
  python cli.py tools                                            # list tools
""",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ── run ──────────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="Run the full planning + development workflow")
    p_run.add_argument("--target", "-t", required=True,
                       help="Project directory to write code into")
    p_run.add_argument("--task", "-T", default="",
                       help="Coding task description (prompted if omitted)")
    p_run.add_argument("--files", "-f", default="",
                       help="Comma-separated list of files to load as context")

    # ── debug ─────────────────────────────────────────────────────────────────
    p_dbg = sub.add_parser("debug", help="Same as run with verbose tool-call tracing")
    p_dbg.add_argument("--target", "-t", required=True, help="Project directory")
    p_dbg.add_argument("--task",   "-T", default="",    help="Coding task")

    # ── resume ────────────────────────────────────────────────────────────────
    p_res = sub.add_parser("resume", help="Resume a previously interrupted workflow")
    p_res.add_argument("--target", "-t", required=True, help="Project directory")

    # ── status ────────────────────────────────────────────────────────────────
    p_sta = sub.add_parser("status", help="Show workflow checkpoint and memory")
    p_sta.add_argument("--target", "-t", required=True, help="Project directory")

    # ── agents ────────────────────────────────────────────────────────────────
    sub.add_parser("agents", help="List available agents and their configurations")

    # ── tools ─────────────────────────────────────────────────────────────────
    sub.add_parser("tools", help="List all registered tools and their schemas")

    return parser


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

_DISPATCH = {
    "run":    cmd_run,
    "debug":  cmd_debug,
    "resume": cmd_resume,
    "status": cmd_status,
    "agents": cmd_agents,
    "tools":  cmd_tools,
}

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if not args.command:
        # No subcommand — print help and exit
        console.print(Panel(
            "[bold cyan]Local LLM Multi-Agent Orchestrator[/bold cyan]\n\n"
            "Usage:  [bold]python cli.py <command> [options][/bold]\n\n"
            "Commands:\n"
            "  [bold green]run[/bold green]     Execute a coding task end-to-end\n"
            "  [bold green]debug[/bold green]   Same as run with verbose tool tracing\n"
            "  [bold green]resume[/bold green]  Resume a paused workflow\n"
            "  [bold green]status[/bold green]  Show checkpoint and memory for a project\n"
            "  [bold green]agents[/bold green]  List agents and their models\n"
            "  [bold green]tools[/bold green]   List registered tools and schemas\n\n"
            "Run [bold]python cli.py <command> --help[/bold] for details.",
            title="cli.py", border_style="cyan",
        ))
        sys.exit(0)

    handler = _DISPATCH.get(args.command)
    if handler is None:
        console.print(f"[red]Unknown command: {args.command}[/red]")
        parser.print_help()
        sys.exit(1)

    try:
        exit_code = handler(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        exit_code = 0

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
