"""Tests for server.api endpoints."""

from unittest.mock import patch

import pytest

# Guard import — server deps may not be installed
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from httpx import ASGITransport, AsyncClient

from src.core.config import RunMode, Settings
from src.server.api import app


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
