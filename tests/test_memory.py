from src.core.memory import MemoryEntry, WorkspaceMemoryStore


def test_memory_store_add_and_load(tmp_path):
    store = WorkspaceMemoryStore(tmp_path, max_entries=5)
    store.add(MemoryEntry(task="Build API", status="done", summary="Created endpoints", files=["api.py"]))

    snapshot = store.load()

    assert len(snapshot.entries) == 1
    assert snapshot.entries[0].task == "Build API"
    assert snapshot.entries[0].files == ["api.py"]


def test_memory_store_builds_relevant_context(tmp_path):
    store = WorkspaceMemoryStore(tmp_path, max_entries=5)
    store.add(MemoryEntry(task="Add auth middleware", status="done", summary="Created auth.py"))
    store.add(MemoryEntry(task="Build dashboard", status="done", summary="Created charts"))

    context = store.build_context("Improve auth login flow")

    assert "Relevant context" in context
    assert "auth middleware" in context
