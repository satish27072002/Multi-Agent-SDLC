"""A2A server — exposes each agent as an Agent-to-Agent protocol server.

Uses FastA2A from Pydantic AI to make agents discoverable and callable
by other agents over HTTP.
"""

from __future__ import annotations

import importlib

from pydantic_ai import Agent


def create_a2a_app(agent: Agent, name: str, description: str, port: int):
    """Wrap a Pydantic AI agent as an A2A-compatible ASGI application.

    Args:
        agent: The Pydantic AI agent to expose.
        name: Human-readable agent name for discovery.
        description: What this agent does.
        port: Port to bind when running standalone.

    Returns:
        A Starlette/ASGI app that speaks A2A protocol.
    """

    try:
        fasta2a_module = importlib.import_module("fasta2a")
        fast_a2a_cls = getattr(fasta2a_module, "FastA2A")

        a2a_app = fast_a2a_cls(
            agent=agent,
            name=name,
            description=description,
        )
        return a2a_app
    except ImportError:
        # FastA2A not installed — return a minimal stub
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def agent_card(request):
            return JSONResponse({
                "name": name,
                "description": description,
                "url": f"http://localhost:{port}",
                "capabilities": {},
            })

        async def health(request):
            return JSONResponse({"status": "ok", "agent": name})

        return Starlette(routes=[
            Route("/.well-known/agent.json", agent_card),
            Route("/health", health),
        ])


# ---------------------------------------------------------------------------
# Agent registry for A2A discovery
# ---------------------------------------------------------------------------

class AgentRegistry:
    """Tracks known A2A agent endpoints for the orchestrator."""

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
        """Create registry with default local agent URLs."""
        registry = cls()
        agents = ["orchestrator", "coding", "review", "testing", "docs", "gitops"]
        for i, name in enumerate(agents):
            registry.register(name, f"http://localhost:{base_port + i}")
        return registry
