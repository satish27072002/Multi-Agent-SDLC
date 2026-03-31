"""CLI entry point — interactive prompt loop with Rich UI or Textual TUI."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from src.agents.coding import CodingResult
from src.agents.docs import DocsResult
from src.agents.gitops import GitPlan
from src.agents.orchestrator import (
    PipelineCallback,
    PipelineState,
    Stage,
    run_pipeline,
)
from src.agents.review import ReviewResult
from src.agents.testing import TestGenResult, TestRunResult
from src.core.config import load_settings

console = Console()


# ---------------------------------------------------------------------------
# Rich UI callback — wired into the orchestrator pipeline
# ---------------------------------------------------------------------------

class RichPipelineUI(PipelineCallback):
    """Displays live pipeline progress in the terminal."""

    def __init__(self, interactive: bool = True) -> None:
        self._interactive = interactive

    STAGE_LABELS = {
        Stage.PLANNING: "[bold cyan]Orchestrator[/]  Planning task...",
        Stage.CODING: "[bold yellow]Coding[/]        Generating code...",
        Stage.TESTING: "[bold magenta]Testing[/]       Writing tests...",
        Stage.RUNNING_TESTS: "[bold magenta]Testing[/]       Running tests...",
        Stage.REVIEWING: "[bold blue]Review[/]        Checking code quality...",
        Stage.DOCS: "[bold green]Docs[/]          Generating documentation...",
        Stage.GITOPS: "[bold red]GitOps[/]        Planning git operations...",
        Stage.DONE: "[bold green]Done[/]",
        Stage.FAILED: "[bold red]Failed[/]",
    }

    async def on_stage_change(self, state: PipelineState) -> None:
        label = self.STAGE_LABELS.get(state.stage, str(state.stage))
        console.print(f"  {label}")

    async def on_coding_done(self, result: CodingResult) -> None:
        done_msg = f"  [bold yellow]Coding[/]        [green]done[/] — {len(result.files)} file(s)"
        console.print(done_msg)
        console.print()
        console.print(Panel(result.summary, title="Summary", border_style="green"))

        table = Table(title="Generated Files", show_lines=True)
        table.add_column("File", style="cyan")
        table.add_column("Explanation", style="white")
        for f in result.files:
            table.add_row(f.path, f.explanation)
        console.print(table)

        for f in result.files:
            lang = _guess_lang(f.path)
            syntax = Syntax(f.content, lang, theme="monokai", line_numbers=True)
            console.print(Panel(syntax, title=f.path, border_style="blue"))

    async def on_tests_generated(self, result: TestGenResult) -> None:
        generated_msg = (
            "  [bold magenta]Testing[/]       [green]generated[/] — "
            f"{len(result.test_files)} test file(s)"
        )
        console.print(generated_msg)

    async def on_tests_run(self, result: TestRunResult) -> None:
        status = "[green]passed[/]" if result.passed else "[red]failed[/]"
        run_msg = (
            "  [bold magenta]Testing[/]       "
            f"{result.tests_passed}/{result.tests_run} tests {status}"
        )
        console.print(run_msg)
        if not result.passed:
            console.print(Panel(result.output, title="Test Output", border_style="red"))

    async def on_review_done(self, result: ReviewResult) -> None:
        status = "[green]approved[/]" if result.approved else "[red]changes requested[/]"
        console.print(f"  [bold blue]Review[/]        {status}")
        if result.issues:
            table = Table(title="Review Issues", show_lines=True)
            table.add_column("File", style="cyan")
            table.add_column("Line", style="yellow")
            table.add_column("Severity", style="red")
            table.add_column("Message", style="white")
            for issue in result.issues:
                table.add_row(issue.file, issue.line, issue.severity.value, issue.message)
            console.print(table)
        console.print(Panel(result.summary, title="Review Summary", border_style="blue"))

    async def on_docs_done(self, result: DocsResult) -> None:
        docs_msg = f"  [bold green]Docs[/]          [green]done[/] — {len(result.files)} file(s)"
        console.print(docs_msg)

    async def on_git_plan(self, plan: GitPlan) -> None:
        console.print(f"  [bold red]GitOps[/]        branch: [cyan]{plan.branch_name}[/]")
        console.print(f"  [bold red]GitOps[/]        commit: {plan.commit_message}")

    async def on_error(self, stage: Stage, error: str) -> None:
        console.print(f"  [bold red]Error[/] in {stage.value}: {error}")

    async def request_approval(self, state: PipelineState) -> bool:
        if not self._interactive:
            return True
        console.print()
        choice = console.input("[bold yellow][A]pprove  [R]eject:[/] ").strip().lower()
        return choice in ("a", "approve", "yes", "y")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guess_lang(path: str) -> str:
    suffixes = {
        ".py": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".rs": "rust",
        ".go": "go", ".java": "java", ".rb": "ruby", ".sh": "bash",
        ".yaml": "yaml", ".yml": "yaml", ".json": "json",
        ".html": "html", ".css": "css", ".sql": "sql",
    }
    for ext, lang in suffixes.items():
        if path.endswith(ext):
            return lang
    return "text"


def _show_final_summary(state: PipelineState) -> None:
    parts: list[str] = []

    if state.coding_result:
        files = [f.path for f in state.coding_result.files]
        parts.append(f"Code: {', '.join(files)}")

    if state.test_run_result:
        parts.append(
            f"Tests: {state.test_run_result.tests_passed}/{state.test_run_result.tests_run} passed"
        )

    if state.review_result:
        review_status = "approved" if state.review_result.approved else "changes requested"
        parts.append(f"Review: {review_status}")

    if state.docs_result:
        doc_files = [d.path for d in state.docs_result.files]
        parts.append(f"Docs: {', '.join(doc_files)}")

    if state.git_plan:
        parts.append(f"Git: {state.git_plan.branch_name}")

    if state.errors:
        parts.append(f"Warnings: {len(state.errors)}")

    console.print()
    console.print(Panel("\n".join(parts), title="Pipeline Complete", border_style="bright_green"))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdlc-agent",
        description="Multi-agent SDLC automation tool",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        default=True,
        help="Run all agents locally (default)",
    )
    parser.add_argument(
        "--server",
        metavar="URL",
        help="Connect to a remote SDLC server (e.g., https://api.example.com)",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch the Textual TUI instead of the Rich REPL",
    )
    parser.add_argument(
        "--workspace", "-w",
        type=Path,
        default=None,
        help="Workspace directory (default: current directory)",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip test generation and execution",
    )
    parser.add_argument(
        "--skip-docs",
        action="store_true",
        help="Skip documentation generation",
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="Skip git operations",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize a new project in the workspace (from-scratch mode)",
    )
    parser.add_argument(
        "--task", "-t",
        type=str,
        help="Run a single task non-interactively and exit",
    )
    return parser


# ---------------------------------------------------------------------------
# Session runners
# ---------------------------------------------------------------------------

async def run_session(
    workspace: Path,
    skip_tests: bool = False,
    skip_docs: bool = True,
    skip_git: bool = True,
    single_task: str | None = None,
) -> None:
    """Run one interactive session with the full SDLC pipeline."""
    settings = load_settings()

    console.print(
        Panel(
            "[bold]SDLC Agent System[/bold]  |  agents: 6 active\n"
            f"workspace: {workspace}\n"
            "Type a coding task, or 'quit' to exit.",
            border_style="bright_blue",
        )
    )

    if single_task:
        console.print(f"\n[bold green]> {single_task}[/bold green]\n")
        state = await run_pipeline(
            task=single_task,
            workspace=workspace,
            settings=settings,
            callback=RichPipelineUI(interactive=False),
            skip_tests=skip_tests,
            skip_docs=skip_docs,
            skip_git=skip_git,
        )
        _show_final_summary(state)
        return

    while True:
        console.print()
        task = console.input("[bold green]> [/]").strip()
        if not task or task.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        console.print()
        state = await run_pipeline(
            task=task,
            workspace=workspace,
            settings=settings,
            callback=RichPipelineUI(),
            skip_tests=skip_tests,
            skip_docs=skip_docs,
            skip_git=skip_git,
        )

        _show_final_summary(state)


def init_project(workspace: Path) -> None:
    """Initialize a new project scaffold in the workspace."""
    dirs = ["src", "tests", "docs"]
    for d in dirs:
        (workspace / d).mkdir(parents=True, exist_ok=True)

    readme = workspace / "README.md"
    if not readme.exists():
        readme.write_text(f"# {workspace.name}\n\nGenerated by SDLC Agent System.\n")

    gitignore = workspace / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("__pycache__/\n*.pyc\n.venv/\n.env\ndist/\n*.egg-info/\n")

    console.print(f"[green]Initialized project at {workspace}[/green]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for `sdlc-agent` CLI command."""
    parser = build_parser()
    args = parser.parse_args()

    workspace = args.workspace or Path.cwd()
    workspace = workspace.resolve()

    if args.init:
        init_project(workspace)

    if args.server:
        console.print(f"[bold]Connecting to server:[/bold] {args.server}")
        console.print("[yellow]Server mode not yet available — running locally.[/yellow]")

    if args.tui:
        try:
            from src.cli.tui import run_tui
            settings = load_settings()
            run_tui(settings=settings, workspace=workspace)
        except ImportError:
            console.print("[red]Textual is required for TUI mode: pip install textual[/red]")
            sys.exit(1)
        return

    try:
        asyncio.run(run_session(
            workspace=workspace,
            skip_tests=args.skip_tests,
            skip_docs=args.skip_docs or True,
            skip_git=args.skip_git or True,
            single_task=args.task,
        ))
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(0)


if __name__ == "__main__":
    main()
