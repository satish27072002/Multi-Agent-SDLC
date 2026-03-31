"""Review agent — checks code quality, style, and correctness."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider

from src.core.config import Settings, load_settings

# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ReviewIssue(BaseModel):
    file: str = Field(description="File path where the issue was found")
    line: str = Field(description="Approximate line or range, e.g. '15' or '15-20'")
    severity: Severity
    message: str = Field(description="Description of the issue")
    suggestion: str = Field(description="How to fix it")


class ReviewResult(BaseModel):
    approved: bool = Field(description="True if the code passes review")
    issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="Issues found during review",
    )
    summary: str = Field(description="Overall assessment of code quality")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior code reviewer. You receive code files and review them for:

1. **Correctness** — logic errors, off-by-one, missing error handling
2. **Style** — naming, formatting, idiomatic patterns
3. **Security** — injection, hardcoded secrets, unsafe operations
4. **Maintainability** — complexity, duplication, unclear intent

Rules:
- Be constructive, not pedantic. Only flag issues that matter.
- If the code is good, approve it. Don't invent problems.
- Set approved=true if there are zero errors (warnings/info are OK).
"""


def build_review_agent(settings: Settings) -> Agent[None, ReviewResult]:
    """Create and return the review agent."""
    model = GroqModel(
        settings.review_model,
        provider=GroqProvider(api_key=settings.groq_api_key),
    )
    return Agent(
        model,
        output_type=ReviewResult,
        system_prompt=SYSTEM_PROMPT,
        retries=2,
    )


async def run_review_agent(code_files: dict[str, str], settings: Settings) -> ReviewResult:
    """Review a set of code files.

    Args:
        code_files: Mapping of file path to file content.
        settings: Application settings.
    """
    agent = build_review_agent(settings)
    prompt_parts = ["Review the following code files:\n"]
    for path, content in code_files.items():
        prompt_parts.append(f"--- {path} ---\n{content}\n")
    result = await agent.run("\n".join(prompt_parts))
    return result.output


class ReviewAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    async def run(self, prompt: str) -> ReviewResult:
        agent = build_review_agent(self.settings)
        result = await agent.run(prompt)
        return result.output
