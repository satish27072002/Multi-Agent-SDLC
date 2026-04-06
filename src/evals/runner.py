from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.agents.orchestrator import AgentMode, run_pipeline
from src.core.config import Settings, load_settings


@dataclass
class EvalCase:
    name: str
    task: str
    required_files: list[str] = field(default_factory=list)
    required_substrings: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    name: str
    passed: bool
    score: float
    missing_files: list[str] = field(default_factory=list)
    missing_substrings: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


async def run_eval_case(
    case: EvalCase,
    settings: Settings,
    agent_mode: AgentMode = AgentMode.LOCAL,
) -> EvalResult:
    with tempfile.TemporaryDirectory(prefix=f"eval-{case.name}-") as temp_dir:
        workspace = Path(temp_dir)
        state = await run_pipeline(
            task=case.task,
            workspace=workspace,
            settings=settings,
            agent_mode=agent_mode,
            skip_docs=True,
            skip_git=True,
        )
        generated_files = [item.path for item in state.coding_result.files] if state.coding_result else []
        missing_files = [path for path in case.required_files if path not in generated_files]
        combined_content = "\n".join(
            item.content for item in (state.coding_result.files if state.coding_result else [])
        )
        missing_substrings = [text for text in case.required_substrings if text not in combined_content]
        denominator = max(1, len(case.required_files) + len(case.required_substrings))
        penalties = len(missing_files) + len(missing_substrings)
        score = max(0.0, 1.0 - (penalties / denominator))
        passed = state.stage.value == "done" and not missing_files and not missing_substrings
        return EvalResult(
            name=case.name,
            passed=passed,
            score=score,
            missing_files=missing_files,
            missing_substrings=missing_substrings,
            generated_files=generated_files,
            errors=state.errors,
        )


async def run_eval_suite(cases: list[EvalCase], settings: Settings) -> list[EvalResult]:
    results: list[EvalResult] = []
    for case in cases:
        results.append(await run_eval_case(case, settings))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(prog="sdlc-evals", description="Run SDLC eval cases")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    from src.evals.datasets import DEFAULT_EVAL_CASES

    settings = load_settings(mode="local")
    results = asyncio.run(run_eval_suite(DEFAULT_EVAL_CASES, settings))
    payload = [asdict(result) for result in results]
    rendered = json.dumps(payload, indent=2)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
