import pytest

from src.agents.coding import CodingResult, GeneratedFile
from src.agents.docs import DocFile, DocsResult
from src.agents.gitops import GitPlan
from src.agents.orchestrator import AgentMode, Stage, run_pipeline
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


@pytest.mark.asyncio
async def test_pipeline_distributed_mode_uses_a2a_clients(monkeypatch, tmp_path):
    settings = Settings(groq_api_key="test-key")

    class FakeA2AClient:
        def __init__(self, base_url):
            self.base_url = base_url

        async def send_payload(self, payload, output_type):
            if output_type is CodingResult:
                return CodingResult(
                    files=[
                        GeneratedFile(path="app.py", content="print('remote')", explanation="app")
                    ],
                    summary="generated remotely",
                )
            if output_type is GenResultModel:
                return GenResultModel(
                    test_files=[
                        GeneratedTest(
                            path="tests/test_app.py",
                            content="def test_ok():\n    assert True\n",
                            explanation="remote test",
                        )
                    ],
                    summary="remote tests",
                )
            if output_type is ReviewResult:
                return ReviewResult(approved=True, issues=[], summary="remote review")
            if output_type is DocsResult:
                return DocsResult(
                    files=[DocFile(path="docs/api.md", content="# api", explanation="docs")],
                    summary="remote docs",
                )
            if output_type is GitPlan:
                return GitPlan(
                    branch_name="feat/remote", commit_message="feat: remote", summary="remote"
                )
            raise AssertionError(f"Unexpected output type: {output_type}")

    async def fake_run_tests(workspace):
        return RunResultModel(
            passed=True,
            output="1 passed",
            tests_run=1,
            tests_passed=1,
            tests_failed=0,
        )

    writes = []

    def fake_write_files(workspace, files):
        writes.append([f.path for f in files])

    monkeypatch.setattr("src.agents.orchestrator.A2AClient", FakeA2AClient)
    monkeypatch.setattr("src.agents.orchestrator.run_tests", fake_run_tests)
    monkeypatch.setattr("src.agents.orchestrator.write_files", fake_write_files)

    state = await run_pipeline(
        task="build app",
        workspace=tmp_path,
        settings=settings,
        agent_mode=AgentMode.DISTRIBUTED,
        agent_urls={
            "coding": "http://coding",
            "testing": "http://testing",
            "review": "http://review",
            "docs": "http://docs",
            "gitops": "http://gitops",
        },
    )

    assert state.stage == Stage.DONE
    assert state.git_plan is not None
    assert writes


@pytest.mark.asyncio
async def test_pipeline_persists_memory_and_reuses_context(monkeypatch, tmp_path):
    settings = Settings(groq_api_key="test-key")
    prompts = []

    async def fake_coding(task, workspace, settings):
        prompts.append(task)
        return CodingResult(
            files=[GeneratedFile(path="app.py", content="print('ok')", explanation="app")],
            summary="generated app",
        )

    async def fake_testing(source_files, workspace, settings):
        return GenResultModel(
            test_files=[
                GeneratedTest(
                    path="tests/test_app.py",
                    content="def test_ok():\n    assert True\n",
                    explanation="test",
                )
            ],
            summary="tests",
        )

    async def fake_run_tests(workspace):
        return RunResultModel(
            passed=True, output="1 passed", tests_run=1, tests_passed=1, tests_failed=0
        )

    async def fake_review(source_files, settings):
        return ReviewResult(approved=True, issues=[], summary="ok")

    async def fake_docs(source_files, settings):
        return DocsResult(files=[], summary="docs")

    async def fake_gitops(change_summary, settings):
        return GitPlan(branch_name="feat/memory", commit_message="feat: memory", summary="ok")

    monkeypatch.setattr("src.agents.orchestrator.run_coding_agent", fake_coding)
    monkeypatch.setattr("src.agents.orchestrator.run_testing_agent", fake_testing)
    monkeypatch.setattr("src.agents.orchestrator.run_tests", fake_run_tests)
    monkeypatch.setattr("src.agents.orchestrator.run_review_agent", fake_review)
    monkeypatch.setattr("src.agents.orchestrator.run_docs_agent", fake_docs)
    monkeypatch.setattr("src.agents.orchestrator.run_gitops_agent", fake_gitops)

    first = await run_pipeline("Build auth service", tmp_path, settings)
    second = await run_pipeline("Improve auth login", tmp_path, settings)

    assert first.stage == Stage.DONE
    assert second.stage == Stage.DONE
    assert (tmp_path / ".sdlc" / "memory.json").exists()
    assert any("Relevant context from previous workspace runs" in prompt for prompt in prompts[1:])
