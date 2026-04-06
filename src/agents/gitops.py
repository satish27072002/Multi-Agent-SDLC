"""GitOps agent — handles git commits and branch management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider

from src.core.config import Settings, load_settings
from src.protocols.mcp_client import GitHubMCPClient

# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------


class GitPlan(BaseModel):
    branch_name: str = Field(description="Git branch name, e.g. feat/add-auth")
    commit_message: str = Field(description="Conventional commit message")
    summary: str = Field(description="What this commit does")


@dataclass
class GitOpsDeps:
    settings: Settings


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


async def create_pull_request_via_mcp(
    settings: Settings,
    repo: str,
    title: str,
    body: str,
    branch: str,
    base: str = "main",
) -> str:
    github = GitHubMCPClient(github_token=settings.github_token)
    await github.connect()
    try:
        result = await github.create_pull_request(
            repo=repo,
            title=title,
            body=body,
            head=branch,
            base=base,
        )
        return result.content
    finally:
        await github.disconnect()


async def list_open_issues_via_mcp(settings: Settings, repo: str) -> str:
    github = GitHubMCPClient(github_token=settings.github_token)
    await github.connect()
    try:
        result = await github.list_issues(repo=repo, state="open")
        return result.content
    finally:
        await github.disconnect()


def build_gitops_agent(settings: Settings) -> Agent[GitOpsDeps, GitPlan]:
    """Create and return the gitops agent."""
    model = GroqModel(
        settings.gitops_model,
        provider=GroqProvider(api_key=settings.groq_api_key),
    )
    agent: Agent[GitOpsDeps, GitPlan] = Agent(
        model,
        deps_type=GitOpsDeps,
        output_type=GitPlan,
        system_prompt=SYSTEM_PROMPT,
        retries=2,
    )

    @agent.tool
    async def create_pull_request(
        ctx: RunContext[GitOpsDeps],
        repo: str,
        title: str,
        body: str,
        branch: str,
        base: str = "main",
    ) -> str:
        return await create_pull_request_via_mcp(
            settings=ctx.deps.settings,
            repo=repo,
            title=title,
            body=body,
            branch=branch,
            base=base,
        )

    @agent.tool
    async def list_open_issues(ctx: RunContext[GitOpsDeps], repo: str) -> str:
        return await list_open_issues_via_mcp(ctx.deps.settings, repo)

    return agent


async def run_gitops_agent(change_summary: str, settings: Settings) -> GitPlan:
    """Generate a git plan for the given changes."""
    agent = build_gitops_agent(settings)
    prompt = "Generate a git branch name and commit message for:\n"
    result = await agent.run(prompt + change_summary, deps=GitOpsDeps(settings=settings))
    return result.output


# ---------------------------------------------------------------------------
# Git operations (subprocess)
# ---------------------------------------------------------------------------


async def _run_git(workspace: Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
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
        result = await agent.run(prompt, deps=GitOpsDeps(settings=self.settings))
        return result.output

    async def create_pull_request(
        self,
        repo: str,
        title: str,
        body: str,
        branch: str,
        base: str = "main",
    ) -> str:
        return await create_pull_request_via_mcp(self.settings, repo, title, body, branch, base)
