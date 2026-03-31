"""Coding agent — generates and modifies code via Groq LLMs."""

from __future__ import annotations

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

class GeneratedFile(BaseModel):
    """A single file produced by the coding agent."""

    path: str = Field(description="Relative file path, e.g. src/auth/middleware.py")
    content: str = Field(description="Complete file content")
    explanation: str = Field(description="Brief explanation of what this file does")


class CodingResult(BaseModel):
    """Structured output from the coding agent."""

    files: list[GeneratedFile] = Field(description="List of files to create or modify")
    summary: str = Field(description="One-paragraph summary of all changes")


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

@dataclass
class CodingDeps:
    """Runtime context for the coding agent."""

    workspace: Path  # root of the user's project
    settings: Settings


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior software engineer. Your job is to generate clean, \
production-quality code based on the user's task description.

Rules:
- Return ALL files needed to complete the task.
- Use clear names, type hints, and docstrings.
- Follow the conventions of the target language/framework.
- Never generate placeholder or TODO comments — write real code.
- Keep files focused: one responsibility per file.
"""


def build_coding_agent(settings: Settings) -> Agent[CodingDeps, CodingResult]:
    """Create and return the coding agent."""
    model = GroqModel(
        settings.coding_model,
        provider=GroqProvider(api_key=settings.groq_api_key),
    )

    agent: Agent[CodingDeps, CodingResult] = Agent(
        model,
        deps_type=CodingDeps,
        output_type=CodingResult,
        system_prompt=SYSTEM_PROMPT,
        retries=2,
    )

    # -- Tools ---------------------------------------------------------------

    @agent.tool
    async def list_files(ctx: RunContext[CodingDeps], directory: str = ".") -> str:
        """List files in a directory of the user's project.

        Args:
            ctx: Agent run context.
            directory: Relative path inside the workspace to list.
        """
        target = ctx.deps.workspace / directory
        if not target.exists():
            return f"Directory does not exist: {directory}"
        entries = sorted(target.iterdir())
        lines = []
        for entry in entries[:50]:  # cap to avoid huge outputs
            prefix = "d " if entry.is_dir() else "f "
            lines.append(prefix + str(entry.relative_to(ctx.deps.workspace)))
        return "\n".join(lines) if lines else "(empty directory)"

    @agent.tool
    async def read_file(ctx: RunContext[CodingDeps], file_path: str) -> str:
        """Read the contents of a file in the user's project.

        Args:
            ctx: Agent run context.
            file_path: Relative path to the file inside the workspace.
        """
        target = ctx.deps.workspace / file_path
        if not target.is_file():
            return f"File not found: {file_path}"
        text = target.read_text(encoding="utf-8", errors="replace")
        # Truncate large files so we don't blow the context window
        if len(text) > 8000:
            return text[:8000] + "\n\n... (truncated)"
        return text

    return agent


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

async def run_coding_agent(
    task: str,
    workspace: Path,
    settings: Settings,
) -> CodingResult:
    """Run the coding agent on a task and return structured output."""
    agent = build_coding_agent(settings)
    deps = CodingDeps(workspace=workspace, settings=settings)
    result = await agent.run(task, deps=deps)
    return result.output


class CodingAgent:
    def __init__(self, settings: Settings | None = None, workspace: Path | None = None) -> None:
        self.settings = settings or load_settings()
        self.workspace = workspace or Path.cwd()

    async def run(self, task: str) -> CodingResult:
        return await run_coding_agent(task=task, workspace=self.workspace, settings=self.settings)
