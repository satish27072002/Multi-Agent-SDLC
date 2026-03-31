"""Task state management — tracks pipeline tasks across sessions.

Supports both in-memory storage (local mode) and Redis (server mode).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskRecord:
    """Represents a single pipeline task execution."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task: str = ""
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    current_stage: str = "planning"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "errors": self.errors,
            "current_stage": self.current_stage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskRecord:
        return cls(
            id=data["id"],
            task=data["task"],
            status=TaskStatus(data["status"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            result=data.get("result", {}),
            errors=data.get("errors", []),
            current_stage=data.get("current_stage", "planning"),
        )


class TaskStore:
    """In-memory task store. Swap with RedisTaskStore for server mode."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def create(self, task_text: str) -> TaskRecord:
        record = TaskRecord(task=task_text)
        self._tasks[record.id] = record
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs: Any) -> TaskRecord | None:
        record = self._tasks.get(task_id)
        if not record:
            return None
        for key, value in kwargs.items():
            if hasattr(record, key):
                object.__setattr__(record, key, value)
        record.updated_at = time.time()
        return record

    def list_tasks(self, limit: int = 50) -> list[TaskRecord]:
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]

    def delete(self, task_id: str) -> bool:
        return self._tasks.pop(task_id, None) is not None


class RedisTaskStore(TaskStore):
    """Redis-backed task store for server/K8s mode."""

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        super().__init__()
        self._redis_url = redis_url
        self._redis: Any = None

    async def connect(self) -> None:
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url)
        except ImportError:
            pass  # Fall back to in-memory

    def create(self, task_text: str) -> TaskRecord:
        record = super().create(task_text)
        if self._redis:
            import asyncio
            asyncio.get_event_loop().create_task(
                self._redis.set(f"task:{record.id}", json.dumps(record.to_dict()), ex=86400)
            )
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        return super().get(task_id)
