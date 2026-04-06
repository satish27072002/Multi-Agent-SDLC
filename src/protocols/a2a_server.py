from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

AgentHandler = Callable[[dict[str, Any]], Awaitable[BaseModel]]


@dataclass
class A2ATaskRecord:
    id: str
    context_id: str
    kind: str
    status: dict[str, Any]
    history: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "contextId": self.context_id,
            "kind": self.kind,
            "status": self.status,
            "history": self.history,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
        }


class A2ATaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, A2ATaskRecord] = {}

    def create(
        self, message: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> A2ATaskRecord:
        task_id = str(uuid4())
        context_id = str(uuid4())
        record = A2ATaskRecord(
            id=task_id,
            context_id=context_id,
            kind="task",
            status={"state": "submitted", "timestamp": _iso_now()},
            history=[message],
            metadata=metadata or {},
        )
        self._tasks[task_id] = record
        return record

    def get(self, task_id: str) -> A2ATaskRecord | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[A2ATaskRecord]:
        return list(self._tasks.values())

    def update_status(
        self, task_id: str, state: str, message: dict[str, Any] | None = None
    ) -> A2ATaskRecord:
        record = self._tasks[task_id]
        record.status = {"state": state, "timestamp": _iso_now()}
        if message:
            record.history.append(message)
        return record

    def set_artifacts(self, task_id: str, artifacts: list[dict[str, Any]]) -> A2ATaskRecord:
        record = self._tasks[task_id]
        record.artifacts = artifacts
        return record


def create_a2a_app(agent_name: str, description: str, handler: AgentHandler, port: int):
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, StreamingResponse
    from starlette.routing import Route

    task_store = A2ATaskStore()

    async def agent_card(_: Request) -> JSONResponse:
        card = {
            "name": agent_name,
            "description": description,
            "url": f"http://localhost:{port}",
            "version": "0.1.0",
            "preferredTransport": "JSONRPC",
            "protocolVersion": "1.0.0",
            "capabilities": {
                "streaming": True,
                "pushNotifications": False,
                "stateTransitionHistory": True,
            },
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
            "skills": [{"id": agent_name, "name": agent_name, "description": description}],
            "interfaces": [{"transport": "http+json", "url": f"http://localhost:{port}/a2a/v1"}],
        }
        return JSONResponse(card)

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "agent": agent_name})

    async def send_message(request: Request) -> JSONResponse:
        body = await request.json()
        message = _extract_message(body)
        payload = _extract_payload(body)
        task = task_store.create(message, metadata=body.get("metadata") or {})
        task_store.update_status(task.id, "working")
        result = await handler(payload)
        artifacts = _artifacts_from_result(result)
        task_store.set_artifacts(task.id, artifacts)
        task_store.update_status(task.id, "completed")
        return JSONResponse(task.to_dict())

    async def send_streaming_message(request: Request) -> StreamingResponse:
        body = await request.json()
        message = _extract_message(body)
        payload = _extract_payload(body)
        task = task_store.create(message, metadata=body.get("metadata") or {})

        async def iterator() -> AsyncIterator[str]:
            task_store.update_status(task.id, "working")
            yield _sse_payload(
                {
                    "event": "taskStatusUpdate",
                    "taskId": task.id,
                    "contextId": task.context_id,
                    "status": task.status,
                    "final": False,
                }
            )
            result = await handler(payload)
            artifacts = _artifacts_from_result(result)
            task_store.set_artifacts(task.id, artifacts)
            task_store.update_status(task.id, "completed")
            yield _sse_payload(
                {
                    "event": "taskArtifactUpdate",
                    "taskId": task.id,
                    "contextId": task.context_id,
                    "artifacts": artifacts,
                    "final": False,
                }
            )
            yield _sse_payload(
                {
                    "event": "taskStatusUpdate",
                    "taskId": task.id,
                    "contextId": task.context_id,
                    "status": task.status,
                    "final": True,
                }
            )

        return StreamingResponse(iterator(), media_type="text/event-stream")

    async def get_task(request: Request) -> JSONResponse:
        task_id = request.path_params["task_id"]
        task = task_store.get(task_id)
        if not task:
            return JSONResponse({"error": "Task not found"}, status_code=404)
        return JSONResponse(task.to_dict())

    async def list_tasks(_: Request) -> JSONResponse:
        return JSONResponse({"tasks": [task.to_dict() for task in task_store.list_tasks()]})

    async def cancel_task(request: Request) -> JSONResponse:
        task_id = request.path_params["task_id"]
        task = task_store.get(task_id)
        if not task:
            return JSONResponse({"error": "Task not found"}, status_code=404)
        if task.status.get("state") not in {"completed", "failed", "canceled"}:
            task_store.update_status(task.id, "canceled")
        return JSONResponse(task.to_dict())

    async def subscribe_to_task(request: Request) -> StreamingResponse:
        task_id = request.path_params["task_id"]

        async def iterator() -> AsyncIterator[str]:
            for _ in range(10):
                task = task_store.get(task_id)
                if task is None:
                    yield _sse_payload(
                        {
                            "event": "error",
                            "taskId": task_id,
                            "message": "Task not found",
                            "final": True,
                        }
                    )
                    return
                yield _sse_payload(
                    {
                        "event": "taskStatusUpdate",
                        "taskId": task.id,
                        "contextId": task.context_id,
                        "status": task.status,
                        "artifacts": task.artifacts,
                        "final": task.status.get("state") in {"completed", "failed", "canceled"},
                    }
                )
                if task.status.get("state") in {"completed", "failed", "canceled"}:
                    return
                await asyncio.sleep(0.25)

        return StreamingResponse(iterator(), media_type="text/event-stream")

    routes = [
        Route("/.well-known/agent-card.json", agent_card, methods=["GET"]),
        Route("/.well-known/agent.json", agent_card, methods=["GET"]),
        Route("/a2a/v1/agent-card", agent_card, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/a2a/v1/message:send", send_message, methods=["POST"]),
        Route("/a2a/v1/message:stream", send_streaming_message, methods=["POST"]),
        Route("/a2a/v1/tasks", list_tasks, methods=["GET"]),
        Route("/a2a/v1/tasks/{task_id}", get_task, methods=["GET"]),
        Route("/a2a/v1/tasks/{task_id}:cancel", cancel_task, methods=["POST"]),
        Route("/a2a/v1/tasks/{task_id}:subscribe", subscribe_to_task, methods=["GET"]),
        Route("/tasks/send", send_message, methods=["POST"]),
        Route("/tasks/{task_id}", get_task, methods=["GET"]),
    ]
    return Starlette(routes=routes)


def _extract_message(body: dict[str, Any]) -> dict[str, Any]:
    message = body.get("message") or body.get("params", {}).get("message")
    if isinstance(message, dict):
        return message
    text = body.get("task") or ""
    return {"role": "user", "parts": [{"kind": "text", "text": text}]}


def _extract_payload(body: dict[str, Any]) -> dict[str, Any]:
    message = _extract_message(body)
    parts = message.get("parts", [])
    text_chunks: list[str] = []
    for part in parts:
        kind = part.get("kind") or part.get("type")
        if kind == "text" and "text" in part:
            text_chunks.append(part["text"])

    text = "".join(text_chunks).strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"task": text}
    return parsed if isinstance(parsed, dict) else {"task": text}


def _artifacts_from_result(result: BaseModel) -> list[dict[str, Any]]:
    return [{"parts": [{"kind": "text", "text": result.model_dump_json()}]}]


def _sse_payload(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, str] = {}

    def register(self, name: str, url: str) -> None:
        self._agents[name] = url

    def get_url(self, name: str) -> str | None:
        return self._agents.get(name)

    def list_agents(self) -> dict[str, str]:
        return dict(self._agents)

    @classmethod
    def from_defaults(cls, base_port: int = 9000) -> AgentRegistry:
        registry = cls()
        agents = ["orchestrator", "coding", "review", "testing", "docs", "gitops"]
        for i, name in enumerate(agents):
            registry.register(name, f"http://localhost:{base_port + i}")
        return registry
