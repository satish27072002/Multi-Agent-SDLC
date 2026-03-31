"""Workspace utilities — write generated files to the user's project."""

from __future__ import annotations

from pathlib import Path

from src.agents.coding import GeneratedFile


def write_files(workspace: Path, files: list[GeneratedFile]) -> list[Path]:
    """Write generated files to disk. Returns list of written paths."""
    written: list[Path] = []
    for f in files:
        target = workspace / f.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.content, encoding="utf-8")
        written.append(target)
    return written
