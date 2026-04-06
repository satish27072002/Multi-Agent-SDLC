from __future__ import annotations

import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import uvicorn
from pydantic import BaseModel

from src.agents.coding import CodingResult, run_coding_agent
from src.agents.docs import DocsResult, run_docs_agent
from src.agents.gitops import GitPlan, run_gitops_agent
from src.agents.review import ReviewResult, run_review_agent
from src.agents.testing import TestGenResult, run_testing_agent
from src.core.config import Settings, load_settings
from src.protocols.a2a_server import create_a2a_app

Handler = Callable[[dict[str, Any], Settings], Awaitable[BaseModel]]


def _safe_relative_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsupported workspace file path: {raw_path}")
    return path


def _materialize_files(root: Path, files: dict[str, str]) -> None:
    for file_path, content in files.items():
        target = root / _safe_relative_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


async def _run_coding(payload: dict[str, Any], settings: Settings) -> CodingResult:
    task = str(payload.get("task", "")).strip()
    if not task:
        raise ValueError("Coding payload requires 'task'")

    workspace_files = payload.get("workspace_files") or {}
    with tempfile.TemporaryDirectory(prefix="coding-agent-") as temp_dir:
        workspace = Path(temp_dir)
        _materialize_files(workspace, workspace_files)
        return await run_coding_agent(task=task, workspace=workspace, settings=settings)


async def _run_testing(payload: dict[str, Any], settings: Settings) -> TestGenResult:
    source_files = payload.get("source_files") or {}
    if not isinstance(source_files, dict) or not source_files:
        raise ValueError("Testing payload requires non-empty 'source_files'")

    workspace_files = dict(payload.get("workspace_files") or {})
    workspace_files.update({str(path): str(content) for path, content in source_files.items()})
    with tempfile.TemporaryDirectory(prefix="testing-agent-") as temp_dir:
        workspace = Path(temp_dir)
        _materialize_files(workspace, workspace_files)
        return await run_testing_agent(
            source_files={str(path): str(content) for path, content in source_files.items()},
            workspace=workspace,
            settings=settings,
        )


async def _run_review(payload: dict[str, Any], settings: Settings) -> ReviewResult:
    source_files = payload.get("source_files") or {}
    if not isinstance(source_files, dict) or not source_files:
        raise ValueError("Review payload requires non-empty 'source_files'")
    normalized = {str(path): str(content) for path, content in source_files.items()}
    return await run_review_agent(normalized, settings)


async def _run_docs(payload: dict[str, Any], settings: Settings) -> DocsResult:
    source_files = payload.get("source_files") or {}
    if not isinstance(source_files, dict) or not source_files:
        raise ValueError("Docs payload requires non-empty 'source_files'")
    normalized = {str(path): str(content) for path, content in source_files.items()}
    return await run_docs_agent(normalized, settings)


async def _run_gitops(payload: dict[str, Any], settings: Settings) -> GitPlan:
    change_summary = str(payload.get("change_summary", "")).strip()
    if not change_summary:
        raise ValueError("GitOps payload requires 'change_summary'")
    return await run_gitops_agent(change_summary, settings)


AGENT_HANDLERS: dict[str, tuple[str, Handler]] = {
    "coding": ("Generates and updates project code", _run_coding),
    "testing": ("Generates pytest coverage for proposed code", _run_testing),
    "review": ("Reviews generated code quality and safety", _run_review),
    "docs": ("Produces documentation for generated code", _run_docs),
    "gitops": ("Creates branch and commit recommendations", _run_gitops),
}


def main() -> None:
    agent_name = os.environ.get("AGENT_NAME", "coding")
    agent_port = int(os.environ.get("AGENT_PORT", "9001"))
    if agent_name not in AGENT_HANDLERS:
        valid = ", ".join(sorted(AGENT_HANDLERS))
        raise ValueError(f"Unsupported AGENT_NAME '{agent_name}'. Expected one of: {valid}")

    description, handler = AGENT_HANDLERS[agent_name]
    settings = load_settings(mode="local")

    async def run_payload(payload: dict[str, Any]) -> BaseModel:
        return await handler(payload, settings)

    app = create_a2a_app(
        agent_name=agent_name,
        description=description,
        handler=run_payload,
        port=agent_port,
    )
    uvicorn.run(app, host="0.0.0.0", port=agent_port)


if __name__ == "__main__":
    main()
