"""Orchestrator — coordinates the multi-agent SDLC workflow.

This is plain Python async logic (not an LLM agent) because:
1. Groq models can't reliably do dynamic routing via tool calls (ADK proved this).
2. The workflow is deterministic: code → test → review → (optional) docs → gitops.
3. Plain Python gives us full control over the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from src.agents.coding import CodingResult, run_coding_agent
from src.agents.docs import DocsResult, run_docs_agent
from src.agents.gitops import GitPlan, run_gitops_agent
from src.agents.review import ReviewResult, run_review_agent
from src.agents.testing import TestGenResult, TestRunResult, run_testing_agent, run_tests
from src.core.config import Settings
from src.core.memory import MemoryEntry, WorkspaceMemoryStore
from src.core.workspace import write_files
from src.protocols.a2a_client import A2AClient

# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------


class Stage(str, Enum):
    PLANNING = "planning"
    CODING = "coding"
    TESTING = "testing"
    RUNNING_TESTS = "running_tests"
    REVIEWING = "reviewing"
    DOCS = "docs"
    GITOPS = "gitops"
    DONE = "done"
    FAILED = "failed"


class AgentMode(str, Enum):
    LOCAL = "local"
    DISTRIBUTED = "distributed"


@dataclass
class PipelineState:
    """Tracks progress through the SDLC pipeline."""

    task: str
    stage: Stage = Stage.PLANNING
    coding_result: CodingResult | None = None
    test_gen_result: TestGenResult | None = None
    test_run_result: TestRunResult | None = None
    review_result: ReviewResult | None = None
    docs_result: DocsResult | None = None
    git_plan: GitPlan | None = None
    errors: list[str] = field(default_factory=list)
    memory_context: str = ""


# ---------------------------------------------------------------------------
# Callbacks for UI updates
# ---------------------------------------------------------------------------


class PipelineCallback:
    """Override these to hook into pipeline events (e.g., for TUI updates)."""

    async def on_stage_change(self, state: PipelineState) -> None:
        pass

    async def on_coding_done(self, result: CodingResult) -> None:
        pass

    async def on_tests_generated(self, result: TestGenResult) -> None:
        pass

    async def on_tests_run(self, result: TestRunResult) -> None:
        pass

    async def on_review_done(self, result: ReviewResult) -> None:
        pass

    async def on_docs_done(self, result: DocsResult) -> None:
        pass

    async def on_git_plan(self, plan: GitPlan) -> None:
        pass

    async def on_error(self, stage: Stage, error: str) -> None:
        pass

    async def request_approval(self, state: PipelineState) -> bool:
        """Return True to approve writing files. Default: auto-approve."""
        return True


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


async def run_pipeline(
    task: str,
    workspace: Path,
    settings: Settings,
    callback: PipelineCallback | None = None,
    agent_mode: AgentMode = AgentMode.LOCAL,
    agent_urls: dict[str, str] | None = None,
    skip_tests: bool = False,
    skip_docs: bool = False,
    skip_git: bool = False,
    max_iterations: int = 3,
) -> PipelineState:
    """Run the full SDLC pipeline: code → test → review → docs → git."""
    cb = callback or PipelineCallback()
    state = PipelineState(task=task)
    urls = agent_urls or _default_agent_urls(settings)
    memory_store = WorkspaceMemoryStore(workspace, max_entries=settings.memory_max_entries)
    memory_context = memory_store.build_context(task) if settings.memory_enabled else ""
    state.memory_context = memory_context

    current_task = _task_with_memory(task, memory_context)
    source_files: dict[str, str] = {}
    iteration = 0
    while iteration < max_iterations:
        iteration += 1

        state.test_gen_result = None
        state.test_run_result = None
        state.review_result = None

        state.stage = Stage.CODING
        await cb.on_stage_change(state)
        try:
            if agent_mode == AgentMode.DISTRIBUTED:
                coding_client = A2AClient(urls["coding"])
                state.coding_result = await coding_client.send_payload(
                    {
                        "task": current_task,
                        "workspace_files": _snapshot_workspace(workspace),
                    },
                    CodingResult,
                )
            else:
                state.coding_result = await run_coding_agent(current_task, workspace, settings)
            await cb.on_coding_done(state.coding_result)
        except Exception as e:
            state.errors.append(f"Coding failed: {e}")
            state.stage = Stage.FAILED
            await cb.on_error(Stage.CODING, str(e))
            return state

        approved = await cb.request_approval(state)
        if not approved:
            state.stage = Stage.FAILED
            state.errors.append("User rejected the generated code.")
            return state

        write_files(workspace, state.coding_result.files)
        source_files = {f.path: f.content for f in state.coding_result.files}

        tests_passed = True
        if not skip_tests:
            state.stage = Stage.TESTING
            await cb.on_stage_change(state)
            try:
                if agent_mode == AgentMode.DISTRIBUTED:
                    testing_client = A2AClient(urls["testing"])
                    state.test_gen_result = await testing_client.send_payload(
                        {
                            "source_files": source_files,
                            "workspace_files": _snapshot_workspace(workspace),
                        },
                        TestGenResult,
                    )
                else:
                    state.test_gen_result = await run_testing_agent(
                        source_files, workspace, settings
                    )
                await cb.on_tests_generated(state.test_gen_result)

                from src.agents.coding import GeneratedFile

                test_as_files = [
                    GeneratedFile(path=t.path, content=t.content, explanation=t.explanation)
                    for t in state.test_gen_result.test_files
                ]
                write_files(workspace, test_as_files)
            except Exception as e:
                tests_passed = False
                state.errors.append(f"Test generation failed: {e}")
                await cb.on_error(Stage.TESTING, str(e))

            state.stage = Stage.RUNNING_TESTS
            await cb.on_stage_change(state)
            try:
                state.test_run_result = await run_tests(workspace)
                await cb.on_tests_run(state.test_run_result)
                tests_passed = tests_passed and state.test_run_result.passed
            except Exception as e:
                tests_passed = False
                state.errors.append(f"Test execution failed: {e}")
                await cb.on_error(Stage.RUNNING_TESTS, str(e))

        review_passed = False
        state.stage = Stage.REVIEWING
        await cb.on_stage_change(state)
        try:
            if agent_mode == AgentMode.DISTRIBUTED:
                review_client = A2AClient(urls["review"])
                state.review_result = await review_client.send_payload(
                    {"source_files": source_files},
                    ReviewResult,
                )
            else:
                state.review_result = await run_review_agent(source_files, settings)
            await cb.on_review_done(state.review_result)
            review_passed = state.review_result.approved
        except Exception as e:
            state.errors.append(f"Review failed: {e}")
            await cb.on_error(Stage.REVIEWING, str(e))

        if tests_passed and review_passed:
            break

        if iteration >= max_iterations:
            state.stage = Stage.FAILED
            state.errors.append(
                f"Reached max feedback iterations ({max_iterations}) without passing tests/review."
            )
            return state

        feedback_parts: list[str] = [
            "Fix issues from previous attempt and regenerate updated code.",
            "Keep existing file structure and improve correctness.",
        ]
        if not tests_passed:
            if state.test_run_result and state.test_run_result.output:
                feedback_parts.append("Test failures:")
                feedback_parts.append(state.test_run_result.output)
            else:
                feedback_parts.append("Tests did not pass or could not be generated/executed.")
        if state.review_result and not state.review_result.approved:
            feedback_parts.append("Review feedback:")
            feedback_parts.append(state.review_result.summary)
            for issue in state.review_result.issues:
                feedback_parts.append(
                    f"- {issue.file}:{issue.line} [{issue.severity.value}] {issue.message}"
                )

        current_task = f"{task}\n\n" + "\n".join(feedback_parts)
        if memory_context:
            current_task = _task_with_memory(current_task, memory_context)

    if state.coding_result is None:
        state.stage = Stage.FAILED
        state.errors.append("Pipeline ended without a coding result.")
        return state

    # ── 5. Docs ───────────────────────────────────────────────────────
    if not skip_docs:
        state.stage = Stage.DOCS
        await cb.on_stage_change(state)
        try:
            if agent_mode == AgentMode.DISTRIBUTED:
                docs_client = A2AClient(urls["docs"])
                state.docs_result = await docs_client.send_payload(
                    {"source_files": source_files},
                    DocsResult,
                )
            else:
                state.docs_result = await run_docs_agent(source_files, settings)
            await cb.on_docs_done(state.docs_result)
            # Write doc files
            from src.agents.coding import GeneratedFile

            doc_as_files = [
                GeneratedFile(path=d.path, content=d.content, explanation=d.explanation)
                for d in state.docs_result.files
            ]
            write_files(workspace, doc_as_files)
        except Exception as e:
            state.errors.append(f"Docs generation failed: {e}")
            await cb.on_error(Stage.DOCS, str(e))

    # ── 6. GitOps ─────────────────────────────────────────────────────
    if not skip_git:
        state.stage = Stage.GITOPS
        await cb.on_stage_change(state)
        try:
            change_summary = state.coding_result.summary
            if agent_mode == AgentMode.DISTRIBUTED:
                gitops_client = A2AClient(urls["gitops"])
                state.git_plan = await gitops_client.send_payload(
                    {"change_summary": change_summary},
                    GitPlan,
                )
            else:
                state.git_plan = await run_gitops_agent(change_summary, settings)
            await cb.on_git_plan(state.git_plan)
        except Exception as e:
            state.errors.append(f"GitOps failed: {e}")
            await cb.on_error(Stage.GITOPS, str(e))

    state.stage = Stage.DONE
    await cb.on_stage_change(state)
    _persist_memory(settings, workspace, state)
    return state


def _default_agent_urls(settings: Settings) -> dict[str, str]:
    return {
        "coding": settings.coding_agent_url,
        "testing": settings.testing_agent_url,
        "review": settings.review_agent_url,
        "docs": settings.docs_agent_url,
        "gitops": settings.gitops_agent_url,
    }


def _snapshot_workspace(workspace: Path, limit: int = 100) -> dict[str, str]:
    if not workspace.exists():
        return {}

    snapshots: dict[str, str] = {}
    skipped = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
    for file_path in sorted(workspace.rglob("*")):
        if len(snapshots) >= limit or not file_path.is_file():
            continue
        if any(part in skipped for part in file_path.parts):
            continue
        try:
            snapshots[str(file_path.relative_to(workspace))] = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue
    return snapshots


def _task_with_memory(task: str, memory_context: str) -> str:
    if not memory_context:
        return task
    return f"{memory_context}\n\nCurrent task:\n{task}"


def _persist_memory(settings: Settings, workspace: Path, state: PipelineState) -> None:
    if not settings.memory_enabled:
        return
    summary = ""
    files: list[str] = []
    if state.coding_result:
        summary = state.coding_result.summary
        files = [item.path for item in state.coding_result.files]
    elif state.review_result:
        summary = state.review_result.summary
    elif state.docs_result:
        summary = state.docs_result.summary
    elif state.errors:
        summary = state.errors[0]
    WorkspaceMemoryStore(workspace, max_entries=settings.memory_max_entries).add(
        MemoryEntry(
            task=state.task,
            status=state.stage.value,
            summary=summary or "Pipeline completed",
            files=files,
            errors=state.errors,
        )
    )
