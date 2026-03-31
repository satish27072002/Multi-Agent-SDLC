"""Retry logic — exponential backoff for LLM calls and external services."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class LLMRetryError(Exception):
    """Raised when all retries for an LLM call are exhausted."""

    def __init__(self, original_error: Exception, attempts: int) -> None:
        self.original_error = original_error
        self.attempts = attempts
        super().__init__(f"LLM call failed after {attempts} attempts: {original_error}")


FALLBACK_RESPONSES = {
    "coding": (
        "I'm unable to generate code right now due to a temporary API issue. "
        "Please try again in a moment."
    ),
    "testing": "Test generation is temporarily unavailable. Please try again shortly.",
    "review": "Code review is temporarily unavailable. Please try again shortly.",
    "docs": "Documentation generation is temporarily unavailable. Please try again shortly.",
    "gitops": "Git planning is temporarily unavailable. Please try again shortly.",
}


async def retry_llm_call(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 2.0,
    timeout: float = 120.0,
    agent_name: str = "unknown",
    **kwargs: Any,
) -> Any:
    """Execute an async function with exponential backoff retry.

    Args:
        func: Async function to call.
        max_retries: Maximum number of attempts.
        base_delay: Base delay in seconds (doubles each retry).
        timeout: Timeout per attempt in seconds.
        agent_name: Name for logging.

    Returns:
        The function's return value.

    Raises:
        LLMRetryError: If all retries are exhausted.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=timeout,
            )
            if attempt > 1:
                logger.info(f"[{agent_name}] Succeeded on attempt {attempt}")
            return result
        except asyncio.TimeoutError:
            last_error = TimeoutError(f"LLM call timed out after {timeout}s")
            logger.warning(f"[{agent_name}] Attempt {attempt}/{max_retries} timed out")
        except Exception as e:
            last_error = e
            logger.warning(f"[{agent_name}] Attempt {attempt}/{max_retries} failed: {e}")

        if attempt < max_retries:
            delay = base_delay * (2 ** (attempt - 1))
            logger.info(f"[{agent_name}] Retrying in {delay:.1f}s...")
            await asyncio.sleep(delay)

    if last_error is None:
        last_error = RuntimeError("Unknown retry failure")
    raise LLMRetryError(last_error, max_retries)
