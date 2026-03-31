"""Textual TUI — rich terminal interface with live progress, diff view, and file list."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import (
    Footer,
    Header,
    Input,
    RichLog,
    Static,
    Tree,
)

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
from src.core.config import Settings

# ---------------------------------------------------------------------------
# Callback that feeds events into the TUI widgets
# ---------------------------------------------------------------------------

class TUIPipelineCallback(PipelineCallback):
    """Routes pipeline events to the TUI app widgets."""

    def __init__(self, app: SDLCApp) -> None:
        self._app = app

    async def on_stage_change(self, state: PipelineState) -> None:
        self._app.update_stage(state.stage)

    async def on_coding_done(self, result: CodingResult) -> None:
        log = self._app.query_one("#agent-log", RichLog)
        log.write(f"[bold yellow]Coding[/]  ✓ {len(result.files)} file(s) generated")
        log.write(f"  Summary: {result.summary}")
        self._app.show_generated_files(result)

    async def on_tests_generated(self, result: TestGenResult) -> None:
        log = self._app.query_one("#agent-log", RichLog)
        log.write(f"[bold magenta]Testing[/]  ✓ {len(result.test_files)} test file(s) generated")

    async def on_tests_run(self, result: TestRunResult) -> None:
        log = self._app.query_one("#agent-log", RichLog)
        status = "✓ passed" if result.passed else "✗ failed"
        log.write(f"[bold magenta]Testing[/]  {result.tests_passed}/{result.tests_run} {status}")
        if not result.passed:
            log.write(result.output)

    async def on_review_done(self, result: ReviewResult) -> None:
        log = self._app.query_one("#agent-log", RichLog)
        status = "✓ approved" if result.approved else "✗ changes requested"
        log.write(f"[bold blue]Review[/]  {status}")
        for issue in result.issues:
            log.write(f"  [{issue.severity.value}] {issue.file}:{issue.line} — {issue.message}")
        log.write(f"  {result.summary}")

    async def on_docs_done(self, result: DocsResult) -> None:
        log = self._app.query_one("#agent-log", RichLog)
        log.write(f"[bold green]Docs[/]  ✓ {len(result.files)} doc file(s)")

    async def on_git_plan(self, plan: GitPlan) -> None:
        log = self._app.query_one("#agent-log", RichLog)
        log.write(f"[bold red]GitOps[/]  branch: {plan.branch_name}")
        log.write(f"[bold red]GitOps[/]  commit: {plan.commit_message}")

    async def on_error(self, stage: Stage, error: str) -> None:
        log = self._app.query_one("#agent-log", RichLog)
        log.write(f"[bold red]Error[/] in {stage.value}: {error}")

    async def request_approval(self, state: PipelineState) -> bool:
        return await self._app.request_user_approval()


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

STAGE_INDICATORS = {
    Stage.PLANNING: ("⏳", "Planning..."),
    Stage.CODING: ("🔨", "Generating code..."),
    Stage.TESTING: ("🧪", "Writing tests..."),
    Stage.RUNNING_TESTS: ("🧪", "Running tests..."),
    Stage.REVIEWING: ("🔍", "Reviewing code..."),
    Stage.DOCS: ("📝", "Generating docs..."),
    Stage.GITOPS: ("🔀", "Planning git ops..."),
    Stage.DONE: ("✅", "Pipeline complete"),
    Stage.FAILED: ("❌", "Pipeline failed"),
}


class StagePanel(Static):
    """Shows the current pipeline stage with agent status indicators."""

    DEFAULT_CSS = """
    StagePanel {
        dock: top;
        height: 12;
        padding: 1 2;
        border: solid $accent;
        background: $surface;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._current = Stage.PLANNING

    def compose(self) -> ComposeResult:
        yield Static(self._render(), id="stage-content")

    def _render(self) -> str:
        lines = ["[bold]Pipeline Status[/bold]\n"]
        for stage in Stage:
            if stage == self._current:
                icon, label = STAGE_INDICATORS[stage]
                lines.append(f"  [bold cyan]► {icon} {label}[/bold cyan]")
            elif (
                stage.value < self._current.value
                if isinstance(stage.value, int)
                else list(Stage).index(stage) < list(Stage).index(self._current)
            ):
                icon, label = STAGE_INDICATORS[stage]
                lines.append(f"  [dim]  ✓ {label}[/dim]")
            else:
                _, label = STAGE_INDICATORS[stage]
                lines.append(f"  [dim]  · {label}[/dim]")
        return "\n".join(lines)

    def set_stage(self, stage: Stage) -> None:
        self._current = stage
        try:
            self.query_one("#stage-content", Static).update(self._render())
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main TUI App
# ---------------------------------------------------------------------------

class SDLCApp(App):
    """Multi-agent SDLC terminal interface."""

    TITLE = "SDLC Agent System"
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-columns: 1fr 2fr;
        grid-rows: auto 1fr auto;
    }

    #stage-panel {
        column-span: 2;
        height: 12;
        border: solid $accent;
        padding: 1 2;
    }

    #file-tree {
        border: solid $secondary;
        height: 100%;
    }

    #agent-log {
        border: solid $primary;
        height: 100%;
    }

    #diff-view {
        border: solid $success;
        height: 100%;
        display: none;
    }

    #input-bar {
        column-span: 2;
        dock: bottom;
        height: 3;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+d", "toggle_diff", "Toggle Diff"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, settings: Settings, workspace: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self._settings = settings
        self._workspace = workspace
        self._approval_event: asyncio.Event | None = None
        self._approval_result: bool = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._render_stage_panel(), id="stage-panel")
        yield Tree("Files", id="file-tree")
        yield RichLog(highlight=True, markup=True, id="agent-log")
        yield RichLog(highlight=True, markup=True, id="diff-view")
        yield Input(placeholder="Type a coding task and press Enter...", id="input-bar")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#agent-log", RichLog)
        log.write("[bold]SDLC Agent System[/bold]  |  agents: 6 active")
        log.write(f"workspace: {self._workspace}")
        log.write("Type a coding task below and press Enter.\n")
        self._refresh_file_tree()

    def _render_stage_panel(self, current: Stage | None = None) -> str:
        stages_order = list(Stage)
        current_idx = stages_order.index(current) if current else -1
        lines = ["[bold]Pipeline Status[/bold]  "]
        parts = []
        for i, stage in enumerate(stages_order):
            icon, label = STAGE_INDICATORS[stage]
            short = stage.value
            if i == current_idx:
                parts.append(f"[bold cyan]{icon} {short}[/bold cyan]")
            elif i < current_idx:
                parts.append(f"[dim green]✓ {short}[/dim green]")
            else:
                parts.append(f"[dim]· {short}[/dim]")
        lines.append("  →  ".join(parts))
        return "\n".join(lines)

    def update_stage(self, stage: Stage) -> None:
        self.query_one("#stage-panel", Static).update(self._render_stage_panel(stage))

    def show_generated_files(self, result: CodingResult) -> None:
        tree = self.query_one("#file-tree", Tree)
        tree.clear()
        tree.root.expand()
        for f in result.files:
            node = tree.root.add(f.path)
            node.data = f
        tree.root.add_leaf("[dim]Select file to view diff[/dim]")

    @on(Tree.NodeSelected)
    def on_file_selected(self, event: Tree.NodeSelected) -> None:
        if event.node.data and hasattr(event.node.data, "content"):
            diff_view = self.query_one("#diff-view", RichLog)
            diff_view.clear()
            diff_view.styles.display = "block"
            diff_view.write(f"[bold]── {event.node.data.path} ──[/bold]\n")
            diff_view.write(event.node.data.content)

    def action_toggle_diff(self) -> None:
        diff_view = self.query_one("#diff-view", RichLog)
        if diff_view.styles.display == "none":
            diff_view.styles.display = "block"
        else:
            diff_view.styles.display = "none"

    def _refresh_file_tree(self) -> None:
        tree = self.query_one("#file-tree", Tree)
        tree.clear()
        tree.root.expand()
        if self._workspace.exists():
            for item in sorted(self._workspace.iterdir()):
                if item.name.startswith(".") or item.name == "__pycache__":
                    continue
                if item.is_dir():
                    tree.root.add(f"📁 {item.name}")
                else:
                    tree.root.add_leaf(f"📄 {item.name}")

    @on(Input.Submitted, "#input-bar")
    def on_task_submitted(self, event: Input.Submitted) -> None:
        task = event.value.strip()
        if not task:
            return
        if task.lower() in ("quit", "exit", "q"):
            self.exit()
            return

        event.input.value = ""
        event.input.disabled = True
        log = self.query_one("#agent-log", RichLog)
        log.write(f"\n[bold green]> {task}[/bold green]\n")
        self.run_pipeline_task(task)

    @work(exclusive=True)
    async def run_pipeline_task(self, task: str) -> None:
        callback = TUIPipelineCallback(self)
        try:
            state = await run_pipeline(
                task=task,
                workspace=self._workspace,
                settings=self._settings,
                callback=callback,
            )
            log = self.query_one("#agent-log", RichLog)
            if state.stage == Stage.DONE:
                log.write("\n[bold green]✅ Pipeline complete![/bold green]")
            else:
                log.write(f"\n[bold red]Pipeline ended: {state.stage.value}[/bold red]")
            if state.errors:
                for err in state.errors:
                    log.write(f"  [red]⚠ {err}[/red]")
        except Exception as e:
            log = self.query_one("#agent-log", RichLog)
            log.write(f"\n[bold red]Pipeline error: {e}[/bold red]")
        finally:
            inp = self.query_one("#input-bar", Input)
            inp.disabled = False
            inp.focus()

    async def request_user_approval(self) -> bool:
        """Prompt user for approval via the TUI."""
        log = self.query_one("#agent-log", RichLog)
        log.write("\n[bold yellow]Review the generated code above.[/bold yellow]")
        log.write("[bold yellow]Type 'approve' or 'reject' in the input bar.[/bold yellow]")

        self._approval_event = asyncio.Event()
        self._approval_result = False

        inp = self.query_one("#input-bar", Input)
        inp.disabled = False
        inp.placeholder = "Type 'approve' or 'reject'..."
        inp.focus()

        # Wait for user to type approve/reject
        await self._approval_event.wait()

        inp.placeholder = "Type a coding task and press Enter..."
        return self._approval_result

    def action_cancel(self) -> None:
        if self._approval_event and not self._approval_event.is_set():
            self._approval_result = False
            self._approval_event.set()


def run_tui(settings: Settings, workspace: Path) -> None:
    """Launch the Textual TUI application."""
    app = SDLCApp(settings=settings, workspace=workspace)
    app.run()
