"""Tests for core.state module."""

from src.core.state import TaskRecord, TaskStatus, TaskStore


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
