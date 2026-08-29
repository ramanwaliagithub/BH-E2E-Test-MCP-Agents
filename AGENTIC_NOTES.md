# Agentic Layer — Technical Notes

Standalone notes on the `agentic/` and `agentic-claude-code/` work: what it
is, why it's built the way it is, and what was actually discovered while
building it. This is a summary layer on top of the exhaustive
[AGENTIC_BUILD_LOG.md](AGENTIC_BUILD_LOG.md) — that file has every command
and every file; this one is the condensed version of what matters.

---

## What exists

Two separate implementations of the same three agents, sitting alongside the
deterministic `ui-tests/` suite without touching it or running in CI:

| | `agentic/` | `agentic-claude-code/` |
|---|---|---|
| Reasoning engine | A second, standalone Claude API call (`anthropic` SDK, own key) | This Claude Code session itself |
| Cost | Real, metered API usage | Whatever the existing Claude Pro/Code plan already covers |
| Can run unattended (CI, cron) | Yes | No — interactive only |
| Status | All 3 built, pure logic tested, **never run live** (unfunded API account) | All 3 built and **run live**, including one generated test that passes for real |

The three agents, same in both implementations:

1. **Self-healing locator agent** (`locator_healer.py` / `heal-locator-cc`) —
   given a broken POM locator, drives a real browser to re-locate the
   element and proposes a fix as a diff. Never writes to `ui-tests/`.
2. **Natural-language test author** (`test_author.py` / `author-test-cc`) —
   given a plain-English scenario, walks it live, then writes a brand-new
   pytest file matching the repo's real conventions. The only agent that
   writes anything, and only ever a new file.
3. **Exploratory smoke-crawler** (`smoke_crawler.py` / `crawl-flows-cc`) —
   given an existing test file, walks its flows live and classifies each as
   `ok`/`drift`/`broken`. Writes only a report, never touches `ui-tests/`.

## Architecture decisions and why

- **Playwright MCP, not Playwright's own codegen.** Codegen records a
  literal action script tied to whatever was under the cursor at record
  time — no notion of "this failed, find its replacement" or "do what I
  describe in English." MCP exposes the same Playwright engine as callable
  tools (`browser_navigate`, `browser_snapshot`, ...) an LLM can reason over
  directly, with `browser_snapshot` returning an accessibility tree as text
  instead of a screenshot.
- **A hand-written ~90-line tool-use loop (`agent_loop.py`), not LangChain.**
  Every agent's entire "brain" is: call Claude, run whatever tool it asks
  for via MCP, feed the result back, repeat. A framework would add its own
  tool-calling abstraction on top of Anthropic's native one, a larger
  dependency surface with its own release cadence, and a layer of
  indirection between "what the model asked for" and "what ran" that makes
  debugging slower.
- **Tool allow-listing per agent.** Playwright MCP exposes 24 tools,
  including one its own docs call "RCE-equivalent"
  (`browser_run_code_unsafe`). Every agent is handed only the ~7 tools its
  task actually needs — enforced both in what the model is shown and what
  can actually execute, not just a suggestion in the prompt.
- **Different write behavior per agent, deliberately.** The locator healer
  and smoke-crawler never call `Path.write_text()`/`Write` on anything under
  `ui-tests/` — full stop. The test author does, but only ever for a
  brand-new filename (refuses to overwrite an existing one). In both
  implementations, nothing in this layer ever calls `git add`/`git commit`
  itself — that's always a separate, human-initiated step.
- **`agentic-claude-code/` duplicates rather than imports from `agentic/`**
  (the small diff-building and JSON-extraction helpers exist in both). This
  was deliberate: the two approaches should never share code or state, so
  either one can be deleted or changed without touching the other.
- **Grounding in real files, not memorized conventions.** The test author
  and smoke-crawler both read the actual `ui-tests/pages/*.py`,
  `conftest.py`, `pytest.ini`, and an existing test file off disk before
  doing anything — so generated code can't invent a fixture, marker, or
  method that doesn't exist, and stays correct automatically as the real
  POM evolves.

## Real problems found while building this (not hypothetical)

- **Accessible names collide.** Every "Add to cart" button on Sauce Demo's
  inventory page has the exact same accessibility-tree name — role+name
  alone can't tell one product's button from another's. Fix: scope a
  `browser_evaluate` DOM query using a sibling locator already in the same
  POM class (e.g. `.inventory_item`) plus the product's text, then read a
  stable attribute (`data-test`) straight from the live DOM.
- **Playwright MCP's synthetic click can silently no-op on this site.** A
  `browser_click` on certain buttons reports success — normal trace, no
  error — but the page state never actually changes. Root cause not fully
  identified (likely specific to how the MCP server's headless Chromium
  build synthesizes the click for this element); confirmed the *app* and
  *element* are both fine by calling the DOM's native `element.click()`
  directly via `browser_evaluate` as a one-off diagnostic. This is a quirk
  of the MCP-driven click path specifically — the same button works fine
  through real Playwright (`pytest-playwright`, no MCP involved).
- **The MCP browser's `localStorage` isn't reset between separate script
  runs.** Sauce Demo keeps its cart in `localStorage`; the MCP server's
  browser profile carries that over across separate `mcp_bridge.py`
  invocations, unlike `pytest-playwright`'s fresh context per test. Caused a
  real false-positive mid-crawl (cart showed 2 items before anything had
  been clicked) — traced to leftover state from an unrelated prior run,
  fixed with `window.localStorage.clear()` + re-navigate before checking any
  cart-dependent flow.
- **Environment/venv portability.** `ui-tests/.venv` was created under one
  Windows user account and referenced an interpreter path that didn't exist
  under a different one in a later session — a pure build-artifact problem
  (already gitignored), fixed with `rm -rf .venv && uv sync --extra
  agentic`. Also had to install the Playwright MCP server's own browser
  binary fresh in each new environment
  (`npx @playwright/mcp@latest install-browser chrome-for-testing`) — it's
  a separate Playwright install from the one `ui-tests/uv.lock` manages.

## Current status

- `agentic/`: all three agents fully coded and unit-tested on their pure
  logic (AST parsing, diff building, JSON extraction, grounding-context
  gathering). **Zero live runs** — every one is blocked at the first real
  Anthropic API call pending a funded account.
- `agentic-claude-code/`: all three skills have run live for real, at zero
  cost. Two produced concrete, verifiable output: a diff for each of two
  intentionally-broken locators (`ADD_TO_CART_BUTTON`,
  `REMOVE_FROM_CART_BUTTON`, both still broken in the repo on purpose,
  original values kept as comments), a new test file
  (`ui-tests/tests/test_multi_item_cart.py`) that was independently run
  through the real `pytest` suite and passed, and a drift report
  (`agentic-claude-code/examples/smoke_crawl_test_login_flow.json`) that
  found a genuine inconsistency: `test_complete_purchase_flow` passes today
  only because it hardcodes a selector literal instead of using the
  (currently broken) `InventoryPage.ADD_TO_CART_BUTTON` constant.
- Both intentional locator breaks are pushed to `main` and will fail the
  `ui-tests` CI job until someone applies one of the proposed fixes — this
  is expected, not a regression.

## Where the rest of the detail lives

- [`AGENTIC_BUILD_LOG.md`](AGENTIC_BUILD_LOG.md) — every file, every
  command, in chronological order.
- [`agentic/ADR.md`](agentic/ADR.md) — the formal architecture decision
  record (MCP vs. codegen, loop vs. LangChain, CI isolation).
- [`agentic/README.md`](agentic/README.md) /
  [`agentic-claude-code/README.md`](agentic-claude-code/README.md) —
  plain-language, file-by-file maps of each implementation.
- `.claude/skills/heal-locator-cc/`, `author-test-cc/`, `crawl-flows-cc/` —
  the runnable procedures for the Claude-Code-driven variant, including the
  known-issues sections referenced above.
