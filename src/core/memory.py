from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class MemoryEntry:
    task: str
    status: str
    summary: str
    created_at: float = field(default_factory=time.time)
    files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class MemorySnapshot:
    entries: list[MemoryEntry] = field(default_factory=list)


class WorkspaceMemoryStore:
    def __init__(self, workspace: Path, max_entries: int = 20) -> None:
        self._workspace = workspace
        self._max_entries = max_entries

    def load(self) -> MemorySnapshot:
        path = self._memory_path()
        if not path.is_file():
            return MemorySnapshot()
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = [MemoryEntry(**entry) for entry in raw.get("entries", [])]
        return MemorySnapshot(entries=entries)

    def add(self, entry: MemoryEntry) -> MemorySnapshot:
        snapshot = self.load()
        snapshot.entries.insert(0, entry)
        snapshot.entries = snapshot.entries[: self._max_entries]
        path = self._memory_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"entries": [asdict(item) for item in snapshot.entries]}, indent=2),
            encoding="utf-8",
        )
        return snapshot

    def build_context(self, task: str, limit: int = 3) -> str:
        snapshot = self.load()
        if not snapshot.entries:
            return ""

        task_terms = {part.lower() for part in task.split() if len(part) > 3}
        ranked = sorted(
            snapshot.entries,
            key=lambda entry: self._score(task_terms, entry),
            reverse=True,
        )
        selected = [entry for entry in ranked[:limit] if self._score(task_terms, entry) > 0]
        if not selected:
            selected = snapshot.entries[: min(limit, len(snapshot.entries))]

        lines = ["Relevant context from previous workspace runs:"]
        for entry in selected:
            lines.append(f"- Task: {entry.task}")
            lines.append(f"  Status: {entry.status}")
            lines.append(f"  Summary: {entry.summary}")
            if entry.files:
                lines.append(f"  Files: {', '.join(entry.files)}")
            if entry.errors:
                lines.append(f"  Errors: {' | '.join(entry.errors[:2])}")
        return "\n".join(lines)

    def _memory_path(self) -> Path:
        return self._workspace / ".sdlc" / "memory.json"

    @staticmethod
    def _score(task_terms: set[str], entry: MemoryEntry) -> int:
        haystack = f"{entry.task} {entry.summary}".lower()
        return sum(1 for term in task_terms if term in haystack)
