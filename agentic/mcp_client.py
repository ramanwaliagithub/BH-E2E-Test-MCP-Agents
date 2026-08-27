"""Thin async wrapper around a Playwright MCP server (stdio transport).

Connects to the server defined in mcp_config.json, lists its tools, and exposes
them in the shape the Anthropic Messages API expects for tool use. Agents build
on top of this rather than talking to the `mcp` SDK directly, so the MCP wiring
lives in one place.
"""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

DEFAULT_CONFIG_PATH = Path(__file__).parent / "mcp_config.json"


class MCPToolError(RuntimeError):
    """Raised when an MCP tool call reports isError=True."""


class MCPClient:
    """Connects to one MCP server over stdio for the lifetime of an `async with` block.

    Usage:
        async with MCPClient.from_config() as client:
            tools = await client.list_tools_as_anthropic()
            snapshot = await client.call_tool("browser_snapshot", {})
    """

    def __init__(self, command: str, args: list[str], env: dict[str, str] | None = None):
        self._command = command
        self._args = args
        self._env = env
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None

    @classmethod
    def from_config(cls, config_path: str | Path | None = None, server: str | None = None) -> "MCPClient":
        """Build a client from mcp_config.json (or a given path) without connecting yet."""
        path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        config = json.loads(path.read_text())
        server_name = server or config.get("defaultServer")
        if not server_name or server_name not in config["mcpServers"]:
            raise KeyError(f"MCP server '{server_name}' not found in {path}")
        server_config = config["mcpServers"][server_name]
        return cls(
            command=server_config["command"],
            args=server_config.get("args", []),
            env=server_config.get("env"),
        )

    async def __aenter__(self) -> "MCPClient":
        params = StdioServerParameters(command=self._command, args=self._args, env=self._env)
        read_stream, write_stream = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read_stream, write_stream))
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self._stack.aclose()
        self._session = None

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("MCPClient is not connected — use 'async with MCPClient(...) as client:'")
        return self._session

    async def list_tools(self) -> list[types.Tool]:
        result = await self.session.list_tools()
        return result.tools

    async def list_tools_as_anthropic(self) -> list[dict[str, Any]]:
        """Convert MCP tool definitions to Anthropic's {name, description, input_schema} shape."""
        tools = await self.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call an MCP tool and return its text content, concatenated.

        Raises MCPToolError if the server reports the call failed.
        """
        result = await self.session.call_tool(name, arguments)
        text = "\n".join(block.text for block in result.content if isinstance(block, types.TextContent))
        if result.is_error:
            raise MCPToolError(text or f"Tool '{name}' failed with no error text")
        return text
