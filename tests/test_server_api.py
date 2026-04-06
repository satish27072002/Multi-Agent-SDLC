"""Tests for server.api endpoints."""

from unittest.mock import patch

import pytest

# Guard import — server deps may not be installed
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from httpx import ASGITransport, AsyncClient

from src.core.config import RunMode, Settings
from src.core.state import TaskStatus
from src.server import api as server_api
from src.server.api import app

pytestmark = pytest.mark.integration


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["agents"] == 6
        assert "version" in data
        assert "uptime" in data


class TestAgentModeHelpers:
    def test_agent_mode_from_settings_distributed(self):
        settings = Settings(groq_api_key="test", agent_mode="distributed")
        assert server_api._agent_mode_from_settings(settings) == server_api.AgentMode.DISTRIBUTED

    def test_agent_urls_from_settings(self):
        settings = Settings(
            groq_api_key="test",
            coding_agent_url="http://coding:9001",
            testing_agent_url="http://testing:9002",
            review_agent_url="http://review:9003",
            docs_agent_url="http://docs:9004",
            gitops_agent_url="http://gitops:9005",
        )
        urls = server_api._agent_urls_from_settings(settings)
        assert urls["coding"] == "http://coding:9001"
        assert urls["gitops"] == "http://gitops:9005"


class TestAgentsEndpoint:
    @pytest.mark.asyncio
    async def test_list_agents(self, client):
        with patch("src.server.api.load_settings") as mock_settings:
            from src.core.config import Settings
            mock_settings.return_value = Settings(groq_api_key="test")
            resp = await client.get("/agents")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["agents"]) == 6
            names = [a["name"] for a in data["agents"]]
            assert "coding" in names
            assert "testing" in names
            assert "review" in names


class TestTasksEndpoint:
    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, client):
        resp = await client.get("/tasks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, client):
        resp = await client.get("/tasks/nonexistent-id")
        assert resp.status_code == 404


class TestAuth:
    @pytest.mark.asyncio
    async def test_tasks_require_bearer_when_token_configured(self, client):
        with patch("src.server.api.load_settings") as mock_settings:
            mock_settings.return_value = Settings(mode=RunMode.SERVER, api_token="secret")
            resp = await client.get("/tasks")
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_tasks_allow_bearer_when_token_configured(self, client):
        with patch("src.server.api.load_settings") as mock_settings:
            mock_settings.return_value = Settings(mode=RunMode.SERVER, api_token="secret")
            resp = await client.get("/tasks", headers={"Authorization": "Bearer secret"})
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_does_not_require_token(self, client):
        with patch("src.server.api.load_settings") as mock_settings:
            mock_settings.return_value = Settings(mode=RunMode.SERVER, api_token="secret")
            resp = await client.get("/health")
            assert resp.status_code == 200


class TestArtifactsAndWorkspaces:
    @pytest.mark.asyncio
    async def test_task_artifacts_lists_workspace_files(self, client, tmp_path):
        with patch("src.server.api.load_settings") as mock_settings:
            mock_settings.return_value = Settings(mode=RunMode.SERVER, api_token="")

            record = server_api.task_store.create("artifact task", workspace=str(tmp_path / "w1"))
            workspace = tmp_path / "w1"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "main.py").write_text("print('ok')\n")
            server_api.task_store.update(record.id, status=TaskStatus.COMPLETED)

            resp = await client.get(f"/tasks/{record.id}/artifacts")
            assert resp.status_code == 200
            data = resp.json()
            assert data["task_id"] == record.id
            assert any(item["path"] == "main.py" for item in data["files"])

    @pytest.mark.asyncio
    async def test_delete_task_workspace_removes_directory(self, client, tmp_path):
        with patch("src.server.api.load_settings") as mock_settings:
            mock_settings.return_value = Settings(mode=RunMode.SERVER, api_token="")

            workspace = tmp_path / "w2"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "notes.txt").write_text("hello\n")
            record = server_api.task_store.create("cleanup", workspace=str(workspace))

            resp = await client.delete(f"/tasks/{record.id}/workspace")
            assert resp.status_code == 200
            body = resp.json()
            assert body["deleted"] is True
            assert workspace.exists() is False

    @pytest.mark.asyncio
    async def test_list_workspaces_returns_entries(self, client, tmp_path):
        with patch("src.server.api.load_settings") as mock_settings:
            mock_settings.return_value = Settings(mode=RunMode.SERVER, api_token="")

            ws = tmp_path / "w3"
            ws.mkdir(parents=True, exist_ok=True)
            (ws / "a.txt").write_text("x")
            record = server_api.task_store.create("workspace list", workspace=str(ws))
            server_api.task_store.update(record.id, status=TaskStatus.RUNNING)

            resp = await client.get("/workspaces")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["workspaces"]
            assert any(item["task_id"] == record.id for item in payload["workspaces"])
