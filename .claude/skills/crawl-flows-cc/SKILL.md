---
name: crawl-flows-cc
description: Exploratory smoke-crawler agent driven by Claude Code itself, with no separate Anthropic API key or standalone agent script. Given an existing pytest test file, walks each of its flows live via the Playwright MCP server and reports whether each one still behaves the way the test assumes — never fixes or writes test code, only a drift report.
---

# crawl-flows-cc

This is the "run inside Claude Code" variant of the smoke-crawler agent in
`agentic/agents/smoke_crawler.py`. That version makes a second, standalone
call to the Anthropic API. This version has no second AI call — **you** (this
Claude Code session) read the test file, walk each flow via
`agentic-claude-code/mcp_bridge.py`, and write the report directly. Same
tool, same MCP config, as `heal-locator-cc` and `author-test-cc` — no new
Python file was needed to build this skill either.

This is the most conservative of the three `-cc` skills: it never fixes
anything and never writes to `ui-tests/` at all — its only output is a
report.

## Inputs needed from the user (ask if not given)

- `test_file` — path to an existing pytest test file (default
  `ui-tests/tests/test_login_flow.py`)
- `url` — base URL of the app (default `https://www.saucedemo.com`)
- optionally `login_url`/`username`/`password`, though these are usually
  already visible inside the test file itself

## Procedure

1. **Read the real test file** (the `Read` tool). Each `test_*` function is
   one flow: its docstring says what it's testing, its body shows exactly
   which locators and values it uses, and its `assert` statements say what
   "correct" looks like. Treat this as the single source of truth for what
   to check — never invent a flow that isn't actually in the file.
2. **For each flow, plan the MCP steps** needed to walk it live, using the
   exact same locators/values the test function uses (same login
   credentials, same selectors, same URL fragments to check for). Write the
   plan as JSON, run it via `python agentic-claude-code/mcp_bridge.py
   <plan.json>` (from repo root, `ui-tests/.venv/Scripts/python.exe`, with
   `node`/`npx` on `PATH`). You can check several flows in one plan if they
   share a starting point (e.g. login), or run one plan per flow — whichever
   keeps the plan easiest to reason about.
3. **Classify each flow** based on what you actually observed:
   - `ok` — behaves exactly as the test file assumes.
   - `drift` — you could still complete the flow, but something differs from
     what the test file assumes (different text, a workaround was needed, an
     extra step appeared) — the scripted test might still pass today but is
     relying on something that quietly changed.
   - `broken` — the flow does not work at all as written.
4. **Write a report directly** with your `Write` tool — a JSON file under
   `agentic-claude-code/reports/` (create the directory if it doesn't exist),
   named `smoke_crawl_<UTC timestamp>.json`, shaped like:
   ```json
   {"flows": [{"name": "<test function name>", "status": "ok"|"drift"|"broken", "findings": "<1-3 sentences, empty if ok>"}]}
   ```
5. **Summarize the findings in chat** — how many flows checked, how many of
   each status, and the specific finding for anything not `ok`.
6. **Never modify `ui-tests/` files.** This skill only ever reads test files
   and writes reports — no diffs, no new test files, no fixes. That's a
   separate, deliberate step for a human (or `heal-locator-cc`/
   `author-test-cc`) to take afterward.
7. **Clean up**: delete any temporary plan JSON and remove any
   `.playwright-mcp/` directory the MCP server wrote during the run.

## Known issues

**1. `browser_click` can silently no-op** (see `heal-locator-cc/SKILL.md` for
full details). Playwright MCP's synthetic click can report success while the
page state doesn't actually change. Don't classify a flow as `broken` on
that basis alone: verify with the same one-off diagnostic technique
(`element.click()` via `browser_evaluate`, used only to confirm whether the
*app* responds to a click at all) before concluding the site itself is
broken versus the MCP click mechanism being unreliable here. If the
diagnostic click works but the normal MCP click didn't, that's a known
tooling quirk, not a finding about this repo's test suite.

**2. The MCP browser's `localStorage`/cart state persists across separate
runs of `mcp_bridge.py`.** Discovered live: Sauce Demo stores its cart in
`localStorage` under the key `cart-contents`, and the MCP server's browser
profile is *not* reset between separate script invocations the way
pytest-playwright resets it between tests (this repo's own
`ui-tests/conftest.py` explicitly documents "a fresh isolated context/page
per test" — the MCP-driven crawl does not get that for free). A crawl run
right after a `heal-locator-cc`/`author-test-cc` run that added items to the
cart will see that leftover cart state, which can make an "Add to cart"
button already show "Remove" and make counts look wrong for reasons that
have nothing to do with the actual app or test. **Before checking any flow
that depends on cart/session state starting empty, clear it first**:
```json
{"tool": "browser_evaluate", "args": {"function": "() => { window.localStorage.clear(); return {cleared: true}; }"}}
```
followed by a fresh `browser_navigate` to reload the page with the cleared
state. Never report this kind of cross-run contamination as drift in the
app or the test — it's an artifact of this crawling tool's browser reuse,
not something the real, isolated pytest suite would ever experience.

## What this skill deliberately does NOT do

- No `ANTHROPIC_API_KEY`, no `anthropic` package, no `agentic/agent_loop.py`.
- No import from `agentic/` at all — same separation as the other two `-cc`
  skills.
- No tool outside the safe set: navigate, snapshot, fill_form, click,
  evaluate (read-only only, except the one sanctioned diagnostic use above).
  Never call `browser_run_code_unsafe`.
- Never writes to `ui-tests/pages/` or `ui-tests/tests/` — this is the one
  agent variant that writes nothing except its own report.
