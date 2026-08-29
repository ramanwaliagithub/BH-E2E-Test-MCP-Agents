# agentic-claude-code/ — the "no separate API key" variant

This is a second implementation of all three agents from the original plan,
kept **completely separate** from [`agentic/`](../agentic/README.md) — no
shared code, no shared config, different mechanism for "the brain." Nothing
here was removed or changed in `agentic/`; both exist side by side so you can
compare them directly. Three skills live here:

- **`heal-locator-cc`** — self-healing locator agent
- **`author-test-cc`** — natural-language test authoring agent
- **`crawl-flows-cc`** — exploratory smoke-crawler agent

All three are real and have actually run, live, at zero API cost — unlike
their `agentic/` counterparts, which are fully built but still blocked on a
funded Anthropic API key.

## The difference in one sentence

`agentic/` has Claude Code call a **second, separate Claude** (via the
Anthropic API, its own key, its own billing) to do the reasoning.
`agentic-claude-code/` has **this Claude Code session itself** do the
reasoning — no second AI call, no API key, no billing beyond your existing
Claude Pro/Code subscription. The tradeoff: it only works interactively,
inside a session like this one — it can't be scheduled or run unattended the
way a standalone script can.

## Why this needed its own approach, not just "reuse `agentic/mcp_client.py`"

`agentic/mcp_client.py` is designed to stay connected for an entire
Claude↔tool conversation happening inside one Python process
(`agent_loop.py`'s loop). Here, *I* (Claude Code) issue commands one Bash call
at a time — a single MCP tool call per Bash invocation would spawn a brand
new, memory-less browser each time (no login, no navigation history carried
over). So `mcp_bridge.py` instead takes a **whole ordered plan** of tool calls
and runs all of them in one persistent browser session, printing every
result — I decide the full plan upfront, then read the combined output to
reason about the fix.

## Files in this folder

| File | What it is | Why it exists |
|---|---|---|
| `mcp_config.json` | Own copy of the Playwright MCP server config | Deliberately duplicated from `agentic/mcp_config.json` rather than shared, so this folder has zero file dependency on `agentic/` |
| `mcp_bridge.py` | Runs an ordered list of MCP tool calls in one browser session, prints each result | The only "tool" any of the three skills needs — no Anthropic SDK import anywhere in it, and no changes were needed to add the second and third skill |
| `pom_diff.py` | Turns a healed locator value into a unified diff against a POM file | Used only by `heal-locator-cc`. Intentionally a duplicate of the same ~40 lines of logic in `agentic/agents/locator_healer.py`, kept separate on purpose |
| `examples/heal_add_to_cart_button.steps.json` | A real, saved plan — login, navigate to inventory, disambiguate and read the "Add to cart" button for the backpack | Documents exactly what a real `heal-locator-cc` run looked like |
| `examples/heal_remove_from_cart_button.steps.json` | A second real saved plan — needs the item added to the cart first before the "Remove" button even exists | A second `heal-locator-cc` example, distinct in that it needs a state-changing step first |
| `examples/smoke_crawl_test_login_flow.json` | The real drift report from crawling `test_login_flow.py` | Documents exactly what a real `crawl-flows-cc` run found, including a genuine `drift` finding — see below |
| `../.claude/skills/heal-locator-cc/SKILL.md` | Recipe: given a broken locator, find and diff the fix | Packages the locator-healing procedure into a documented, repeatable skill |
| `../.claude/skills/author-test-cc/SKILL.md` | Recipe: given a scenario, write a new test file | No new Python needed — Claude Code's own `Read`/`Write` tools do the conventions-gathering and file-writing that `agentic/agents/test_author.py` had to hand-write |
| `../.claude/skills/crawl-flows-cc/SKILL.md` | Recipe: given a test file, report on drift | Also needed no new Python — reads the test file, walks it, writes a report, all with Claude Code's own tools |

## How each skill actually ran (real, not hypothetical)

**`heal-locator-cc`**, twice — for `ADD_TO_CART_BUTTON` and later
`REMOVE_FROM_CART_BUTTON`. The second one needed an extra step (add the item
to the cart first, since the "Remove" button doesn't exist until then) and
surfaced the very first find of the `browser_click`-silently-no-ops issue
(see the skill file's "Known issues" section) — worked around with a one-off
raw `element.click()` diagnostic. Both produced clean, human-reviewable
diffs; see `../AGENTIC_BUILD_LOG.md` for full output and exact commands.

**`author-test-cc`**, once — scenario: "Add the Sauce Labs Backpack and the
Bike Light to the cart, then verify the cart shows 2 items." Read the real
`ui-tests/pages/*.py`/`conftest.py`/`pytest.ini`/`test_login_flow.py`
conventions first, hit the same click-no-op issue verifying the flow (worked
around the same way), then wrote `ui-tests/tests/test_multi_item_cart.py`.
**This one was verified all the way through**: it was run for real via
`pytest tests/test_multi_item_cart.py` (the actual deterministic suite, not
MCP) and **passed** — a real, working, newly-authored test.

**`crawl-flows-cc`**, once — against the real `ui-tests/tests/test_login_flow.py`.
Walked all 4 flows live and found 3 `ok` plus one genuine `drift`: the
`test_complete_purchase_flow` test hardcodes its own correct selector literal
instead of using `InventoryPage.ADD_TO_CART_BUTTON` (which is currently
broken) — so the test passes today, but only because it doesn't use the
class constant meant to represent that exact button. That's a real
maintainability gap a rigid pass/fail assertion would never surface, and
it's the entire reason this agent's `ok`/`drift`/`broken` scale (not just
pass/fail) exists. The full report is saved at
`examples/smoke_crawl_test_login_flow.json`.

This run also surfaced a second real issue: it initially found the cart
already containing 2 items from the prior `author-test-cc` run, because the
MCP browser's `localStorage` (where Sauce Demo keeps its cart) isn't reset
between separate script invocations — unlike pytest-playwright's fresh
context per test. Documented in `crawl-flows-cc/SKILL.md`'s "Known issues,"
along with the fix (`window.localStorage.clear()` before checking
cart-dependent flows).

## Running it yourself

```bash
cd <repo root>   # node/npx must be on PATH

# heal-locator-cc: run a plan, then diff
ui-tests/.venv/Scripts/python.exe agentic-claude-code/mcp_bridge.py \
  agentic-claude-code/examples/heal_add_to_cart_button.steps.json
ui-tests/.venv/Scripts/python.exe agentic-claude-code/pom_diff.py \
  --pom "ui-tests/pages/inventory_page.py" --class-name InventoryPage \
  --locator ADD_TO_CART_BUTTON --new-value "<the value the plan found>"

# author-test-cc and crawl-flows-cc have no dedicated script — they're
# Claude Code itself reading/writing files directly, per their SKILL.md
# procedures. Easiest path: open a Claude Code session in this repo and
# invoke /author-test-cc or /crawl-flows-cc.
```

No `ANTHROPIC_API_KEY` needed anywhere in this folder — `mcp_bridge.py` and
`pom_diff.py` never import `anthropic`. The only cost is whatever your Claude
Pro/Code plan already covers for the session doing the reasoning.

## Fits with the rest of the repo like `agentic/` does — with one real difference

Nothing here runs in CI, nothing here can be triggered by
`.github/workflows/tests.yml`. But unlike `agentic/`, **not every skill here
is read-only**: `heal-locator-cc` and `crawl-flows-cc` never write to
`ui-tests/`, but `author-test-cc`'s entire job is to write a new test file
there (never an existing one) — same as its `agentic/agents/test_author.py`
counterpart. The human-review gate for that is the same as everywhere else
in this repo: nothing here calls `git add`/`git commit` itself, so the
generated file sits in the working tree for a human to review before it
becomes a commit. The `mcp` Python package (needed by `mcp_bridge.py`) is
already installed via `ui-tests/pyproject.toml`'s `agentic` optional-dependency
group — reused because it's a third-party protocol library, not "the other
implementation"; no new dependency was added for this folder.
