from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class A2AClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    async def send_payload(self, payload: dict[str, Any], output_type: type[T]) -> T:
        message = {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": json.dumps(payload),
                    }
                ],
            }
        }
        raw = await self._post_message(message)
        return output_type.model_validate_json(raw)

    async def send_text(self, task: str, output_type: type[T]) -> T:
        return await self.send_payload({"task": task}, output_type)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=5.0,
                transport=self._transport,
            ) as client:
                response = await client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def get_agent_card(self) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=10.0,
            transport=self._transport,
        ) as client:
            response = await client.get(f"{self.base_url}/.well-known/agent-card.json")
            response.raise_for_status()
            return response.json()

    async def get_task(self, task_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=10.0,
            transport=self._transport,
        ) as client:
            response = await client.get(f"{self.base_url}/a2a/v1/tasks/{task_id}")
            response.raise_for_status()
            return response.json()

    async def list_tasks(self) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=10.0,
            transport=self._transport,
        ) as client:
            response = await client.get(f"{self.base_url}/a2a/v1/tasks")
            response.raise_for_status()
            return response.json()

    async def _post_message(self, message: dict[str, Any]) -> str:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self._transport,
        ) as client:
            response = await client.post(
                f"{self.base_url}/a2a/v1/message:send",
                json=message,
            )
            response.raise_for_status()

        data = response.json()
        if "id" in data:
            task = await self.get_task(data["id"])
            data = task
        artifacts = data.get("artifacts") or data.get("result", {}).get("artifacts", [])
        text_parts: list[str] = []
        for artifact in artifacts:
            for part in artifact.get("parts", []):
                kind = part.get("kind") or part.get("type")
                if kind == "text" and "text" in part:
                    text_parts.append(part["text"])

        if not text_parts:
            raise ValueError("A2A response did not contain a text artifact")
        return "".join(text_parts)
