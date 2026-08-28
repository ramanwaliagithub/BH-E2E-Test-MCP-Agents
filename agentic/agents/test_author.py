"""Natural-language test authoring agent.

Given a plain-English scenario, explores the live app via MCP tools to
confirm each step actually works, then emits a complete new pytest test file
under ui-tests/tests/ that matches this repo's existing conventions exactly —
not a one-off recorded script. Reuses agent_loop.py/mcp_client.py; the only
new logic here is grounding the model in the real POM/test/fixture/marker
files (so it can't invent conventions) and writing out a validated result.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import re
from pathlib import Path

from agentic.agent_loop import run_agent_loop
from agentic.mcp_client import MCPClient

# Same rationale as locator_healer.py: read-only exploration plus the minimum
# interaction needed to walk the scenario (click, fill forms, wait). No file
# upload/drag/tab management/unsafe code execution.
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
You are a test-authoring assistant for a Python Playwright/pytest UI suite \
that uses the Page Object Model. You are given a plain-English scenario and \
must produce ONE complete, runnable pytest test function for it.

You will be shown this repo's real, current Page Object classes, an existing \
test file (as a style reference), the pytest fixtures available, and the \
pytest markers this project defines. Treat all of that as ground truth for \
what conventions to follow — do not invent methods, locators, fixtures, or \
markers that aren't shown to you.

Strategy:
1. Walk the scenario yourself using the browser tools first — navigate, log \
in if the scenario needs it, and perform each step — to confirm the flow \
actually works on the live site and that any assertion you plan to write \
would actually hold. Use browser_snapshot to see the page and confirm state \
after each action (e.g. a cart badge count, an error message, a URL change).
2. If a step needs an element not covered by an existing Page Object method, \
follow this repo's own precedent: pass a raw CSS selector string directly \
into an existing generic method (e.g. `inventory_page.add_product_to_cart(\
"button[data-test='...']")`) — verify that selector actually matches on the \
live page (browser_snapshot / a read-only browser_evaluate query) rather \
than guessing it from memory. Never introduce a new Page Object class or \
method — if the scenario truly needs one, say so in a comment instead of \
inventing it.
3. Match the shown style exactly: a short module docstring only if this is \
framed as a new file, `import pytest` plus `from pages.<module> import \
<ClassName>` for every Page Object used, one `@pytest.mark.<marker>` \
decorator per test (pick smoke or regression based on the scenario — smoke \
for a core happy-path flow, regression for edge/negative cases), a \
`def test_<name>(page, env_config):` signature, a docstring stating the \
scenario and whether it's a HAPPY PATH or NEGATIVE CASE, `# Step N: ...` \
comments, and assert statements with descriptive failure messages.

When you are done, respond with ONLY a single fenced Python code block \
containing the complete file content — no other prose before or after it.
"""


def gather_pom_conventions(ui_tests_dir: Path) -> str:
    """Read the real POM/test/fixture/marker files so the model is grounded in
    what actually exists instead of guessing conventions from memory."""
    parts = []

    pages_dir = ui_tests_dir / "pages"
    for pom_file in sorted(pages_dir.glob("*.py")):
        parts.append(f"### {pom_file.relative_to(ui_tests_dir)}\n```python\n{pom_file.read_text()}```")

    conftest = ui_tests_dir / "conftest.py"
    if conftest.exists():
        parts.append(f"### {conftest.relative_to(ui_tests_dir)} (available fixtures)\n```python\n{conftest.read_text()}```")

    example_test = ui_tests_dir / "tests" / "test_login_flow.py"
    if example_test.exists():
        parts.append(f"### {example_test.relative_to(ui_tests_dir)} (style reference)\n```python\n{example_test.read_text()}```")

    pytest_ini = ui_tests_dir / "pytest.ini"
    if pytest_ini.exists():
        parts.append(f"### {pytest_ini.relative_to(ui_tests_dir)} (available markers)\n```ini\n{pytest_ini.read_text()}```")

    return "\n\n".join(parts)


def extract_python_code(text: str) -> str:
    """Pull the fenced ```python code block out of the model's final answer."""
    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if not match:
        raise ValueError(f"No fenced python code block found in model output:\n{text}")
    return match.group(1)


def build_user_prompt(scenario: str, conventions: str, url: str, login_url: str | None, username: str | None, password: str | None) -> str:
    login_section = ""
    if login_url:
        login_section = f"\nTo reach the relevant page(s) you may need to log in at {login_url} with username '{username}' and password '{password}'.\n"
    return f"""\
Scenario to author a test for:

    {scenario}

The app under test is at {url}.{login_section}

Here are this repo's real conventions to follow exactly:

{conventions}

Walk the scenario live first, then respond with the final test file only.
"""


async def author_test(
    scenario: str,
    ui_tests_dir: Path,
    url: str,
    login_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> str:
    """Run the authoring agent. Returns the generated test file's source code
    (already validated as syntactically valid Python) — does not write it to disk."""
    conventions = gather_pom_conventions(ui_tests_dir)
    user_prompt = build_user_prompt(scenario, conventions, url, login_url, username, password)

    async with MCPClient.from_config() as client:
        response_text = await run_agent_loop(
            client,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            allowed_tools=ALLOWED_TOOLS,
        )

    code = extract_python_code(response_text)

    try:
        ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Model produced invalid Python: {exc}\n\n{code}") from exc

    return code


def main() -> None:
    parser = argparse.ArgumentParser(description="Natural-language test authoring agent")
    parser.add_argument("--scenario", required=True, help="Plain-English description of the test scenario")
    parser.add_argument("--output", required=True, help="Filename to write under <ui-tests-dir>/tests/, e.g. test_multi_item_cart.py")
    parser.add_argument("--url", default="https://www.saucedemo.com", help="Base URL of the app under test")
    parser.add_argument("--login-url", default=None)
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--ui-tests-dir", default="ui-tests", type=Path)
    parser.add_argument("--force", action="store_true", help="Overwrite the output file if it already exists")
    args = parser.parse_args()

    output_path = args.ui_tests_dir / "tests" / args.output
    if output_path.exists() and not args.force:
        raise SystemExit(f"{output_path} already exists — pass --force to overwrite")

    code = asyncio.run(
        author_test(args.scenario, args.ui_tests_dir, args.url, args.login_url, args.username, args.password)
    )

    output_path.write_text(code)
    print(f"Wrote {output_path}")
    print("\n--- generated test (review before committing) ---\n")
    print(code)


if __name__ == "__main__":
    main()
