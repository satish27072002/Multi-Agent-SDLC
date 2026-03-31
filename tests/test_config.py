"""Tests for core.config module."""

import pytest

from src.core.config import RunMode, Settings, load_settings


class TestSettings:
    def test_default_models(self):
        s = Settings(groq_api_key="test-key")
        assert s.coding_model == "qwen/qwen3-32b"
        assert s.review_model == "llama-3.3-70b-versatile"
        assert s.testing_model == "meta-llama/llama-4-scout-17b-16e-instruct"
        assert s.docs_model == "meta-llama/llama-4-scout-17b-16e-instruct"
        assert s.orchestrator_model == "llama-3.1-8b-instant"
        assert s.gitops_model == "llama-3.1-8b-instant"

    def test_default_mode_is_server(self):
        s = Settings(groq_api_key="test-key")
        assert s.mode == RunMode.SERVER

    def test_validate_allows_empty_key_in_server_mode(self):
        s = Settings(groq_api_key="")
        s.validate()

    def test_validate_requires_groq_key_in_local_mode(self):
        s = Settings(groq_api_key="", mode=RunMode.LOCAL)
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            s.validate()

    def test_validate_passes_with_key(self):
        s = Settings(groq_api_key="test-key")
        s.validate()  # should not raise

    def test_retry_defaults(self):
        s = Settings(groq_api_key="test-key")
        assert s.max_retries == 3
        assert s.retry_base_delay == 2.0
        assert s.llm_timeout == 120

    def test_load_settings_from_env(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "env-test-key")
        s = load_settings()
        assert s.groq_api_key == "env-test-key"

    def test_load_settings_with_mode_override(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        s = load_settings(mode="local")
        assert s.mode == RunMode.LOCAL

    def test_load_settings_reads_api_token_from_env(self, monkeypatch):
        monkeypatch.setenv("SDLC_API_TOKEN", "token-123")
        s = load_settings()
        assert s.api_token == "token-123"

    def test_load_settings_reads_workspace_ttl_from_env(self, monkeypatch):
        monkeypatch.setenv("SDLC_WORKSPACE_TTL_SECONDS", "3600")
        s = load_settings()
        assert s.workspace_ttl_seconds == 3600
