import asyncio
from types import SimpleNamespace

import pytest

from src.agents.coding import CodingResult, GeneratedFile
from src.agents.orchestrator import Stage
from src.cli.tui import SDLCApp, StagePanel
from src.core.config import Settings

pytestmark = pytest.mark.unit


class _DummyStyles:
    def __init__(self):
        self.display = "none"


class _DummyRichLog:
    def __init__(self):
        self.styles = _DummyStyles()
        self.lines = []

    def clear(self):
        self.lines.clear()

    def write(self, value):
        self.lines.append(str(value))


class _DummyNode:
    def __init__(self):
        self.children = []
        self.data = None

    def expand(self):
        return None

    def add(self, value):
        node = _DummyNode()
        node.data = value
        self.children.append(node)
        return node

    def add_leaf(self, value):
        node = _DummyNode()
        node.data = value
        self.children.append(node)
        return node


class _DummyTree:
    def __init__(self):
        self.root = _DummyNode()

    def clear(self):
        self.root = _DummyNode()


def _build_app(tmp_path):
    return SDLCApp(settings=Settings(groq_api_key="test-key"), workspace=tmp_path)


def test_stage_panel_render_and_set_stage():
    panel = StagePanel()
    rendered = panel._render_status()
    assert "Pipeline Status" in rendered
    panel.set_stage(Stage.CODING)


def test_sdlcapp_render_stage_panel(tmp_path):
    app = _build_app(tmp_path)
    rendered = app._render_stage_panel(Stage.TESTING)
    assert "Pipeline Status" in rendered
    assert "testing" in rendered


def test_sdlcapp_toggle_diff_and_show_files(tmp_path, monkeypatch):
    app = _build_app(tmp_path)
    diff = _DummyRichLog()
    tree = _DummyTree()
    lookup = {
        "#diff-view": diff,
        "#file-tree": tree,
    }
    monkeypatch.setattr(app, "query_one", lambda selector, *_: lookup[selector])

    app.action_toggle_diff()
    assert diff.styles.display == "block"
    app.action_toggle_diff()
    assert diff.styles.display == "none"

    result = CodingResult(
        files=[GeneratedFile(path="a.py", content="x=1", explanation="a")],
        summary="ok",
    )
    app.show_generated_files(result)
    assert tree.root.children


def test_refresh_file_tree_ignores_hidden(tmp_path, monkeypatch):
    app = _build_app(tmp_path)
    (tmp_path / "visible.py").write_text("x=1")
    (tmp_path / ".hidden").write_text("x=1")
    (tmp_path / "pkg").mkdir()

    tree = _DummyTree()
    monkeypatch.setattr(app, "query_one", lambda selector, *_: tree)

    app._refresh_file_tree()
    labels = [n.data for n in tree.root.children]
    assert any("visible.py" in str(v) for v in labels)
    assert not any(".hidden" in str(v) for v in labels)


@pytest.mark.asyncio
async def test_request_user_approval_flow(tmp_path, monkeypatch):
    app = _build_app(tmp_path)
    log = _DummyRichLog()
    inp = SimpleNamespace(disabled=True, placeholder="", focus=lambda: None)
    lookup = {
        "#agent-log": log,
        "#input-bar": inp,
    }
    monkeypatch.setattr(app, "query_one", lambda selector, *_: lookup[selector])

    async def release():
        await asyncio.sleep(0.01)
        app._approval_result = True
        app._approval_event.set()

    task = asyncio.create_task(app.request_user_approval())
    await release()
    assert await task is True
    assert any("approve" in line for line in log.lines)


def test_action_cancel_sets_reject(tmp_path):
    app = _build_app(tmp_path)
    app._approval_event = asyncio.Event()
    app._approval_result = True
    app.action_cancel()
    assert app._approval_result is False
    assert app._approval_event.is_set()
