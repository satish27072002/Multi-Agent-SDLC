import pytest

from src.agents.coding import CodingResult, GeneratedFile
from src.agents.docs import DocFile, DocsResult
from src.agents.gitops import GitPlan
from src.agents.orchestrator import Stage, run_pipeline
from src.agents.review import ReviewResult
from src.agents.testing import (
    GeneratedTest,
)
from src.agents.testing import (
    TestGenResult as GenResultModel,
)
from src.agents.testing import (
    TestRunResult as RunResultModel,
)
from src.core.config import Settings

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_pipeline_success_first_attempt(monkeypatch, tmp_path):
    settings = Settings(groq_api_key="test-key")

    async def fake_coding(task, workspace, cfg):
        return CodingResult(
            files=[GeneratedFile(path="app.py", content="print('ok')", explanation="app")],
            summary="generated",
        )

    async def fake_testing(source_files, workspace, cfg):
        return GenResultModel(
            test_files=[
                GeneratedTest(
                    path="tests/test_app.py",
                    content="def test_ok(): pass",
                    explanation="t",
                )
            ],
            summary="tests",
        )

    async def fake_run_tests(workspace):
        return RunResultModel(
            passed=True,
            output="1 passed",
            tests_run=1,
            tests_passed=1,
            tests_failed=0,
        )

    async def fake_review(source_files, cfg):
        return ReviewResult(approved=True, issues=[], summary="approved")

    async def fake_docs(source_files, cfg):
        return DocsResult(
            files=[DocFile(path="docs/api.md", content="# api", explanation="docs")],
            summary="ok",
        )

    async def fake_gitops(summary, cfg):
        return GitPlan(branch_name="feat/x", commit_message="feat: x", summary="x")

    monkeypatch.setattr("src.agents.orchestrator.run_coding_agent", fake_coding)
    monkeypatch.setattr("src.agents.orchestrator.run_testing_agent", fake_testing)
    monkeypatch.setattr("src.agents.orchestrator.run_tests", fake_run_tests)
    monkeypatch.setattr("src.agents.orchestrator.run_review_agent", fake_review)
    monkeypatch.setattr("src.agents.orchestrator.run_docs_agent", fake_docs)
    monkeypatch.setattr("src.agents.orchestrator.run_gitops_agent", fake_gitops)

    writes = []

    def fake_write_files(workspace, files):
        writes.append([f.path for f in files])

    monkeypatch.setattr("src.agents.orchestrator.write_files", fake_write_files)

    state = await run_pipeline(
        task="build app",
        workspace=tmp_path,
        settings=settings,
        skip_tests=False,
        skip_docs=False,
        skip_git=False,
    )

    assert state.stage == Stage.DONE
    assert state.review_result is not None and state.review_result.approved is True
    assert state.test_run_result is not None and state.test_run_result.passed is True
    assert writes


@pytest.mark.asyncio
async def test_pipeline_retries_after_failed_tests(monkeypatch, tmp_path):
    settings = Settings(groq_api_key="test-key")
    tasks_seen = []

    async def fake_coding(task, workspace, cfg):
        tasks_seen.append(task)
        return CodingResult(
            files=[GeneratedFile(path="app.py", content="x=1", explanation="app")],
            summary="generated",
        )

    async def fake_testing(source_files, workspace, cfg):
        return GenResultModel(test_files=[], summary="tests")

    calls = {"tests": 0}

    async def fake_run_tests(workspace):
        calls["tests"] += 1
        if calls["tests"] == 1:
            return RunResultModel(
                passed=False,
                output="1 failed",
                tests_run=1,
                tests_passed=0,
                tests_failed=1,
            )
        return RunResultModel(
            passed=True,
            output="1 passed",
            tests_run=1,
            tests_passed=1,
            tests_failed=0,
        )

    async def fake_review(source_files, cfg):
        return ReviewResult(approved=True, issues=[], summary="approved")

    monkeypatch.setattr("src.agents.orchestrator.run_coding_agent", fake_coding)
    monkeypatch.setattr("src.agents.orchestrator.run_testing_agent", fake_testing)
    monkeypatch.setattr("src.agents.orchestrator.run_tests", fake_run_tests)
    monkeypatch.setattr("src.agents.orchestrator.run_review_agent", fake_review)
    monkeypatch.setattr("src.agents.orchestrator.write_files", lambda workspace, files: None)

    state = await run_pipeline(
        task="build app",
        workspace=tmp_path,
        settings=settings,
        skip_docs=True,
        skip_git=True,
        max_iterations=3,
    )

    assert state.stage == Stage.DONE
    assert len(tasks_seen) == 2
    assert "Fix issues from previous attempt" in tasks_seen[1]


@pytest.mark.asyncio
async def test_pipeline_fails_after_max_iterations(monkeypatch, tmp_path):
    settings = Settings(groq_api_key="test-key")

    async def fake_coding(task, workspace, cfg):
        return CodingResult(
            files=[GeneratedFile(path="app.py", content="x=1", explanation="app")],
            summary="generated",
        )

    async def fake_testing(source_files, workspace, cfg):
        return GenResultModel(test_files=[], summary="tests")

    async def fake_run_tests(workspace):
        return RunResultModel(
            passed=False,
            output="still failing",
            tests_run=1,
            tests_passed=0,
            tests_failed=1,
        )

    async def fake_review(source_files, cfg):
        return ReviewResult(approved=False, issues=[], summary="not approved")

    monkeypatch.setattr("src.agents.orchestrator.run_coding_agent", fake_coding)
    monkeypatch.setattr("src.agents.orchestrator.run_testing_agent", fake_testing)
    monkeypatch.setattr("src.agents.orchestrator.run_tests", fake_run_tests)
    monkeypatch.setattr("src.agents.orchestrator.run_review_agent", fake_review)
    monkeypatch.setattr("src.agents.orchestrator.write_files", lambda workspace, files: None)

    state = await run_pipeline(
        task="build app",
        workspace=tmp_path,
        settings=settings,
        skip_docs=True,
        skip_git=True,
        max_iterations=2,
    )

    assert state.stage == Stage.FAILED
    assert any("max feedback iterations" in e for e in state.errors)
