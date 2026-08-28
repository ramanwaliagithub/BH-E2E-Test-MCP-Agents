# agentic/ — plain-language guide

This folder is a separate, optional add-on to the test suite. It lets an AI
agent (Claude) drive a real browser itself to do things a fixed script can't:
find a broken locator's replacement, or (later) explore the app and flag when
something changed. It never runs in CI and never edits your test files
directly — see "How it fits with the rest of the repo" below.

For the *why* behind each architecture choice, see [`ADR.md`](ADR.md). For a
chronological, command-by-command history of every change, see
[`../AGENTIC_BUILD_LOG.md`](../AGENTIC_BUILD_LOG.md). This file is the
plain-English map that ties both together.

## The big picture

Your existing suite (`ui-tests/`) is **scripted**: a human wrote every
locator and every click in advance, and it runs the same way every time.
That's exactly right for a regression suite, but it has no way to react when
something *unexpected* happens — like a website renaming an HTML attribute a
test depended on.

`agentic/` solves a narrower problem: **give an AI agent a real, controllable
browser, and a direct line to Claude, so it can look at a page and reason
about what changed.** Concretely, right now, that means two working agents:
- the **self-healing locator agent** — point it at a broken locator, and it
  logs into the site, looks at the page, and proposes a fixed selector as a
  diff for a human to review.
- the **natural-language test author** — give it a plain-English scenario,
  and it walks the live site to confirm the flow actually works, then emits a
  new pytest test file matching this repo's real Page Object conventions
  (read from disk, not guessed).

A third agent is designed for but not yet built (see "Not built yet" below):
an autonomous smoke-crawler.

## How it actually works, step by step

1. **A browser-for-AI service** ("Playwright MCP") runs in the background. It's
   the same Playwright engine your tests already use, but exposed as a set of
   named actions — `browser_navigate`, `browser_click`, `browser_snapshot`,
   etc. — that a program can call instead of a human clicking around.
2. **`mcp_client.py`** connects to that service, asks it "what actions do you
   support?", and translates the answer into a format Claude understands.
3. **`agent_loop.py`** is the brain loop: send Claude a task and the list of
   available actions → Claude decides it needs to use one (e.g. "take a
   snapshot of the page") → the loop actually runs that action via
   `mcp_client.py` → the result goes back to Claude → repeat until Claude has
   a final answer.
4. **`agents/locator_healer.py`** is one task built on that loop: "here's a
   broken locator, here's what it's supposed to do, here's the page — go find
   it." It turns Claude's final answer into a one-line code diff. It never
   edits your files — it only prints/returns the diff.
5. **`agents/test_author.py`** is a different task on the same loop: "here's
   a scenario in plain English." It reads your *real* Page Objects, fixtures,
   and markers off disk first (so it can't invent a convention that doesn't
   exist), walks the scenario live to confirm it actually works, then writes
   a new pytest test file matching that style.

## File-by-file map

| File | What it is | Why it's needed |
|---|---|---|
| `mcp_config.json` | Settings saying how to start the AI-controllable browser | Keeps that config out of your real `pytest.ini`/CI setup entirely |
| `mcp_client.py` | Connects to the browser service, lists its actions, wraps them for Claude | The one place that knows how to "speak MCP" — nothing else needs to |
| `agent_loop.py` | The reusable "ask Claude → run the action it wants → repeat" loop | Every agent (healer, and future ones) shares this instead of reinventing it |
| `agents/locator_healer.py` | The self-healing locator agent | Finds a broken locator's replacement, proposes a diff |
| `agents/test_author.py` | The natural-language test authoring agent | Turns a plain-English scenario into a new, convention-matching pytest file |
| `.env.example` | Template showing what secret config is needed | Documents the required `ANTHROPIC_API_KEY` without committing a real one |
| `.env.local` | Your real secret key (you created this, gitignored) | Lets `agent_loop.py` authenticate to Claude without hardcoding a key in code |
| `ADR.md` | Why-we-built-it-this-way document | Explains MCP vs. plain Playwright, why no LangChain, where human review sits, how CI stays untouched |
| `__init__.py` / `agents/__init__.py` | Empty marker files | Makes `agentic` and `agentic.agents` proper importable Python packages |

Everything above exists already — nothing on this list is still to be created
for either agent.

## Not built yet (from the original goals, still open)

- **Exploratory/autonomous smoke agent** — crawls key flows each run and
  flags drift before it breaks scripted tests. Per the ADR, this one would
  need its own separate, non-blocking CI workflow (never a required check).
  Would reuse `mcp_client.py` and `agent_loop.py` as-is — only a new file
  under `agents/` (plus its own tool allow-list and prompt) is needed.

## Two ways to build "the brain" — and a third way to test for free

`agent_loop.py` today is a ~60-line hand-written loop that calls the Anthropic
API directly. That was a deliberate choice, but it's worth naming the
alternatives, since it came up while troubleshooting billing:

| | **Custom loop (built)** | **LangChain** | **Run inside Claude Code** |
|---|---|---|---|
| What changes | Nothing — this is what exists | Swap `agent_loop.py` for LangChain's agent executor + `langchain-mcp-adapters`; adds 3 new dependencies | Rebuild the healer as a Claude Code skill/subagent instead of a standalone script |
| Needs its own paid API key? | Yes | Yes — same underlying API, same billing | **No** — uses your existing Claude Pro/Code subscription |
| Can run unattended (CI, scheduled) | Yes | Yes | No — only inside an interactive Claude Code session |
| Transparency | Every step visible in one file you wrote | Logic lives inside LangChain's library code | Logic lives inside a Claude Code skill, not your own codebase |
| Dependency surface | 2 packages (`anthropic`, `mcp`) | Several more packages, own release cadence | None (uses Claude Code itself) |
| Best for | A standalone tool you can explain/hand off/automate | Wanting LangChain's built-in memory/retries/tracing | Testing the *concept* right now without spending money |

**Current status:** built the custom-loop version (leftmost column), fully
wired and tested except for the final live run, which is blocked on the
Anthropic API account needing a funded credit balance
(console.anthropic.com → Settings → Billing) — a billing gap, not a code
issue. LangChain was considered and intentionally not used, per the
"auditable, no heavyweight framework" preference. The "run inside Claude Code"
path was raised as a way to test the concept without spending money, but
hasn't been built — it would mean building this as an interactive Claude Code
skill instead of the standalone script described in the original goals.

## How it fits with the rest of the repo

- `ui-tests/`, `api-tests/`, `api-tests-python/` — completely untouched by
  anything in `agentic/`. CI (`.github/workflows/tests.yml`) never installs or
  runs anything from this folder.
- `agentic`'s only dependency footprint is an *optional* extra in
  `ui-tests/pyproject.toml` (`uv sync --extra agentic`) — a plain `uv sync`
  (what CI runs) never installs `anthropic`/`mcp`.
- The locator healer never writes to `ui-tests/pages/` or `ui-tests/tests/` —
  it only ever returns a diff for a human to review and apply, same as any
  other pull request.

## Running the demos (once billing is sorted)

Run from the repo root, with `node`/`npx` on `PATH` and a funded key in
`agentic/.env.local`.

**Locator healer** — requires `ADD_TO_CART_BUTTON` in
`ui-tests/pages/inventory_page.py` to actually be broken first (it already is
in this repo, for exactly this purpose — see `AGENTIC_BUILD_LOG.md`):

```bash
ui-tests/.venv/Scripts/python.exe -m agentic.agents.locator_healer \
  --pom "ui-tests/pages/inventory_page.py" \
  --class-name InventoryPage \
  --locator ADD_TO_CART_BUTTON \
  --description "the Add to cart button for the Sauce Labs Backpack product on the inventory/products page" \
  --url "https://www.saucedemo.com/inventory.html" \
  --login-url "https://www.saucedemo.com" \
  --username standard_user \
  --password secret_sauce
```

**Test author** — no setup required, writes a new file under
`ui-tests/tests/`:

```bash
ui-tests/.venv/Scripts/python.exe -m agentic.agents.test_author \
  --scenario "Add the Sauce Labs Backpack and the Bike Light to the cart, then verify the cart shows 2 items" \
  --output test_multi_item_cart.py \
  --login-url "https://www.saucedemo.com" \
  --username standard_user \
  --password secret_sauce
```
