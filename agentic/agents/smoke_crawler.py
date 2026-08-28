"""Exploratory smoke-crawler agent.

Reuses agent_loop.py/mcp_client.py, same as the other two agents. Unlike
them, this one never fixes or authors anything — it reads the repo's real,
existing pytest test file as the source of "what flows matter and what they
expect," walks each flow live via MCP, and produces a structured drift
report. A human decides what (if anything) to do with the report; nothing
in this file ever writes to ui-tests/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from agentic.agent_loop import run_agent_loop
from agentic.mcp_client import MCPClient

# Same safe set as the other agents: enough to walk a flow and observe the
# page, nothing that mutates anything beyond what the flow itself requires,
# nothing that runs arbitrary code.
ALLOWED_TOOLS = [
    "browser_navigate",
    "browser_snapshot",
    "browser_find",
    "browser_fill_form",
    "browser_click",
    "browser_evaluate",
    "browser_wait_for",
]

SYSTEM_PROMPT = """\
You are a drift-detection agent for a Python Playwright/pytest UI suite. \
You do NOT fix anything and you do NOT write any files — your only job is to \
walk existing test flows live and report whether they still behave the way \
the test file assumes.

You will be shown the full source of a real pytest test file. Each test \
function is one "key flow": its docstring says what it's testing, and its \
body shows exactly which locators and assertions it relies on.

For each test function:
1. Perform the same steps live using the browser tools, using the literal \
locators/values shown in the file (e.g. the same username, the same \
data-test selector).
2. Check whether every element you needed actually resolved (did not time \
out or fail to be found), and whether the resulting page state matches what \
the test's assert statements expect (same text, same count, same URL \
fragment, etc.).
3. Classify the flow as one of:
   - "ok" — behaves exactly as the test file assumes.
   - "drift" — you could still complete the flow, but something differs from \
what the test file assumes (different text, a different but findable \
selector, an extra step, a layout change) — the test might still pass today \
but is relying on something that quietly changed.
   - "broken" — the flow does not work at all as written (an element never \
appears, an assertion's expected condition cannot be reached).

When you are done checking every test function shown to you, respond with \
ONLY a single JSON object, no other text:
{"flows": [{"name": "<test function name>", "status": "ok"|"drift"|"broken", \
"findings": "<1-3 sentences on what you found; empty string if ok>"}]}
"""


def extract_json(text: str) -> dict:
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    return json.loads(stripped)


def build_user_prompt(test_file_source: str, url: str, login_url: str | None, username: str | None, password: str | None) -> str:
    login_section = ""
    if login_url:
        login_section = f"\nThe app is at {url}; log in at {login_url} with the credentials shown in the test file where needed.\n"
    return f"""\
Here is the real test file to check flows from:

```python
{test_file_source}
```
{login_section}
Walk every test function's flow live, then respond with the final JSON report only.
"""


async def crawl(
    test_file: Path,
    url: str,
    login_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    max_iterations: int = 40,
) -> dict:
    """Run the crawler against one test file. Returns the parsed drift report."""
    source = test_file.read_text()
    user_prompt = build_user_prompt(source, url, login_url, username, password)

    async with MCPClient.from_config() as client:
        response_text = await run_agent_loop(
            client,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            allowed_tools=ALLOWED_TOOLS,
            max_iterations=max_iterations,
        )

    return extract_json(response_text)


def save_report(report: dict, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = reports_dir / f"smoke_crawl_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2))
    return path


def print_summary(report: dict) -> None:
    flows = report.get("flows", [])
    counts = {"ok": 0, "drift": 0, "broken": 0}
    for flow in flows:
        counts[flow.get("status", "broken")] = counts.get(flow.get("status", "broken"), 0) + 1

    print(f"{len(flows)} flows checked: {counts.get('ok', 0)} ok, {counts.get('drift', 0)} drift, {counts.get('broken', 0)} broken\n")
    for flow in flows:
        if flow.get("status") != "ok":
            print(f"  [{flow.get('status').upper()}] {flow.get('name')}: {flow.get('findings')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Exploratory smoke-crawler agent")
    parser.add_argument("--test-file", default=Path("ui-tests/tests/test_login_flow.py"), type=Path)
    parser.add_argument("--url", default="https://www.saucedemo.com")
    parser.add_argument("--login-url", default="https://www.saucedemo.com")
    parser.add_argument("--username", default="standard_user")
    parser.add_argument("--password", default="secret_sauce")
    parser.add_argument("--reports-dir", default=Path("agentic/reports"), type=Path)
    args = parser.parse_args()

    report = asyncio.run(
        crawl(args.test_file, args.url, args.login_url, args.username, args.password)
    )

    report_path = save_report(report, args.reports_dir)
    print(f"Report saved to {report_path}\n")
    print_summary(report)


if __name__ == "__main__":
    main()
