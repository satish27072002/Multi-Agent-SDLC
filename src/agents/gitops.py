"""GitOps agent — handles git commits and branch management."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider

from src.core.config import Settings, load_settings

# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------

class GitPlan(BaseModel):
    branch_name: str = Field(description="Git branch name, e.g. feat/add-auth")
    commit_message: str = Field(description="Conventional commit message")
    summary: str = Field(description="What this commit does")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a Git operations specialist. Given a description of code changes, \
produce a git branch name and commit message.

Rules:
- Use conventional commits: feat:, fix:, refactor:, test:, docs:
- Branch names: type/short-description (lowercase, hyphens)
- Commit messages: imperative mood, under 72 chars for the first line
- Add a body paragraph if the changes are non-trivial
"""


def build_gitops_agent(settings: Settings) -> Agent[None, GitPlan]:
    """Create and return the gitops agent."""
    model = GroqModel(
        settings.gitops_model,
        provider=GroqProvider(api_key=settings.groq_api_key),
    )
    return Agent(
        model,
        output_type=GitPlan,
        system_prompt=SYSTEM_PROMPT,
        retries=2,
    )


async def run_gitops_agent(change_summary: str, settings: Settings) -> GitPlan:
    """Generate a git plan for the given changes."""
    agent = build_gitops_agent(settings)
    prompt = "Generate a git branch name and commit message for:\n"
    result = await agent.run(prompt + change_summary)
    return result.output


# ---------------------------------------------------------------------------
# Git operations (subprocess)
# ---------------------------------------------------------------------------

async def _run_git(workspace: Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    return stdout.decode(errors="replace").strip()


async def git_commit(workspace: Path, plan: GitPlan, files: list[str]) -> str:
    """Create a branch, stage files, and commit."""
    await _run_git(workspace, "checkout", "-b", plan.branch_name)
    for f in files:
        await _run_git(workspace, "add", f)
    await _run_git(workspace, "commit", "-m", plan.commit_message)
    return f"Committed on branch '{plan.branch_name}': {plan.commit_message}"


class GitOpsAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    async def run(self, prompt: str) -> GitPlan:
        agent = build_gitops_agent(self.settings)
        result = await agent.run(prompt)
        return result.output
