"""Tests for core.state module."""

import pytest

from src.core.state import RedisTaskStore, TaskRecord, TaskStatus, TaskStore

pytestmark = pytest.mark.unit


class TestTaskStore:
    def test_create_task(self):
        store = TaskStore()
        record = store.create("Build auth system")
        assert record.task == "Build auth system"
        assert record.status == TaskStatus.PENDING
        assert record.id

    def test_get_task(self):
        store = TaskStore()
        record = store.create("Test task")
        retrieved = store.get(record.id)
        assert retrieved is not None
        assert retrieved.id == record.id
        assert retrieved.task == "Test task"

    def test_get_nonexistent_returns_none(self):
        store = TaskStore()
        assert store.get("nonexistent-id") is None

    def test_update_task(self):
        store = TaskStore()
        record = store.create("Task to update")
        updated = store.update(record.id, status=TaskStatus.RUNNING, current_stage="coding")
        assert updated is not None
        assert updated.status == TaskStatus.RUNNING
        assert updated.current_stage == "coding"

    def test_update_nonexistent_returns_none(self):
        store = TaskStore()
        assert store.update("nonexistent", status=TaskStatus.FAILED) is None

    def test_list_tasks(self):
        store = TaskStore()
        store.create("Task 1")
        store.create("Task 2")
        store.create("Task 3")
        tasks = store.list_tasks()
        assert len(tasks) == 3

    def test_list_tasks_limit(self):
        store = TaskStore()
        for i in range(10):
            store.create(f"Task {i}")
        tasks = store.list_tasks(limit=5)
        assert len(tasks) == 5

    def test_delete_task(self):
        store = TaskStore()
        record = store.create("Task to delete")
        assert store.delete(record.id) is True
        assert store.get(record.id) is None

    def test_delete_nonexistent(self):
        store = TaskStore()
        assert store.delete("nonexistent") is False


class TestTaskRecord:
    def test_to_dict(self):
        record = TaskRecord(task="Test", status=TaskStatus.RUNNING)
        d = record.to_dict()
        assert d["task"] == "Test"
        assert d["status"] == "running"
        assert "id" in d

    def test_from_dict(self):
        data = {
            "id": "test-id",
            "task": "Test task",
            "status": "completed",
            "created_at": 1000.0,
            "updated_at": 1001.0,
            "result": {"files": ["a.py"]},
            "errors": [],
            "current_stage": "done",
        }
        record = TaskRecord.from_dict(data)
        assert record.id == "test-id"
        assert record.status == TaskStatus.COMPLETED
        assert record.result == {"files": ["a.py"]}


class _FakeRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}
        self.index: dict[str, float] = {}

    def set(self, key, value, ex=None):
        self.kv[key] = value

    def get(self, key):
        return self.kv.get(key)

    def zadd(self, key, mapping):
        self.index.update(mapping)

    def zrevrange(self, key, start, end):
        ordered = sorted(self.index.items(), key=lambda item: item[1], reverse=True)
        values = [item[0] for item in ordered]
        if end < 0:
            return values[start:]
        return values[start : end + 1]

    def delete(self, key):
        existed = key in self.kv
        self.kv.pop(key, None)
        return 1 if existed else 0

    def zrem(self, key, member):
        self.index.pop(member, None)


class TestRedisTaskStore:
    def test_redis_store_persists_and_reads(self):
        store = RedisTaskStore()
        fake = _FakeRedis()
        store._redis = fake

        created = store.create("Build API", workspace="/tmp/work")
        assert created.id in fake.index

        store._tasks.clear()
        loaded = store.get(created.id)
        assert loaded is not None
        assert loaded.task == "Build API"
        assert loaded.workspace == "/tmp/work"

    def test_redis_store_update_and_delete(self):
        store = RedisTaskStore()
        fake = _FakeRedis()
        store._redis = fake

        created = store.create("Build API")
        updated = store.update(created.id, status=TaskStatus.RUNNING, current_stage="coding")
        assert updated is not None
        assert updated.current_stage == "coding"

        assert store.delete(created.id) is True
        assert store.get(created.id) is None

    def test_redis_store_falls_back_to_memory_when_unavailable(self):
        store = RedisTaskStore()
        store._redis_unavailable = True

        created = store.create("Fallback task")
        assert store.get(created.id) is not None
