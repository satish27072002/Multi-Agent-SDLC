"""MCP client — connects agents to external tools via Model Context Protocol.

Provides a unified interface for agents to access:
- GitHub operations (clone, create PR, list issues)
- File system operations
- Terminal command execution
- Linter integration
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MCPTool:
    """Represents a tool available via MCP."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPToolResult:
    """Result from executing an MCP tool."""

    content: str
    is_error: bool = False


class MCPClient:
    """Client for communicating with MCP servers.

    Supports both stdio-based (subprocess) and HTTP-based MCP servers.
    """

    def __init__(
        self,
        server_command: list[str] | None = None,
        server_url: str | None = None,
        server_env: dict[str, str] | None = None,
    ) -> None:
        self._server_command = server_command
        self._server_url = server_url
        self._server_env = server_env
        self._process: asyncio.subprocess.Process | None = None
        self._tools: dict[str, MCPTool] = {}
        self._request_id = 0

    async def connect(self) -> None:
        """Start the MCP server and discover available tools."""
        if self._server_command:
            self._process = await asyncio.create_subprocess_exec(
                *self._server_command,
                env=self._server_env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # Send initialize request
            await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "sdlc-agent", "version": "0.1.0"},
                },
            )
            # Discover tools
            tools_response = await self._send_request("tools/list", {})
            if tools_response and "tools" in tools_response:
                for tool_data in tools_response["tools"]:
                    tool = MCPTool(
                        name=tool_data["name"],
                        description=tool_data.get("description", ""),
                        input_schema=tool_data.get("inputSchema", {}),
                    )
                    self._tools[tool.name] = tool

    async def disconnect(self) -> None:
        """Shut down the MCP server connection."""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None

    def list_tools(self) -> list[MCPTool]:
        """Return all available tools from this server."""
        return list(self._tools.values())

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> MCPToolResult:
        """Execute a tool on the MCP server."""
        if name not in self._tools:
            return MCPToolResult(content=f"Unknown tool: {name}", is_error=True)

        response = await self._send_request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments or {},
            },
        )

        if response and "content" in response:
            parts = []
            for item in response["content"]:
                if item.get("type") == "text":
                    parts.append(item["text"])
            return MCPToolResult(content="\n".join(parts))

        return MCPToolResult(content="No response from tool", is_error=True)

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Send a JSON-RPC request to the MCP server."""
        if not self._process or not self._process.stdin or not self._process.stdout:
            return None

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        message = json.dumps(request) + "\n"
        self._process.stdin.write(message.encode())
        await self._process.stdin.drain()

        line = await asyncio.wait_for(self._process.stdout.readline(), timeout=30)
        if line:
            response = json.loads(line.decode())
            return response.get("result")
        return None


# ---------------------------------------------------------------------------
# GitHub MCP integration
# ---------------------------------------------------------------------------


class GitHubMCPClient(MCPClient):
    """MCP client pre-configured for GitHub operations.

    Wraps the GitHub MCP server (npx @modelcontextprotocol/server-github)
    to provide repository operations for the GitOps agent.
    """

    def __init__(self, github_token: str | None = None) -> None:
        env_token = github_token or ""
        super().__init__(
            server_command=["npx", "-y", "@modelcontextprotocol/server-github"],
            server_env={
                "GITHUB_PERSONAL_ACCESS_TOKEN": env_token,
                "GITHUB_TOKEN": env_token,
            },
        )
        self._github_token = env_token

    async def clone_repo(self, repo: str, target_dir: Path) -> MCPToolResult:
        """Clone a GitHub repository."""
        return await self.call_tool(
            "clone_repository",
            {
                "repository": repo,
                "target_directory": str(target_dir),
            },
        )

    async def create_pull_request(
        self,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
    ) -> MCPToolResult:
        """Create a pull request on GitHub."""
        return await self.call_tool(
            "create_pull_request",
            {
                "repository": repo,
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )

    async def list_issues(self, repo: str, state: str = "open") -> MCPToolResult:
        """List issues on a GitHub repository."""
        return await self.call_tool(
            "list_issues",
            {
                "repository": repo,
                "state": state,
            },
        )


# ---------------------------------------------------------------------------
# File system MCP tools (local, no server needed)
# ---------------------------------------------------------------------------


class LocalToolsMCP:
    """Local MCP-compatible tools that don't need an external server.

    Provides file system and terminal tools directly.
    """

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    async def read_file(self, path: str) -> MCPToolResult:
        """Read a file from the workspace."""
        target = self._workspace / path
        if not target.is_file():
            return MCPToolResult(content=f"File not found: {path}", is_error=True)
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            return MCPToolResult(content=content)
        except Exception as e:
            return MCPToolResult(content=str(e), is_error=True)

    async def write_file(self, path: str, content: str) -> MCPToolResult:
        """Write a file to the workspace."""
        target = self._workspace / path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return MCPToolResult(content=f"Written: {path}")
        except Exception as e:
            return MCPToolResult(content=str(e), is_error=True)

    async def list_directory(self, path: str = ".") -> MCPToolResult:
        """List files in a directory."""
        target = self._workspace / path
        if not target.is_dir():
            return MCPToolResult(content=f"Not a directory: {path}", is_error=True)
        entries = sorted(target.iterdir())
        lines = []
        for entry in entries[:100]:
            prefix = "dir  " if entry.is_dir() else "file "
            lines.append(f"{prefix}{entry.relative_to(self._workspace)}")
        return MCPToolResult(content="\n".join(lines) if lines else "(empty)")

    async def run_command(self, command: str, timeout: int = 60) -> MCPToolResult:
        """Run a shell command in the workspace."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self._workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode(errors="replace")
            return MCPToolResult(content=output, is_error=proc.returncode != 0)
        except asyncio.TimeoutError:
            return MCPToolResult(content=f"Command timed out after {timeout}s", is_error=True)
        except Exception as e:
            return MCPToolResult(content=str(e), is_error=True)

    async def run_linter(self, path: str, linter: str = "ruff") -> MCPToolResult:
        """Run a linter on a file."""
        return await self.run_command(f"{linter} check {path}")
