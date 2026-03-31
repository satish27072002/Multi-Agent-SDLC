"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class RunMode(str, Enum):
    """How the system runs agents."""
    LOCAL = "local"       # All agents run in-process
    SERVER = "server"     # Agents run on a remote server (K8s)


@dataclass(frozen=True)
class Settings:
    """All settings for the multi-agent SDLC system."""

    groq_api_key: str = field(default_factory=lambda: os.environ.get("GROQ_API_KEY", ""))

    # Model assignments per agent (Groq free-tier models)
    coding_model: str = "qwen/qwen3-32b"
    orchestrator_model: str = "llama-3.1-8b-instant"
    review_model: str = "llama-3.3-70b-versatile"
    testing_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    docs_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    gitops_model: str = "llama-3.1-8b-instant"

    # Verified model IDs (from Groq API, March 2026):
    # - qwen/qwen3-32b
    # - llama-3.1-8b-instant
    # - llama-3.3-70b-versatile
    # - meta-llama/llama-4-scout-17b-16e-instruct

    # Run mode
    mode: RunMode = RunMode.SERVER

    # Server settings (for hosted/server mode)
    server_url: str = field(default_factory=lambda: os.environ.get("SDLC_SERVER_URL", "http://localhost:8080"))

    # GitHub integration
    github_token: str = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN", ""))

    # Retry settings
    max_retries: int = 3
    retry_base_delay: float = 2.0  # seconds, exponential backoff: 2s → 4s → 8s

    # Timeouts
    llm_timeout: int = 120  # seconds per LLM call

    def validate(self) -> None:
        """Raise if required settings are missing."""
        if self.mode == RunMode.LOCAL and not self.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is required for local mode. "
                "Set it in your environment or .env file.\n"
                "Get a free key at https://console.groq.com/keys"
            )


def load_settings(**overrides: str) -> Settings:
    """Load and validate settings from the environment."""
    mode_override = RunMode(overrides["mode"]) if "mode" in overrides else RunMode.SERVER
    server_override = overrides.get("server_url", os.environ.get("SDLC_SERVER_URL", "http://localhost:8080"))
    settings = Settings(mode=mode_override, server_url=server_override)
    settings.validate()
    return settings
