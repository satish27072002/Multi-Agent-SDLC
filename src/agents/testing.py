"""Testing agent — generates tests and runs them via subprocess."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider

from src.core.config import Settings, load_settings

# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------

class GeneratedTest(BaseModel):
    path: str = Field(description="Relative path for the test file, e.g. tests/test_auth.py")
    content: str = Field(description="Complete test file content")
    explanation: str = Field(description="What this test covers")


class TestGenResult(BaseModel):
    test_files: list[GeneratedTest] = Field(description="Generated test files")
    summary: str = Field(description="Summary of test coverage")


class TestRunResult(BaseModel):
    passed: bool
    output: str = Field(description="stdout/stderr from the test runner")
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

@dataclass
class TestingDeps:
    workspace: Path
    settings: Settings


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior test engineer. Your job is to generate comprehensive tests \
for the provided source code.

Rules:
- Use pytest as the test framework.
- Cover happy path, edge cases, and error cases.
- Use descriptive test names: test_<function>_<scenario>.
- Keep tests focused — one assertion per test when practical.
- Import from the correct module paths based on the project structure.
"""


def build_testing_agent(settings: Settings) -> Agent[TestingDeps, TestGenResult]:
    """Create and return the testing agent."""
    model = GroqModel(
        settings.testing_model,
        provider=GroqProvider(api_key=settings.groq_api_key),
    )

    agent: Agent[TestingDeps, TestGenResult] = Agent(
        model,
        deps_type=TestingDeps,
        output_type=TestGenResult,
        system_prompt=SYSTEM_PROMPT,
        retries=4,
    )

    @agent.tool
    async def read_file(ctx: RunContext[TestingDeps], file_path: str) -> str:
        """Read a source file to understand what needs testing.

        Args:
            ctx: Agent run context.
            file_path: Relative path to the file.
        """
        target = ctx.deps.workspace / file_path
        if not target.is_file():
            return f"File not found: {file_path}"
        text = target.read_text(encoding="utf-8", errors="replace")
        if len(text) > 8000:
            return text[:8000] + "\n\n... (truncated)"
        return text

    return agent


async def run_testing_agent(
    source_files: dict[str, str],
    workspace: Path,
    settings: Settings,
) -> TestGenResult:
    """Generate tests for the given source files."""
    agent = build_testing_agent(settings)
    deps = TestingDeps(workspace=workspace, settings=settings)

    prompt_parts = ["Generate pytest tests for the following source files:\n"]
    for path, content in source_files.items():
        prompt_parts.append(f"--- {path} ---\n{content}\n")

    result = await agent.run("\n".join(prompt_parts), deps=deps)
    return result.output


async def run_tests(workspace: Path) -> TestRunResult:
    """Execute pytest in the workspace and return results."""
    requirements = workspace / "requirements.txt"
    if requirements.exists():
        install_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            "requirements.txt",
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        install_stdout, _ = await asyncio.wait_for(install_proc.communicate(), timeout=120)
        install_output = install_stdout.decode(errors="replace")
        if install_proc.returncode != 0:
            return TestRunResult(
                passed=False,
                output=f"Dependency install failed:\n{install_output}",
                tests_run=0,
                tests_passed=0,
                tests_failed=0,
            )

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pytest",
        "-v",
        "--tb=short",
        cwd=str(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
    output = stdout.decode(errors="replace")

    passed = proc.returncode == 0
    # Parse counts from pytest output (e.g., "4 passed, 1 failed")
    tests_run = tests_passed = tests_failed = 0
    for line in output.splitlines():
        if "passed" in line or "failed" in line:
            import re
            nums = re.findall(r"(\d+) (passed|failed)", line)
            for count, status in nums:
                if status == "passed":
                    tests_passed = int(count)
                elif status == "failed":
                    tests_failed = int(count)
            tests_run = tests_passed + tests_failed

    return TestRunResult(
        passed=passed,
        output=output,
        tests_run=tests_run,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
    )


class TestingAgent:
    def __init__(self, settings: Settings | None = None, workspace: Path | None = None) -> None:
        self.settings = settings or load_settings()
        self.workspace = workspace or Path.cwd()

    async def run(self, prompt: str) -> TestGenResult:
        agent = build_testing_agent(self.settings)
        deps = TestingDeps(workspace=self.workspace, settings=self.settings)
        result = await agent.run(prompt, deps=deps)
        return result.output
