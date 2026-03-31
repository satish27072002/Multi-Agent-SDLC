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
    workspace: str = ""

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
            "workspace": self.workspace,
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
            workspace=data.get("workspace", ""),
        )


class TaskStore:
    """In-memory task store. Swap with RedisTaskStore for server mode."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def create(self, task_text: str, workspace: str = "") -> TaskRecord:
        record = TaskRecord(task=task_text, workspace=workspace)
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

    def backend_name(self) -> str:
        return "memory"


class RedisTaskStore(TaskStore):
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "sdlc:task",
        ttl_seconds: int = 86400,
    ) -> None:
        super().__init__()
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._index_key = f"{key_prefix}:index"
        self._ttl_seconds = ttl_seconds
        self._redis: Any = None
        self._redis_unavailable = False

    def _task_key(self, task_id: str) -> str:
        return f"{self._key_prefix}:{task_id}"

    def _get_redis(self) -> Any:
        if self._redis_unavailable:
            return None
        if self._redis is not None:
            return self._redis

        try:
            import redis

            client = redis.Redis.from_url(self._redis_url, decode_responses=True)
            client.ping()
            self._redis = client
            return client
        except Exception:
            self._redis_unavailable = True
            return None

    def backend_name(self) -> str:
        return "redis" if self._get_redis() else "memory"

    def _persist(self, record: TaskRecord) -> None:
        redis_client = self._get_redis()
        if not redis_client:
            return

        payload = json.dumps(record.to_dict())
        redis_client.set(self._task_key(record.id), payload, ex=self._ttl_seconds)
        redis_client.zadd(self._index_key, {record.id: record.created_at})

    def _load_from_redis(self, task_id: str) -> TaskRecord | None:
        redis_client = self._get_redis()
        if not redis_client:
            return None

        raw = redis_client.get(self._task_key(task_id))
        if not raw:
            return None

        data = json.loads(raw)
        record = TaskRecord.from_dict(data)
        self._tasks[record.id] = record
        return record

    def create(self, task_text: str, workspace: str = "") -> TaskRecord:
        record = super().create(task_text, workspace=workspace)
        self._persist(record)
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        record = super().get(task_id)
        if record:
            return record
        return self._load_from_redis(task_id)

    def update(self, task_id: str, **kwargs: Any) -> TaskRecord | None:
        record = super().update(task_id, **kwargs)
        if not record:
            loaded = self._load_from_redis(task_id)
            if not loaded:
                return None
            record = super().update(task_id, **kwargs)
            if not record:
                return None

        self._persist(record)
        return record

    def list_tasks(self, limit: int = 50) -> list[TaskRecord]:
        redis_client = self._get_redis()
        if redis_client:
            task_ids = redis_client.zrevrange(self._index_key, 0, max(0, limit - 1))
            for task_id in task_ids:
                if task_id not in self._tasks:
                    self._load_from_redis(task_id)

        return super().list_tasks(limit)

    def delete(self, task_id: str) -> bool:
        removed = super().delete(task_id)

        redis_client = self._get_redis()
        if redis_client:
            deleted = redis_client.delete(self._task_key(task_id)) > 0
            redis_client.zrem(self._index_key, task_id)
            return removed or deleted

        return removed
