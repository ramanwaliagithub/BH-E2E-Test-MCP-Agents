"""Thin tool-use loop: Anthropic Messages API + MCP tools, nothing else.

Deliberately not a framework — no LangChain, no planner/executor abstraction.
Every agent in agentic/agents/ builds on this one function because the pattern
(call the model, run any tool it asks for via MCP, feed the result back, repeat
until it stops asking) is identical across the locator healer, test author, and
smoke crawler. Keeping it here means an interviewer (or a future maintainer) can
read one ~50-line function and see the entire control flow this repo relies on.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from agentic.mcp_client import MCPClient, MCPToolError

_env_path = Path(__file__).parent / ".env.local"
if _env_path.exists():
    load_dotenv(_env_path)

DEFAULT_MODEL = os.environ.get("AGENTIC_MODEL", "claude-sonnet-5")
MAX_TOOL_ITERATIONS = 15


async def run_agent_loop(
    mcp_client: MCPClient,
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    allowed_tools: list[str] | None = None,
) -> str:
    """Run one Claude + MCP tool-use conversation to completion.

    Loops until Claude replies without requesting a tool (stop_reason != "tool_use")
    or `max_iterations` is hit. Returns the final text response.

    `allowed_tools`, when given, restricts both what the model is shown (it never
    sees tools outside this list) and what actually gets executed (defense in
    depth in case the model names a tool it wasn't offered). Every MCP server here
    exposes some tools with real side effects or arbitrary code execution
    (e.g. Playwright MCP's browser_run_code_unsafe) that most agents have no
    business calling — callers should pass the narrowest set their task needs.
    """
    client = anthropic.Anthropic()
    tools = await mcp_client.list_tools_as_anthropic()
    if allowed_tools is not None:
        tools = [t for t in tools if t["name"] in allowed_tools]
    allowed_names = {t["name"] for t in tools}
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]

    for _ in range(max_iterations):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(block.text for block in response.content if block.type == "text")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                if block.name not in allowed_names:
                    raise MCPToolError(f"Tool '{block.name}' is not in the allowed tool set for this agent")
                result_text = await mcp_client.call_tool(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
                )
            except Exception as exc:  # MCPToolError or transport failure — feed back, don't crash the loop
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(exc),
                        "is_error": True,
                    }
                )
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"Agent loop did not converge within {max_iterations} tool-use iterations")
