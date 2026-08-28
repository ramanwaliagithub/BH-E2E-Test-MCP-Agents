"""Stateless, no-LLM bridge from Claude Code to a Playwright MCP server.

This is the "Option 3" variant: there is no second AI model call anywhere in
this file, and no ANTHROPIC_API_KEY. Claude Code itself (the session you're
reading this from, covered by your existing subscription) is the reasoning
engine — it decides the plan, this script only executes MCP tool calls and
returns their raw text output for Claude Code to read and reason over.

Deliberately does NOT import anything from agentic/ (which drives the same
Playwright MCP server from a second, standalone Claude API call instead) —
kept fully separate so the two approaches never share code or get confused
with each other.

A single call to this script runs a whole ORDERED LIST of MCP tool calls
against one persistent browser session (one login + all navigation stays
valid across every step in the list), because each separate Bash invocation
from Claude Code would otherwise spawn a brand new, stateless browser with no
memory of prior steps.

Usage:
    python mcp_bridge.py <path-to-steps.json>

steps.json is a JSON array like:
    [
      {"tool": "browser_navigate", "args": {"url": "https://example.com"}},
      {"tool": "browser_snapshot", "args": {}}
    ]

Prints each step's result to stdout, clearly separated, in order.
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

CONFIG_PATH = Path(__file__).parent / "mcp_config.json"


async def run_steps(steps: list[dict]) -> None:
    config = json.loads(CONFIG_PATH.read_text())
    server_name = config["defaultServer"]
    server = config["mcpServers"][server_name]
    params = StdioServerParameters(command=server["command"], args=server.get("args", []))

    async with AsyncExitStack() as stack:
        read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
        session: ClientSession = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()

        for i, step in enumerate(steps, start=1):
            tool_name = step["tool"]
            arguments = step.get("args", {})
            print(f"\n===== step {i}: {tool_name}({json.dumps(arguments)}) =====")
            try:
                result = await session.call_tool(tool_name, arguments)
                text = "\n".join(b.text for b in result.content if isinstance(b, types.TextContent))
                if result.is_error:
                    print(f"[ERROR] {text}")
                else:
                    print(text)
            except Exception as exc:
                print(f"[EXCEPTION] {exc}")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python mcp_bridge.py <path-to-steps.json>", file=sys.stderr)
        sys.exit(1)

    steps = json.loads(Path(sys.argv[1]).read_text())
    asyncio.run(run_steps(steps))


if __name__ == "__main__":
    main()
