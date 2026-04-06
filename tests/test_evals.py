import pytest

from src.agents.orchestrator import AgentMode, PipelineState, Stage
from src.core.config import Settings
from src.evals.runner import EvalCase, run_eval_case, run_eval_suite


@pytest.mark.asyncio
async def test_run_eval_case_scores_missing_requirements(monkeypatch):
    from src.agents.coding import CodingResult, GeneratedFile

    async def fake_pipeline(*args, **kwargs):
        state = PipelineState(task="x", stage=Stage.DONE)
        state.coding_result = CodingResult(
            files=[
                GeneratedFile(
                    path="app.py", content="def hello():\n    return 'hi'", explanation="app"
                )
            ],
            summary="generated",
        )
        return state

    monkeypatch.setattr("src.evals.runner.run_pipeline", fake_pipeline)
    case = EvalCase(
        name="sample",
        task="build app",
        required_files=["app.py", "tests/test_app.py"],
        required_substrings=["def hello", "pytest"],
    )
    result = await run_eval_case(case, Settings(groq_api_key="test"), agent_mode=AgentMode.LOCAL)

    assert result.passed is False
    assert "tests/test_app.py" in result.missing_files
    assert "pytest" in result.missing_substrings


@pytest.mark.asyncio
async def test_run_eval_suite_aggregates_results(monkeypatch):
    async def fake_case(case, settings, agent_mode=AgentMode.LOCAL):
        from src.evals.runner import EvalResult

        return EvalResult(name=case.name, passed=True, score=1.0)

    monkeypatch.setattr("src.evals.runner.run_eval_case", fake_case)
    results = await run_eval_suite(
        [EvalCase(name="one", task="a"), EvalCase(name="two", task="b")],
        Settings(groq_api_key="test"),
    )
    assert [item.name for item in results] == ["one", "two"]
