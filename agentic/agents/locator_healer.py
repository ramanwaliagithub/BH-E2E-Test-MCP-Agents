"""Self-healing locator agent.

Given a POM class + locator constant that's known (or suspected) to be broken,
this agent drives a real browser via the Playwright MCP server, re-locates the
intended element semantically (accessibility role/name, page structure, and a
read-only DOM query to recover a durable attribute — never by trusting the old
selector), and proposes a fix as a unified diff against the POM source file.

It never edits the POM file itself. A human reviews the diff and applies it —
per the project's human-in-the-loop gate, this agent has no write access to
framework/ui-tests code.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from agentic.agent_loop import run_agent_loop
from agentic.mcp_client import MCPClient

# Read-only exploration + the minimum interaction needed to reach the target page
# (e.g. logging in). No file upload/drag/JS-eval-for-mutation/tab management —
# this agent only ever needs to look at a page and click through a login form.
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
You are a Playwright locator-healing assistant for a Python Page Object Model \
(POM) test suite. You are given one locator constant that is broken or \
suspected broken, and your job is to find the correct selector for the same \
element on the live page — never assume the old selector still works.

Strategy:
1. If a login step is described, perform it first (browser_fill_form + \
browser_click) to reach the target page.
2. Use browser_snapshot to understand the page and find the element matching \
the given description by its accessible role and name.
3. Accessible name alone is often ambiguous — e.g. multiple buttons on a page \
can share the exact same name (like several "Add to cart" buttons, one per \
product). When that happens, use browser_evaluate to run a small READ-ONLY \
JavaScript snippet (querySelector/querySelectorAll, textContent, getAttribute — \
never anything that changes page state) to find the one specific element \
scoped by nearby distinguishing text, and read a stable identifying attribute \
from it (id, data-test, data-testid, or a unique class).
4. Prefer a CSS selector using that stable attribute, consistent with this \
codebase's existing convention (e.g. button[data-test='...']). Only fall back \
to a Playwright text-scoped CSS selector (using :has-text()) if no such \
attribute exists.
5. Never call browser_evaluate to click, type, submit, or otherwise mutate the \
page — only to read attributes/text you can already see are safe to read.

When you are confident in your answer, respond with ONLY a single JSON object \
as your final message — no markdown fences, no other text before or after it:
{"found": true|false, "new_locator": "<selector string, or empty if not found>", \
"confidence": "high"|"medium"|"low", "reasoning": "<1-3 sentences>"}
"""


@dataclass
class LocatorSite:
    const_name: str
    lineno: int
    line: str
    current_value: str


def find_locator(source: str, class_name: str, const_name: str) -> LocatorSite:
    """Locate a `CONST_NAME = "value"` class attribute via AST, for a precise diff."""
    import ast

    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == class_name):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                continue
            if stmt.targets[0].id != const_name:
                continue
            if not isinstance(stmt.value, ast.Constant) or not isinstance(stmt.value.value, str):
                continue
            return LocatorSite(
                const_name=const_name,
                lineno=stmt.lineno,
                line=lines[stmt.lineno - 1],
                current_value=stmt.value.value,
            )

    raise ValueError(f"Could not find '{const_name}' as a string constant in class '{class_name}'")


def build_healed_line(original_line: str, const_name: str, new_value: str) -> str:
    """Replace only the string literal on a `CONST_NAME = "old"` line, keeping formatting."""
    match = re.match(
        rf"^(?P<indent>\s*){re.escape(const_name)}(?P<sep>\s*=\s*)(?P<quote>['\"])(?P<old>.*)(?P=quote)(?P<trail>\s*)$",
        original_line,
    )
    if not match:
        raise ValueError(f"Line does not match expected 'CONST = \"...\"' shape: {original_line!r}")

    quote = match["quote"]
    if quote in new_value and "'" not in new_value:
        quote = "'"
    elif quote in new_value:
        quote = '"' if new_value.count('"') < new_value.count("'") else "'"

    newline = "\n" if original_line.endswith("\n") else ""
    return f"{match['indent']}{const_name}{match['sep']}{quote}{new_value}{quote}{match['trail'].rstrip(chr(10))}{newline}"


def build_diff(pom_path: Path, source: str, site: LocatorSite, new_value: str) -> str:
    old_lines = source.splitlines(keepends=True)
    new_lines = old_lines.copy()
    new_lines[site.lineno - 1] = build_healed_line(site.line, site.const_name, new_value)
    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=str(pom_path),
        tofile=str(pom_path),
        lineterm="",
    )
    # Normalize line endings before rejoining: content lines carry their own "\n"
    # (from splitlines(keepends=True)) but header/hunk lines don't (lineterm=""),
    # so join naively concatenates them — strip and rejoin uniformly instead.
    return "\n".join(line.rstrip("\n") for line in diff_lines)


def extract_json(text: str) -> dict:
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    return json.loads(stripped)


def build_user_prompt(
    class_name: str,
    const_name: str,
    current_value: str,
    description: str,
    url: str,
    login_url: str | None,
    username: str | None,
    password: str | None,
) -> str:
    login_section = ""
    if login_url:
        login_section = (
            f"\nTo reach the target page you must first log in at {login_url} "
            f"with username '{username}' and password '{password}'.\n"
        )
    return f"""\
The locator `{class_name}.{const_name}` in our Page Object Model is broken or \
suspected broken. Its current (possibly stale) value is:

    {current_value!r}

This locator is meant to target: {description}
{login_section}
Navigate to {url} and find the correct, durable selector for this element. \
Follow the strategy in your instructions, then respond with the final JSON \
object only.
"""


async def heal_locator(
    pom_path: Path,
    class_name: str,
    const_name: str,
    description: str,
    url: str,
    login_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> tuple[dict, str]:
    """Run the healing agent. Returns (parsed JSON verdict, unified diff string)."""
    source = pom_path.read_text()
    site = find_locator(source, class_name, const_name)

    user_prompt = build_user_prompt(
        class_name, const_name, site.current_value, description, url, login_url, username, password
    )

    async with MCPClient.from_config() as client:
        response_text = await run_agent_loop(
            client,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            allowed_tools=ALLOWED_TOOLS,
        )

    verdict = extract_json(response_text)
    diff = ""
    if verdict.get("found") and verdict.get("new_locator"):
        diff = build_diff(pom_path, source, site, verdict["new_locator"])
    return verdict, diff


def main() -> None:
    parser = argparse.ArgumentParser(description="Self-healing Playwright locator agent")
    parser.add_argument("--pom", required=True, type=Path, help="Path to the POM file, e.g. ui-tests/pages/inventory_page.py")
    parser.add_argument("--class-name", required=True, help="Class name inside the POM file, e.g. InventoryPage")
    parser.add_argument("--locator", required=True, help="Locator constant name, e.g. ADD_TO_CART_BUTTON")
    parser.add_argument("--description", required=True, help="Plain-English description of the element, e.g. 'the Add to cart button for the Sauce Labs Backpack product'")
    parser.add_argument("--url", required=True, help="URL of the page containing the element")
    parser.add_argument("--login-url", default=None, help="Login page URL, if the target page requires auth")
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    args = parser.parse_args()

    verdict, diff = asyncio.run(
        heal_locator(
            args.pom,
            args.class_name,
            args.locator,
            args.description,
            args.url,
            args.login_url,
            args.username,
            args.password,
        )
    )

    print(json.dumps(verdict, indent=2))
    if diff:
        print("\n--- proposed diff (not applied) ---\n")
        print(diff)


if __name__ == "__main__":
    main()
