---
name: author-test-cc
description: Natural-language test authoring agent driven by Claude Code itself, with no separate Anthropic API key or standalone agent script. Given a plain-English scenario, walks the live app via the Playwright MCP server to confirm the flow actually works, then writes a new pytest test file under ui-tests/tests/ matching this repo's real conventions.
---

# author-test-cc

This is the "run inside Claude Code" variant of the test-authoring agent in
`agentic/agents/test_author.py`. That version makes a second, standalone call
to the Anthropic API. This version has no second AI call at all — **you**
(this Claude Code session) do the reasoning and write the file directly with
your own `Read`/`Write` tools. `agentic-claude-code/mcp_bridge.py` is the only
tool this needs, reused exactly as-is from `heal-locator-cc` — no new Python
file was needed to build this skill.

## Inputs needed from the user (ask if not given)

- `scenario` — plain-English description of what the test should do
- `output` — filename for the new test, e.g. `test_multi_item_cart.py`
- `url` — page the scenario starts on (default `https://www.saucedemo.com`)
- optionally `login_url`/`username`/`password` if the scenario needs auth

## Procedure

1. **Read this repo's real conventions first** (the `Read` tool, not MCP —
   these are local files): every file under `ui-tests/pages/*.py`,
   `ui-tests/conftest.py` (for available fixtures like `env_config`),
   `ui-tests/pytest.ini` (for the marker names — currently `smoke`,
   `regression`, `slow`), and `ui-tests/tests/test_login_flow.py` as a style
   reference. Treat all of this as ground truth — do not invent a Page
   Object method, fixture, or marker that isn't actually there.
2. **Plan the MCP steps** needed to walk the scenario live — navigate, log in
   if needed, click/fill whatever the scenario requires, then a
   `browser_snapshot` or read-only `browser_evaluate` to confirm the outcome
   the scenario describes (a cart count, an error message, a URL change).
   Same approach as `heal-locator-cc`: write the plan as JSON, run it via
   `python agentic-claude-code/mcp_bridge.py <plan.json>` (from repo root,
   using `ui-tests/.venv/Scripts/python.exe`, with `node`/`npx` on `PATH`).
   If something didn't work the way you expected, revise the plan and
   re-run — don't guess past a surprise.
3. **Write the test file directly** with your `Write` tool, following the
   conventions read in step 1 exactly:
   - a short module docstring only if this is a genuinely new file concept
   - `import pytest` then `from pages.<module> import <ClassName>` for every
     Page Object used
   - one `@pytest.mark.<marker>` decorator (`smoke` for a core happy path,
     `regression` for an edge/negative case)
   - `def test_<name>(page, env_config):` signature
   - a docstring stating the scenario and whether it's a HAPPY PATH or
     NEGATIVE CASE
   - `# Step N: ...` comments and assert statements with descriptive failure
     messages
   - if a step needs an element not covered by an existing Page Object
     method, follow this repo's own precedent: pass a raw CSS selector
     string straight into an existing generic method (e.g.
     `inventory_page.add_product_to_cart("button[data-test='...']")`) —
     verified live in step 2, never guessed from memory. Never invent a new
     Page Object class or method; leave a comment instead if one is
     genuinely needed.
4. **Validate the file** you just wrote is syntactically correct:
   `ui-tests/.venv/Scripts/python.exe -c "import ast; ast.parse(open('<path>').read())"`.
   If it fails, fix the file and re-validate before calling this done.
5. **Show the user the file's path and content.** Do not `git add`/`git
   commit` it yourself — that is a separate, explicit step the user decides
   on, same as every other file change in this repo.
6. **Clean up**: delete any temporary plan JSON (unless it's meant to stay as
   a documented example under `agentic-claude-code/examples/`) and remove any
   `.playwright-mcp/` directory the MCP server wrote during the run.

## Known issues (see heal-locator-cc/SKILL.md and crawl-flows-cc/SKILL.md for full details)

**1.** Playwright MCP's synthetic `browser_click` can silently no-op on this
site — it reports success but the page state doesn't change. If a step you
expect to change something (a cart badge, a page navigation) doesn't after a
click, don't assume your selector is wrong first — see the diagnostic
technique documented in `heal-locator-cc/SKILL.md` (a one-off raw
`element.click()` via `browser_evaluate`, used only to isolate the cause,
never as the actual test step). This actually happened live while building
this skill's own demo test (`test_multi_item_cart.py`) — the cart badge
verification needed the same workaround.

**2.** The MCP browser's `localStorage`/cart state persists across separate
`mcp_bridge.py` runs (unlike pytest-playwright's fresh context per test) —
see `crawl-flows-cc/SKILL.md` for the full discovery. If your scenario
depends on the cart starting empty, clear it first with
`window.localStorage.clear()` via `browser_evaluate` and re-navigate, or
account for pre-existing items when writing your verification steps. This
does **not** affect the generated test file itself — that runs through
pytest-playwright's own isolated fixtures — only your own live verification
while authoring it.

## What this skill deliberately does NOT do

- No `ANTHROPIC_API_KEY`, no `anthropic` package, no `agentic/agent_loop.py`.
- No import from `agentic/` at all — same separation as `heal-locator-cc`.
- No tool outside the safe set: navigate, snapshot, fill_form, click,
  evaluate (read-only only). Never call `browser_run_code_unsafe`.
- Never overwrites an existing test file — if `output` already exists, ask
  the user before proceeding rather than silently replacing it.
