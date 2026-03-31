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
from src.core.workspace import write_files

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
    skip_tests: bool = False,
    skip_docs: bool = False,
    skip_git: bool = False,
) -> PipelineState:
    """Run the full SDLC pipeline: code → test → review → docs → git."""
    cb = callback or PipelineCallback()
    state = PipelineState(task=task)

    # ── 1. Coding ──────────────────────────────────────────────────────
    state.stage = Stage.CODING
    await cb.on_stage_change(state)
    try:
        state.coding_result = await run_coding_agent(task, workspace, settings)
        await cb.on_coding_done(state.coding_result)
    except Exception as e:
        state.errors.append(f"Coding failed: {e}")
        state.stage = Stage.FAILED
        await cb.on_error(Stage.CODING, str(e))
        return state

    # ── Approval gate ──────────────────────────────────────────────────
    approved = await cb.request_approval(state)
    if not approved:
        state.stage = Stage.FAILED
        state.errors.append("User rejected the generated code.")
        return state

    # Write code files to disk
    write_files(workspace, state.coding_result.files)

    # Build a dict of generated source files for downstream agents
    source_files = {f.path: f.content for f in state.coding_result.files}

    # ── 2. Testing (generate) ─────────────────────────────────────────
    if not skip_tests:
        state.stage = Stage.TESTING
        await cb.on_stage_change(state)
        try:
            state.test_gen_result = await run_testing_agent(source_files, workspace, settings)
            await cb.on_tests_generated(state.test_gen_result)

            # Write test files to disk
            from src.agents.coding import GeneratedFile
            test_as_files = [
                GeneratedFile(path=t.path, content=t.content, explanation=t.explanation)
                for t in state.test_gen_result.test_files
            ]
            write_files(workspace, test_as_files)
        except Exception as e:
            state.errors.append(f"Test generation failed: {e}")
            await cb.on_error(Stage.TESTING, str(e))

        # ── 3. Run tests ──────────────────────────────────────────────
        state.stage = Stage.RUNNING_TESTS
        await cb.on_stage_change(state)
        try:
            state.test_run_result = await run_tests(workspace)
            await cb.on_tests_run(state.test_run_result)
        except Exception as e:
            state.errors.append(f"Test execution failed: {e}")
            await cb.on_error(Stage.RUNNING_TESTS, str(e))

    # ── 4. Review ─────────────────────────────────────────────────────
    state.stage = Stage.REVIEWING
    await cb.on_stage_change(state)
    try:
        state.review_result = await run_review_agent(source_files, settings)
        await cb.on_review_done(state.review_result)
    except Exception as e:
        state.errors.append(f"Review failed: {e}")
        await cb.on_error(Stage.REVIEWING, str(e))

    # ── 5. Docs ───────────────────────────────────────────────────────
    if not skip_docs:
        state.stage = Stage.DOCS
        await cb.on_stage_change(state)
        try:
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
            state.git_plan = await run_gitops_agent(change_summary, settings)
            await cb.on_git_plan(state.git_plan)
        except Exception as e:
            state.errors.append(f"GitOps failed: {e}")
            await cb.on_error(Stage.GITOPS, str(e))

    state.stage = Stage.DONE
    await cb.on_stage_change(state)
    return state
