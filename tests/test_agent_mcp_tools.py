import pytest

from src.agents.coding import mcp_list_files, mcp_read_file, mcp_run_linter
from src.agents.gitops import create_pull_request_via_mcp, list_open_issues_via_mcp
from src.agents.testing import mcp_run_command, mcp_testing_read_file
from src.core.config import Settings
from src.protocols.mcp_client import MCPToolResult

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_coding_agent_uses_local_mcp(monkeypatch, tmp_path):
    calls = []

    async def fake_list_directory(self, directory="."):
        calls.append(("list", directory))
        return MCPToolResult(content="file app.py")

    async def fake_read_file(self, file_path):
        calls.append(("read", file_path))
        return MCPToolResult(content="print('ok')")

    async def fake_run_linter(self, file_path, linter="ruff"):
        calls.append(("lint", file_path, linter))
        return MCPToolResult(content="All checks passed!")

    monkeypatch.setattr(
        "src.protocols.mcp_client.LocalToolsMCP.list_directory", fake_list_directory
    )
    monkeypatch.setattr("src.protocols.mcp_client.LocalToolsMCP.read_file", fake_read_file)
    monkeypatch.setattr("src.protocols.mcp_client.LocalToolsMCP.run_linter", fake_run_linter)

    assert await mcp_list_files(tmp_path, "src") == "file app.py"
    assert await mcp_read_file(tmp_path, "app.py") == "print('ok')"
    assert await mcp_run_linter(tmp_path, "app.py") == "All checks passed!"
    assert calls == [("list", "src"), ("read", "app.py"), ("lint", "app.py", "ruff")]


@pytest.mark.asyncio
async def test_testing_agent_uses_local_mcp(monkeypatch, tmp_path):
    calls = []

    async def fake_read_file(self, file_path):
        calls.append(("read", file_path))
        return MCPToolResult(content="def f(): return 1")

    async def fake_run_command(self, command, timeout=60):
        calls.append(("command", command, timeout))
        return MCPToolResult(content="pytest -q")

    monkeypatch.setattr("src.protocols.mcp_client.LocalToolsMCP.read_file", fake_read_file)
    monkeypatch.setattr("src.protocols.mcp_client.LocalToolsMCP.run_command", fake_run_command)

    assert await mcp_testing_read_file(tmp_path, "app.py") == "def f(): return 1"
    assert await mcp_run_command(tmp_path, "pytest -q") == "pytest -q"
    assert calls == [("read", "app.py"), ("command", "pytest -q", 30)]


@pytest.mark.asyncio
async def test_gitops_uses_github_mcp_for_pull_requests(monkeypatch):
    events = []

    class FakeGitHubMCPClient:
        def __init__(self, github_token=None):
            events.append(("init", github_token))

        async def connect(self):
            events.append(("connect",))

        async def create_pull_request(self, repo, title, body, head, base="main"):
            events.append(("create_pr", repo, title, body, head, base))
            return MCPToolResult(content="https://example.com/pr/1")

        async def list_issues(self, repo, state="open"):
            events.append(("list_issues", repo, state))
            return MCPToolResult(content="issue-1")

        async def disconnect(self):
            events.append(("disconnect",))

    monkeypatch.setattr("src.agents.gitops.GitHubMCPClient", FakeGitHubMCPClient)
    settings = Settings(groq_api_key="test", github_token="gh-token")

    pr = await create_pull_request_via_mcp(
        settings=settings,
        repo="satish27072002/multi-agent-sdlc",
        title="feat: test",
        body="body",
        branch="feat/test",
    )
    issues = await list_open_issues_via_mcp(settings, "satish27072002/multi-agent-sdlc")

    assert pr == "https://example.com/pr/1"
    assert issues == "issue-1"
    assert events[0] == ("init", "gh-token")
    assert (
        "create_pr",
        "satish27072002/multi-agent-sdlc",
        "feat: test",
        "body",
        "feat/test",
        "main",
    ) in events
    assert ("list_issues", "satish27072002/multi-agent-sdlc", "open") in events
