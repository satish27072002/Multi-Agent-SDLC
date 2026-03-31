"""Tests for core.retry module."""

import asyncio

import pytest

from src.core.retry import LLMRetryError, retry_llm_call


class TestRetryLLMCall:
    def test_success_on_first_try(self):
        async def succeeds():
            return "ok"

        result = asyncio.run(retry_llm_call(succeeds, max_retries=3, base_delay=0.01))
        assert result == "ok"

    def test_success_after_retries(self):
        attempt = 0

        async def fails_then_succeeds():
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise RuntimeError("temporary failure")
            return "recovered"

        result = asyncio.run(retry_llm_call(
            fails_then_succeeds, max_retries=3, base_delay=0.01, agent_name="test"
        ))
        assert result == "recovered"
        assert attempt == 3

    def test_all_retries_exhausted(self):
        async def always_fails():
            raise RuntimeError("permanent failure")

        with pytest.raises(LLMRetryError) as exc_info:
            asyncio.run(retry_llm_call(
                always_fails, max_retries=3, base_delay=0.01, agent_name="test"
            ))
        assert exc_info.value.attempts == 3
        assert "permanent failure" in str(exc_info.value.original_error)

    def test_timeout_triggers_retry(self):
        attempt = 0

        async def slow_then_fast():
            nonlocal attempt
            attempt += 1
            if attempt < 2:
                await asyncio.sleep(10)  # will timeout
            return "fast"

        result = asyncio.run(retry_llm_call(
            slow_then_fast, max_retries=3, base_delay=0.01, timeout=0.1, agent_name="test"
        ))
        assert result == "fast"
        assert attempt == 2
