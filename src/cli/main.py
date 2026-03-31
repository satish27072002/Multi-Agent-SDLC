"""CLI entry point — interactive prompt loop with Rich UI or Textual TUI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
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
        default=False,
        help="Run all agents locally (fallback mode)",
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
    settings=None,
    skip_tests: bool = False,
    skip_docs: bool = True,
    skip_git: bool = True,
    single_task: str | None = None,
) -> None:
    """Run one interactive session with the full SDLC pipeline."""
    settings = settings or load_settings(mode="local")

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
        try:
            task = console.input("[bold green]> [/]").strip()
        except EOFError:
            console.print("[dim]Goodbye.[/dim]")
            break
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


async def run_server_session(
    workspace: Path,
    settings,
    skip_tests: bool = False,
    skip_docs: bool = True,
    skip_git: bool = True,
    single_task: str | None = None,
) -> None:
    base_url = settings.server_url.rstrip("/")

    console.print(
        Panel(
            "[bold]SDLC Agent System[/bold]  |  mode: hosted server\n"
            f"server: {base_url}\n"
            f"workspace: {workspace}\n"
            "Type a coding task, or 'quit' to exit.",
            border_style="bright_blue",
        )
    )

    async def _run_remote_task(task: str) -> None:
        payload = {
            "task": task,
            "workspace": str(workspace),
            "skip_tests": skip_tests,
            "skip_docs": skip_docs,
            "skip_git": skip_git,
            "auto_approve": True,
        }
        timeout = httpx.Timeout(30.0, connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            create_resp = await client.post(f"{base_url}/tasks", json=payload)
            create_resp.raise_for_status()
            created = create_resp.json()
            task_id = created["task_id"]
            console.print(f"  [bold cyan]Server[/]       submitted task [cyan]{task_id}[/]")

            last_stage = ""
            while True:
                status_resp = await client.get(f"{base_url}/tasks/{task_id}")
                status_resp.raise_for_status()
                status = status_resp.json()

                stage = status.get("current_stage") or "unknown"
                if stage != last_stage:
                    console.print(f"  [bold cyan]Server[/]       stage: {stage}")
                    last_stage = stage

                state = status.get("status", "").lower()
                if state in {"completed", "failed"}:
                    if state == "completed":
                        console.print("  [bold green]Server[/]       task completed")
                    else:
                        errors = status.get("errors") or []
                        message = "\n".join(errors) if errors else "task failed"
                        console.print(Panel(message, title="Server Error", border_style="red"))

                    result = status.get("result") or {}
                    pretty = json.dumps(result, indent=2) if result else "{}"
                    console.print(Panel(pretty, title="Server Result", border_style="green"))
                    return

                await asyncio.sleep(1.0)

    if single_task:
        console.print(f"\n[bold green]> {single_task}[/bold green]\n")
        await _run_remote_task(single_task)
        return

    while True:
        console.print()
        try:
            task = console.input("[bold green]> [/]").strip()
        except EOFError:
            console.print("[dim]Goodbye.[/dim]")
            break
        if not task or task.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        console.print()
        await _run_remote_task(task)


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

    server_url_override = args.server if args.server else None
    requested_mode = "local" if args.local else "server"

    load_kwargs = {"mode": requested_mode}
    if server_url_override:
        load_kwargs["server_url"] = server_url_override

    try:
        settings = load_settings(**load_kwargs)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)

    if args.tui:
        try:
            from src.cli.tui import run_tui
            settings = load_settings(mode="local")
            run_tui(settings=settings, workspace=workspace)
        except ImportError:
            console.print("[red]Textual is required for TUI mode: pip install textual[/red]")
            sys.exit(1)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            sys.exit(1)
        return

    try:
        if settings.mode.value == "server":
            try:
                asyncio.run(run_server_session(
                    workspace=workspace,
                    settings=settings,
                    skip_tests=args.skip_tests,
                    skip_docs=args.skip_docs,
                    skip_git=args.skip_git,
                    single_task=args.task,
                ))
            except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as exc:
                console.print(
                    f"[yellow]Server unavailable ({exc}). Falling back to local mode.[/yellow]"
                )
                local_settings = load_settings(mode="local", server_url=settings.server_url)
                asyncio.run(run_session(
                    workspace=workspace,
                    settings=local_settings,
                    skip_tests=args.skip_tests,
                    skip_docs=args.skip_docs,
                    skip_git=args.skip_git,
                    single_task=args.task,
                ))
        else:
            asyncio.run(run_session(
                workspace=workspace,
                settings=settings,
                skip_tests=args.skip_tests,
                skip_docs=args.skip_docs,
                skip_git=args.skip_git,
                single_task=args.task,
            ))
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(0)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
