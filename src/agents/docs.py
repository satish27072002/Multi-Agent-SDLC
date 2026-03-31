"""Docs agent — generates documentation for code."""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider

from src.core.config import Settings, load_settings

# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------

class DocFile(BaseModel):
    path: str = Field(description="Relative path for the doc file, e.g. docs/API.md")
    content: str = Field(description="Complete file content (Markdown)")
    explanation: str = Field(description="What this doc covers")


class DocsResult(BaseModel):
    files: list[DocFile] = Field(description="Generated documentation files")
    summary: str = Field(description="Summary of documentation generated")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a technical writer. Generate clear, useful documentation for the \
provided source code.

Rules:
- Write in Markdown.
- Include: purpose, usage examples, API reference, and setup instructions.
- Be concise — developers read docs to solve problems, not for prose.
- If the code has a CLI, document the commands and flags.
- If it has an API, document the endpoints with request/response examples.
"""


def build_docs_agent(settings: Settings) -> Agent[None, DocsResult]:
    """Create and return the docs agent."""
    model = GroqModel(
        settings.docs_model,
        provider=GroqProvider(api_key=settings.groq_api_key),
    )
    return Agent(
        model,
        output_type=DocsResult,
        system_prompt=SYSTEM_PROMPT,
        retries=2,
    )


async def run_docs_agent(source_files: dict[str, str], settings: Settings) -> DocsResult:
    """Generate documentation for the given source files."""
    agent = build_docs_agent(settings)
    prompt_parts = ["Generate documentation for the following source files:\n"]
    for path, content in source_files.items():
        prompt_parts.append(f"--- {path} ---\n{content}\n")
    result = await agent.run("\n".join(prompt_parts))
    return result.output


class DocsAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    async def run(self, prompt: str) -> DocsResult:
        agent = build_docs_agent(self.settings)
        result = await agent.run(prompt)
        return result.output
