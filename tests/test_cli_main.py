import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from src.agents.coding import CodingResult, GeneratedFile
from src.agents.docs import DocFile, DocsResult
from src.agents.gitops import GitPlan
from src.agents.orchestrator import PipelineState, Stage
from src.agents.review import ReviewResult
from src.agents.testing import TestRunResult as RunResultModel
from src.cli import main as cli_main
from src.core.config import RunMode, Settings

pytestmark = pytest.mark.integration


def test_guess_lang_known_and_unknown():
    assert cli_main._guess_lang("foo.py") == "python"
    assert cli_main._guess_lang("foo.tsx") == "typescript"
    assert cli_main._guess_lang("foo.unknown") == "text"


def test_load_settings_defaults_to_server_mode(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    settings = cli_main.load_settings()
    assert settings.mode == RunMode.SERVER


def test_build_parser_parses_task_and_flags():
    parser = cli_main.build_parser()
    args = parser.parse_args(["--task", "hello", "--skip-tests", "--skip-docs", "--skip-git"])
    assert args.task == "hello"
    assert args.skip_tests is True
    assert args.skip_docs is True
    assert args.skip_git is True


def test_server_headers_include_bearer_token():
    settings = Settings(api_token="secret")
    headers = cli_main._server_headers(settings)
    assert headers["Authorization"] == "Bearer secret"


def test_server_headers_without_token():
    settings = Settings(api_token="")
    headers = cli_main._server_headers(settings)
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_request_with_retry_retries_on_server_error(monkeypatch):
    request = httpx.Request("GET", "http://test/tasks")
    first = httpx.Response(500, request=request)
    second = httpx.Response(200, request=request, json={"ok": True})

    class DummyClient:
        def __init__(self):
            self.calls = 0

        async def request(self, method, url, **kwargs):
            self.calls += 1
            return first if self.calls == 1 else second

    async def no_sleep(_):
        return None

    monkeypatch.setattr(cli_main.asyncio, "sleep", no_sleep)
    settings = Settings(max_retries=2, retry_base_delay=0.01)
    client = DummyClient()

    resp = await cli_main._request_with_retry(client, "GET", "http://test/tasks", settings)
    assert resp.status_code == 200
    assert client.calls == 2


@pytest.mark.asyncio
async def test_request_with_retry_raises_on_unauthorized(monkeypatch):
    request = httpx.Request("GET", "http://test/tasks")
    unauthorized = httpx.Response(401, request=request, json={"detail": "Invalid bearer token"})

    class DummyClient:
        async def request(self, method, url, **kwargs):
            return unauthorized

    async def no_sleep(_):
        return None

    monkeypatch.setattr(cli_main.asyncio, "sleep", no_sleep)
    settings = Settings(max_retries=2, retry_base_delay=0.01)

    with pytest.raises(httpx.HTTPStatusError):
        await cli_main._request_with_retry(DummyClient(), "GET", "http://test/tasks", settings)


def test_init_project_creates_scaffold(tmp_path):
    cli_main.init_project(tmp_path)
    assert (tmp_path / "src").exists()
    assert (tmp_path / "tests").exists()
    assert (tmp_path / "docs").exists()
    assert (tmp_path / "README.md").exists()
    assert (tmp_path / ".gitignore").exists()


def test_show_final_summary_prints_panel(monkeypatch):
    state = PipelineState(task="x", stage=Stage.DONE)
    state.coding_result = CodingResult(
        files=[GeneratedFile(path="a.py", content="x=1", explanation="a")],
        summary="done",
    )
    state.test_run_result = RunResultModel(
        passed=True,
        output="1 passed",
        tests_run=1,
        tests_passed=1,
    )
    state.review_result = ReviewResult(approved=True, issues=[], summary="ok")
    state.docs_result = DocsResult(
        files=[DocFile(path="docs/a.md", content="# a", explanation="a")],
        summary="ok",
    )
    state.git_plan = GitPlan(branch_name="feat/x", commit_message="feat: x", summary="x")

    calls = []
    monkeypatch.setattr(
        cli_main.console,
        "print",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    cli_main._show_final_summary(state)
    assert calls


@pytest.mark.asyncio
async def test_run_session_single_task_uses_noninteractive_callback(monkeypatch, tmp_path):
    settings = Settings(groq_api_key="test-key")
    seen = {}

    async def fake_pipeline(task, workspace, settings, callback, skip_tests, skip_docs, skip_git):
        seen["interactive"] = callback._interactive
        return PipelineState(task=task, stage=Stage.DONE)

    monkeypatch.setattr(cli_main, "load_settings", lambda **kwargs: settings)
    monkeypatch.setattr(cli_main, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(cli_main, "_show_final_summary", lambda state: None)

    await cli_main.run_session(tmp_path, single_task="hello")
    assert seen["interactive"] is False


@pytest.mark.asyncio
async def test_run_session_quits_without_running_pipeline(monkeypatch, tmp_path):
    settings = Settings(groq_api_key="test-key")
    monkeypatch.setattr(cli_main, "load_settings", lambda **kwargs: settings)

    inputs = iter(["quit"])
    monkeypatch.setattr(cli_main.console, "input", lambda *args, **kwargs: next(inputs))

    async def should_not_run(*args, **kwargs):
        raise AssertionError("pipeline should not run")

    monkeypatch.setattr(cli_main, "run_pipeline", should_not_run)
    await cli_main.run_session(tmp_path)


def test_main_tui_importerror_exits(monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "build_parser",
        lambda: SimpleNamespace(
            parse_args=lambda: SimpleNamespace(
                init=False,
                local=False,
                server=None,
                tui=True,
                workspace=Path.cwd(),
                skip_tests=False,
                skip_docs=False,
                skip_git=False,
                task=None,
            )
        ),
    )
    original_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "src.cli.tui":
            raise ImportError("missing textual")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with pytest.raises(SystemExit):
        cli_main.main()


def test_main_runs_session(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli_main,
        "build_parser",
        lambda: SimpleNamespace(
            parse_args=lambda: SimpleNamespace(
                init=False,
                local=False,
                server=None,
                tui=False,
                workspace=tmp_path,
                skip_tests=True,
                skip_docs=True,
                skip_git=True,
                task="hi",
            )
        ),
    )

    called = {}

    def fake_asyncio_run(coro):
        called["ran"] = True
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(
        cli_main,
        "load_settings",
        lambda **kwargs: Settings(groq_api_key="test-key", mode=RunMode.LOCAL),
    )
    monkeypatch.setattr(cli_main, "_show_final_summary", lambda state: None)

    async def fake_pipeline(task, workspace, settings, callback, skip_tests, skip_docs, skip_git):
        return PipelineState(task=task, stage=Stage.DONE)

    monkeypatch.setattr(cli_main, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(cli_main.asyncio, "run", fake_asyncio_run)

    cli_main.main()
    assert called.get("ran") is True


def test_main_server_mode_uses_remote_session(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli_main,
        "build_parser",
        lambda: SimpleNamespace(
            parse_args=lambda: SimpleNamespace(
                init=False,
                local=False,
                server=None,
                tui=False,
                workspace=tmp_path,
                skip_tests=False,
                skip_docs=False,
                skip_git=False,
                task="hi",
            )
        ),
    )

    called = {}

    def fake_asyncio_run(coro):
        called["ran"] = True
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(cli_main, "load_settings", lambda **kwargs: Settings(mode=RunMode.SERVER))
    monkeypatch.setattr(cli_main, "run_server_session", lambda **kwargs: asyncio.sleep(0))
    monkeypatch.setattr(cli_main.asyncio, "run", fake_asyncio_run)

    cli_main.main()
    assert called.get("ran") is True


def test_main_server_fallbacks_to_local(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli_main,
        "build_parser",
        lambda: SimpleNamespace(
            parse_args=lambda: SimpleNamespace(
                init=False,
                local=False,
                server=None,
                tui=False,
                workspace=tmp_path,
                skip_tests=False,
                skip_docs=False,
                skip_git=False,
                task="hi",
            )
        ),
    )

    def fake_load_settings(**kwargs):
        mode = kwargs.get("mode", "server")
        if mode == "local":
            return Settings(groq_api_key="k", mode=RunMode.LOCAL)
        return Settings(mode=RunMode.SERVER)

    async def failing_server(**kwargs):
        raise httpx.ConnectError("down")

    async def local_ok(**kwargs):
        return None

    called = {"local": False}

    def fake_asyncio_run(coro):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()

    async def wrapped_local(**kwargs):
        called["local"] = True
        await local_ok(**kwargs)

    monkeypatch.setattr(cli_main, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli_main, "run_server_session", failing_server)
    monkeypatch.setattr(cli_main, "run_session", wrapped_local)
    monkeypatch.setattr(cli_main.asyncio, "run", fake_asyncio_run)

    cli_main.main()
    assert called["local"] is True
