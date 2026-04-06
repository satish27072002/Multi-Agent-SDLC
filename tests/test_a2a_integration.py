import json

import pytest

pytest.importorskip("httpx")
pytest.importorskip("starlette")

from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from src.protocols.a2a_client import A2AClient
from src.protocols.a2a_server import create_a2a_app

pytestmark = pytest.mark.integration


class ExampleResponse(BaseModel):
    value: str


@pytest.mark.asyncio
async def test_a2a_client_round_trips_typed_response():
    async def handler(payload: dict[str, str]) -> ExampleResponse:
        return ExampleResponse(value=f"echo:{payload['task']}")

    app = create_a2a_app(
        agent_name="echo",
        description="echo agent",
        handler=handler,
        port=9001,
    )
    transport = ASGITransport(app=app)
    client = A2AClient("http://test", transport=transport)

    result = await client.send_text("hello", ExampleResponse)

    assert result.value == "echo:hello"


@pytest.mark.asyncio
async def test_a2a_server_exposes_agent_card_and_health():
    async def handler(payload: dict[str, str]) -> ExampleResponse:
        return ExampleResponse(value=json.dumps(payload))

    app = create_a2a_app(
        agent_name="echo",
        description="echo agent",
        handler=handler,
        port=9001,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        card = await client.get("/.well-known/agent-card.json")
        health = await client.get("/health")

    assert card.status_code == 200
    assert card.json()["name"] == "echo"
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_a2a_server_exposes_task_lifecycle_endpoints():
    async def handler(payload: dict[str, str]) -> ExampleResponse:
        return ExampleResponse(value=f"done:{payload['task']}")

    app = create_a2a_app(
        agent_name="echo",
        description="echo agent",
        handler=handler,
        port=9001,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/a2a/v1/message:send",
            json={"message": {"role": "user", "parts": [{"kind": "text", "text": json.dumps({"task": "hello"})}]}}
        )
        task_id = created.json()["id"]
        fetched = await client.get(f"/a2a/v1/tasks/{task_id}")
        listing = await client.get("/a2a/v1/tasks")

    assert created.status_code == 200
    assert fetched.status_code == 200
    assert fetched.json()["status"]["state"] == "completed"
    assert listing.status_code == 200
    assert any(item["id"] == task_id for item in listing.json()["tasks"])


@pytest.mark.asyncio
async def test_a2a_streaming_endpoint_emits_status_and_artifacts():
    async def handler(payload: dict[str, str]) -> ExampleResponse:
        return ExampleResponse(value=f"stream:{payload['task']}")

    app = create_a2a_app(
        agent_name="echo",
        description="echo agent",
        handler=handler,
        port=9001,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/a2a/v1/message:stream",
            json={"message": {"role": "user", "parts": [{"kind": "text", "text": json.dumps({"task": "hello"})}]}}
        )

    assert response.status_code == 200
    body = response.text
    assert "taskStatusUpdate" in body
    assert "taskArtifactUpdate" in body
